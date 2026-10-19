import getpass
import json
import os
import re
import shutil
import threading
import time
from urllib.parse import parse_qs, urlparse

import requests

API_URL = "https://api.real-debrid.com/rest/1.0"

# same value qBittorrent uses for an unknown ETA, the library card shows it as "∞"
INFINITE_ETA = 8640000

CHUNK_SIZE = 1024 * 1024


class RealDebridError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

    def is_transient(self):
        return self.status_code == 429 or (self.status_code or 0) >= 500


class RDTorrent:
    """
    A download tracked by JCRealDebrid, exposes the same attributes the UI reads from qBittorrent torrents.
    """
    def __init__(self, magnet_uri, name, content_path, rd_id=None, state="queued", error=None, progress=0.0):
        self.magnet_uri = magnet_uri
        self.name = name
        self.content_path = content_path
        self.rd_id = rd_id
        self.state = state
        self.error = error
        self.progress = progress
        self.dlspeed = 0
        self.eta = 0 if state == "completed" else INFINITE_ETA
        # held while changing the state, so a stopped worker can't overwrite a pause
        self.lock = threading.Lock()

    def to_dict(self):
        return {"magnet_uri": self.magnet_uri, "name": self.name, "content_path": self.content_path,
                "rd_id": self.rd_id, "state": self.state, "error": self.error, "progress": self.progress}

    @classmethod
    def from_dict(cls, data):
        return cls(data["magnet_uri"], data["name"], data["content_path"], data.get("rd_id"), data.get("state", "queued"),
                   data.get("error"), data.get("progress", 0.0))


