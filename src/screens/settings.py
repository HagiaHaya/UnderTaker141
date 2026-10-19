from widgets.core import Plugin
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.scrollview import MDScrollView
from kivymd.toast.kivytoast.kivytoast import toast
from utils import get_settings, write_settings
import yaml
from database import Database
from threading import Thread
db = Database("games.db")

class Settings(Plugin):
    name = "Settings"
    icon = "cog"
    
    def __init__(self, qbt_client=None,**kwargs):
        super().__init__(**kwargs)
        self.settings_yaml = get_settings()
        # settings files created before Real-Debrid support lack these keys
        self.settings_yaml["general"].setdefault("download_client", "qbittorrent")
        self.settings_yaml.setdefault("realdebrid_api", {"api_token": ""})
        
        # scrollable, the settings don't fit on small screens
        self.scroll = MDScrollView()
        self.add_widget(self.scroll)
        self.layout = MDBoxLayout(orientation="vertical", padding="12dp", spacing="12dp", adaptive_height=True)
        self.scroll.add_widget(self.layout)
        
        
        # settings label
        self.settings_label = MDLabel(text="Settings", halign="left", font_style="H4", size_hint=(1, 0.1))
        self.layout.add_widget(self.settings_label)
        
        # general settings
        self.save_path = MDTextField(text=self.settings_yaml["general"]["save_path"], hint_text="Save path", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.save_path)
        
        # download client, qBittorrent or Real-Debrid
        self.client_row = MDBoxLayout(orientation="horizontal", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, None), height="48dp")
        self.client_row.add_widget(MDLabel(text="Use Real-Debrid instead of qBittorrent"))
        self.use_realdebrid = MDSwitch(pos_hint={"center_y": 0.5})
        # kivymd 1.1.1 crashes when active is passed to the constructor
        self.use_realdebrid.active = self.settings_yaml["general"]["download_client"] == "realdebrid"
        self.client_row.add_widget(self.use_realdebrid)
        self.layout.add_widget(self.client_row)
        
        # qBittorrent settings
        self.qbt_host = MDTextField(text=self.settings_yaml["qbittorrent_api"]["host"], hint_text="qBittorrent host", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.qbt_host)
        self.qbt_port = MDTextField(text=str(self.settings_yaml["qbittorrent_api"]["port"]), hint_text="qBittorrent port", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.qbt_port)
        self.qbt_username = MDTextField(text=self.settings_yaml["qbittorrent_api"]["username"], hint_text="qBittorrent username", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.qbt_username)
        self.qbt_password = MDTextField(text=self.settings_yaml["qbittorrent_api"]["password"], hint_text="qBittorrent password", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.qbt_password)
        
        # Real-Debrid settings
        self.rd_api_token = MDTextField(text=self.settings_yaml["realdebrid_api"]["api_token"], hint_text="Real-Debrid API token (real-debrid.com/apitoken)", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.rd_api_token)
        
        # igdb settings
        self.twitch_client_id = MDTextField(text=self.settings_yaml["igdb"]["twitch_client_id"], hint_text="Twitch client id", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.twitch_client_id)
        self.twitch_client_secret = MDTextField(text=self.settings_yaml["igdb"]["twitch_client_secret"], hint_text="Twitch client secret", pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.1))
        self.layout.add_widget(self.twitch_client_secret)
        
        # buttons
        self.save_btn = MDRaisedButton(text="Save",on_press=self.save_settings, pos_hint={"center_x": 0.5, "center_y": 0.5}, size_hint=(0.8, 0.00001))
        self.layout.add_widget(self.save_btn)
        
        # update database button, color red, text color black
        self.update_db_btn = MDRaisedButton(text="Update database",pos_hint={"center_x": 0.5, "center_y": 0.5}, md_bg_color="#ff0000", size_hint=(0.8, 0.00001), text_color=(0, 0, 0, 1))
        self.update_db_btn.bind(on_press=self.update_db)
        self.layout.add_widget(self.update_db_btn)
        
        # boxlayout as spacer
        self.layout.add_widget(MDBoxLayout(size_hint=(None, None), size=(1, 150)))
        
        # rows keep their own height so the layout can grow past the screen
        self.settings_label.adaptive_height = True
        for row in self.layout.children:
            row.size_hint_y = None
        
        
        
    def save_settings(self, instance):
        old_client = self.settings_yaml["general"]["download_client"]
        self.settings_yaml["general"]["save_path"] = self.save_path.text
        self.settings_yaml["general"]["download_client"] = "realdebrid" if self.use_realdebrid.active else "qbittorrent"
        self.settings_yaml["qbittorrent_api"]["host"] = self.qbt_host.text
        self.settings_yaml["qbittorrent_api"]["port"] = int(self.qbt_port.text)
        self.settings_yaml["qbittorrent_api"]["username"] = self.qbt_username.text
        self.settings_yaml["qbittorrent_api"]["password"] = self.qbt_password.text
        self.settings_yaml["realdebrid_api"]["api_token"] = self.rd_api_token.text.strip()
        self.settings_yaml["igdb"]["twitch_client_id"] = self.twitch_client_id.text
        self.settings_yaml["igdb"]["twitch_client_secret"] = self.twitch_client_secret.text
        
        write_settings(self.settings_yaml)
            
        self.settings_yaml = get_settings()
        
        if self.settings_yaml["general"]["download_client"] != old_client:
            toast("Restart UnderTaker141 to switch the download client", duration=3.0)
        
        
    def update_db(self, instance):
        instance.disabled = True

        t = Thread(target=self.update_db_helper, args={instance})
        t.start()
        
    def update_db_helper(self, instance):
        from utils import ReleasesFeed
        
        updater = ReleasesFeed(twitch_client_id=self.settings_yaml["igdb"]["twitch_client_id"], twitch_client_secret=self.settings_yaml["igdb"]["twitch_client_secret"], db_object=db)
        t = Thread(target=updater.pipeline)
        t.start()
        instance.text = "Database is being updated, please DO NOT close the application."
        t.join()
        instance.text = "Database update done"