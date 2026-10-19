# UnderTaker141

This project is for educational purposes only, do not use it against any law or to harm anyone, I am not responsible for any misuse of this project.

<img src="https://i.imgur.com/mGkRVa2.jpg">

<h1 align="center">UnderTaker141 (very creative name)</h1>

UnderTaker is a free and open source game center and [qBittorrent](https://github.com/qbittorrent/qBittorrent) client for Linux, UnderTaker141 fetches all the repacks uploaded by [johncena141](https://1337x.to/user/johncena141/) on 1337x, then fetches their summary and cover art from [IGDB](igdb.com) and displayes them in a "nice" UI :3.

Just download the game and run it! Everything is pre-configured for you, thanks to johncena141's repacks! <br />

# IMPORTANT
- Please read [johncena141's guide](https://gitlab.com/jc141x/setup/-/tree/main) to understand more about how their repacks work, and double check the dependencies for their repacks.
- If you are using a VPN, do not forget to set the network interface in qBittorent to your VPN interface.
- Instead of qBittorrent you can download through [Real-Debrid](https://real-debrid.com) (premium account required), no torrent client needed.

# Dependencies
- [AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher)
- Latest qBittorent with WebUI enabled (not needed when using Real-Debrid)
- All the dependencies for johncena141's repacks (check their [guide](https://gitlab.com/jc141x/setup/-/blob/main/README.md))

# Installation
- Download the latest release from [here](https://github.com/AbdelrhmanNile/UnderTaker141/releases)
- Run the AppImage and enjoy!

# Extra Steps for Steam Deck

- To edit the read-only image ([details](https://help.steampowered.com/en/faqs/view/671A-4453-E8D2-323C)):

```
passwd # to set a password
sudo steamos-readonly disable
```
- Install compatible version of DwarFS:
```
git clone https://aur.archlinux.org/dwarfs-bin.git
makepkg -si
```

# Configuration
After you run the AppImage, head to the settings tab.

## qBittorent
- Enter your qBittorent WebUI host (default is localhost)
- Enter your qBittorent WebUI port (default is 8080)
- Enter your qBittorent WebUI username (default is admin)
- Enter your qBittorent WebUI password (default is adminadmin)

## Real-Debrid (optional, instead of qBittorrent)
- Turn on "Use Real-Debrid instead of qBittorrent"
- Enter your Real-Debrid API token, you can find it [here](https://real-debrid.com/apitoken)
- Click save and restart UnderTaker141

Games are added to Real-Debrid, downloaded there, then downloaded over HTTPS into your save path. Pause stops the local download and resume continues it, unfinished downloads also continue when you restart the app. Deleting a game also removes it from your Real-Debrid torrents.

## IGDB
- Create a Twitch API app and get a client ID and from [here](https://dev.twitch.tv/console/apps/create)

# Updating the database
To update the database and fetch new releases by johncena141, head to the settings tab and click on the "update database" button. This will take a few minutes and will freeze the app (and might freeze your system), just wait until it finishes and everything will return to normal.