class JCRealDebrid:
    """
    A class to download JC141 releases through Real-Debrid, a drop-in replacement for JCQbt.

    Magnets are added to Real-Debrid, which downloads them in the cloud, then the files are
    downloaded over HTTPS into the save path. Downloads are tracked in a local state file
    since Real-Debrid has no tags to tell our torrents apart.
    """
    name = "Real-Debrid"

    # states during which the game can't be launched yet
    busy_states = ["queued", "adding", "magnet_conversion", "waiting_files_selection", "rd_queued",
                   "rd_downloading", "rd_compressing", "rd_uploading", "downloading", "paused", "waiting for connection"]

    def __init__(self, api_token, save_path):
        self.api_token = api_token
        self.save_path = save_path

        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_token}"

        self.connected = False
        self.last_check = 0
        self.check_lock = threading.Lock()

        self.state_path = f"/home/{getpass.getuser()}/.config/undertaker141/realdebrid.json"
        self.state_lock = threading.Lock()
        self.torrents = {}  # hash -> RDTorrent
        self.workers = {}  # hash -> (thread, stop event)

        self.check_connection()
        self.load_state()

    # ---- connection ----

    def check_connection(self, dt=None):
        try:
            user = self.request("GET", "/user")
            if user.get("type") != "premium":
                print("\n--# Real-Debrid account is not premium, torrents can't be downloaded. #--\n")
            self.connected = True
        except Exception as e:
            print(f"\n--# Please make sure your Real-Debrid API token is correct. ({e}) #--\n")
            self.connected = False
        self.last_check = time.time()

    def is_connected(self):
        # called every few seconds by every library card, so refresh in the background at most every 30s
        if time.time() - self.last_check > 30 and self.check_lock.acquire(blocking=False):
            self.last_check = time.time()

            def refresh():
                try:
                    self.check_connection()
                finally:
                    self.check_lock.release()
            threading.Thread(target=refresh, daemon=True).start()
        return self.connected

    def request(self, method, endpoint, **kwargs):
        response = self.session.request(method, API_URL + endpoint, timeout=15, **kwargs)
        if response.status_code >= 400:
            try:
                message = response.json().get("error", response.text)
            except ValueError:
                message = response.text
            raise RealDebridError(f"{response.status_code} {message}", response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # ---- same interface as JCQbt ----

    def get_torrents(self):
        return list(self.torrents.values())

    def get_torrent(self, url):
        return self.torrents.get(self.get_hash(url))

    def count(self):
        return len(self.torrents)

    def download(self, url):
        torrent_hash = self.get_hash(url)
        if torrent_hash in self.torrents:
            return
        name = self.safe_name(self.get_display_name(url) or torrent_hash)
        self.torrents[torrent_hash] = RDTorrent(url, name, os.path.join(self.save_path, name))
        self.save_state()
        self.start_worker(torrent_hash)

    def pause(self, url):
        torrent_hash = self.get_hash(url)
        torrent = self.torrents.get(torrent_hash)
        if torrent is None or torrent.state in ("completed", "error"):
            return
        with torrent.lock:
            self.stop_worker(torrent_hash)
            torrent.state = "paused"
            torrent.dlspeed = 0
            torrent.eta = INFINITE_ETA
        self.save_state()

    def resume(self, url):
        # also retries downloads that failed
        torrent_hash = self.get_hash(url)
        torrent = self.torrents.get(torrent_hash)
        if torrent is None or torrent.state == "completed":
            return
        with torrent.lock:
            torrent.state = "queued"
            torrent.error = None
        self.save_state()
        self.start_worker(torrent_hash)

    def delete(self, url, delete_files=False):
        torrent_hash = self.get_hash(url)
        torrent = self.torrents.pop(torrent_hash, None)
        if torrent is None:
            return
        self.save_state()
        with torrent.lock:
            worker = self.stop_worker(torrent_hash)
        self.workers.pop(torrent_hash, None)

        # wait for the worker to stop writing before removing anything, without blocking the UI
        def cleanup():
            if worker is not None:
                worker.join()
            if torrent.rd_id:
                try:
                    self.request("DELETE", f"/torrents/delete/{torrent.rd_id}")
                except Exception as e:
                    print(f"Could not delete {torrent.name} from Real-Debrid: {e}")
            if delete_files and os.path.isdir(torrent.content_path):
                shutil.rmtree(torrent.content_path, ignore_errors=True)
        threading.Thread(target=cleanup, daemon=True).start()

    # get torrent hash from magnet link
    def get_hash(self, url):
        return re.findall(r"magnet:\?xt=urn:btih:([a-zA-Z0-9]+)", url)[0].lower()

    # ---- workers ----

    def start_worker(self, torrent_hash):
        previous = self.workers.get(torrent_hash)
        if previous is not None and previous[0].is_alive() and not previous[1].is_set():
            return
        stop = threading.Event()
        thread = threading.Thread(target=self.worker, args=(torrent_hash, stop, previous and previous[0]), daemon=True)
        self.workers[torrent_hash] = (thread, stop)
        thread.start()

    def stop_worker(self, torrent_hash):
        # the worker entry is kept so the next worker can wait for this one to finish
        worker = self.workers.get(torrent_hash)
        if worker is None:
            return None
        worker[1].set()
        return worker[0]

    def update(self, torrent, stop, **fields):
        """
        Set fields of a torrent from a worker, ignored once the worker was stopped.
        """
        with torrent.lock:
            if stop.is_set():
                return False
            for key, value in fields.items():
                setattr(torrent, key, value)
            return True

    def worker(self, torrent_hash, stop, previous=None):
        # a paused worker may still be writing its last chunk to the same files
        if previous is not None:
            previous.join()

        torrent = self.torrents.get(torrent_hash)
        retry_delay = 5
        while torrent is not None and not stop.is_set():
            try:
                info = self.wait_for_cloud(torrent, stop)
                if info is not None:
                    self.download_files(torrent, info, stop)
                return
            except (requests.ConnectionError, requests.Timeout, RealDebridError) as e:
                if isinstance(e, RealDebridError) and not e.is_transient():
                    self.fail(torrent, stop, e)
                    return
                print(f"Real-Debrid connection error for {torrent.name}: {e}")
                self.update(torrent, stop, state="waiting for connection", dlspeed=0, eta=INFINITE_ETA)
                stop.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 120)
            except Exception as e:
                self.fail(torrent, stop, e)
                return

    def fail(self, torrent, stop, error):
        print(f"Real-Debrid download of {torrent.name} failed: {error}")
        if self.update(torrent, stop, state="error", error=str(error), dlspeed=0, eta=INFINITE_ETA):
            self.save_state()

    def wait_for_cloud(self, torrent, stop):
        """
        Add the magnet to Real-Debrid and wait until it's downloaded there, returns the torrent info.
        """
        if torrent.rd_id is None:
            self.update(torrent, stop, state="adding")
            rd_id = self.request("POST", "/torrents/addMagnet", data={"magnet": torrent.magnet_uri})["id"]
            # keep the id even if stopped meanwhile, so deleting removes it from Real-Debrid
            torrent.rd_id = rd_id
            self.save_state()

        while not stop.is_set():
            info = self.request("GET", f"/torrents/info/{torrent.rd_id}")
            status = info["status"]

            if info.get("filename") and status != "magnet_conversion":
                name = self.safe_name(info["filename"])
                if name != torrent.name and self.update(torrent, stop, name=name, content_path=os.path.join(self.save_path, name)):
                    self.save_state()

            if status == "downloaded":
                return info
            if status in ("magnet_error", "error", "virus", "dead"):
                raise RealDebridError(f"Real-Debrid reported status '{status}'")

            if status == "waiting_files_selection":
                self.request("POST", f"/torrents/selectFiles/{torrent.rd_id}", data={"files": "all"})
            state = status if status in ("magnet_conversion", "waiting_files_selection") else f"rd_{status}"

            progress = info.get("progress", 0) / 100
            speed = info.get("speed", 0) or 0
            remaining = info.get("bytes", 0) * (1 - progress)
            self.update(torrent, stop, state=state, progress=progress, dlspeed=speed,
                        eta=int(remaining / speed) if speed else INFINITE_ETA)
            stop.wait(5)
        return None

    def download_files(self, torrent, info, stop):
        """
        Unrestrict the Real-Debrid links of a torrent and download them into its content path.
        """
        files = [f for f in info["files"] if f["selected"]]
        links = info["links"]

        # file paths are relative to the torrent folder, drop the folder name in case they include it
        root = f"/{info.get('filename')}/"
        if files and all(f["path"].startswith(root) for f in files):
            for f in files:
                f["path"] = f["path"][len(root):]

        # Real-Debrid gives one link per selected file, unless it packed them into an archive
        if len(files) == len(links):
            targets = [(link, self.safe_path(torrent.content_path, f["path"]), f["bytes"]) for f, link in zip(files, links)]
        else:
            targets = [(link, None, None) for link in links]

        total = sum(size for _, _, size in targets if size) or info.get("bytes", 0)
        done = 0
        self.update(torrent, stop, state="downloading", progress=0.0)
        speed_window = (time.time(), 0)

        for link, path, size in targets:
            if stop.is_set():
                return
            unrestricted = self.request("POST", "/unrestrict/link", data={"link": link})
            if path is None:
                path = self.safe_path(torrent.content_path, unrestricted["filename"])
            size = unrestricted.get("filesize") or size

            os.makedirs(os.path.dirname(path), exist_ok=True)
            existing = os.path.getsize(path) if os.path.isfile(path) else 0
            if size and existing == size:
                done += size
                continue

            headers = {"Range": f"bytes={existing}-"} if existing else {}
            with requests.get(unrestricted["download"], headers=headers, stream=True, timeout=30) as response:
                response.raise_for_status()
                # the server ignored the range, start the file over
                if existing and response.status_code != 206:
                    existing = 0
                done += existing
                with open(path, "ab" if existing else "wb") as f:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if stop.is_set():
                            return
                        f.write(chunk)
                        done += len(chunk)

                        now = time.time()
                        if now - speed_window[0] >= 1:
                            speed = int((done - speed_window[1]) / (now - speed_window[0]))
                            speed_window = (now, done)
                            self.update(torrent, stop, progress=done / total if total else 0.0, dlspeed=speed,
                                        eta=int((total - done) / speed) if speed else INFINITE_ETA)

        if self.update(torrent, stop, state="completed", progress=1.0, dlspeed=0, eta=0):
            self.save_state()

    # ---- helpers ----

    def get_display_name(self, url):
        names = parse_qs(urlparse(url).query).get("dn")
        return names[0] if names else None

    def safe_name(self, name):
        name = name.replace("/", "_").replace("\0", "").strip()
        return name if name not in ("", ".", "..") else "download"

    def safe_path(self, base, relative):
        # torrent file paths come from the internet, never write outside the game folder
        parts = [p for p in relative.replace("\\", "/").split("/") if p not in ("", ".", "..")]
        if not parts:
            raise RealDebridError(f"Invalid file path '{relative}'")
        return os.path.join(base, *parts)

    def load_state(self):
        if not os.path.isfile(self.state_path):
            return
        with open(self.state_path) as f:
            data = json.load(f)
        for torrent_hash, entry in data.items():
            torrent = RDTorrent.from_dict(entry)
            self.torrents[torrent_hash] = torrent
            # continue downloads interrupted by closing the app
            if torrent.state not in ("completed", "error", "paused"):
                self.start_worker(torrent_hash)

    def save_state(self):
        with self.state_lock:
            data = {h: t.to_dict() for h, t in list(self.torrents.items())}
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            tmp_path = self.state_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.state_path)
