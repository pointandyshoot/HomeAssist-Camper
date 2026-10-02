# Camper Home Assistant

A reproducible local camper monitor for Raspberry Pi Zero 2 W, Raspberry Pi OS Lite **64-bit**, onboard Wi-Fi/BLE and Home Assistant Container. The USB OTG port stays available for a future RTL-SDR.

**Status: implemented and software-validated; physical commissioning required.** 512 MB RAM is below Home Assistant's recommended hardware. ARM64 compatibility does not prove that this workload fits: complete the [acceptance checklist](docs/TESTING.md) before relying on it while travelling. No physical Pi or batteries were available during development.

## Start here

1. Flash current Raspberry Pi OS Lite 64-bit with Raspberry Pi Imager. Set Wi-Fi country, an initial Wi-Fi connection and SSH credentials/key.
2. SSH in, then:

   ```sh
   git clone https://github.com/pointandyshoot/HomeAssist-Camper.git
   cd HomeAssist-Camper
   cp .env.example .env
   cp networking/config.example.json networking/config.json
   cp homeassistant/secrets.example.yaml homeassistant/secrets.yaml
   nano networking/config.json
   sudo ./tools/bootstrap.sh
   sudo reboot
   ```

3. Join `Camper-HA` with your chosen password. Open **http://192.168.42.1:8123** or **http://homeassistant.local:8123** and create your local HA account.
4. With Internet available, commission BLUETTI in **Bluetooth Control** mode, native Aranet and BLE Battery Management System. Follow [INSTALL](docs/INSTALL.md), [BLUETTI](docs/BLUETTI.md), [ARANET](docs/ARANET.md) and [SMARTBAT](docs/SMARTBAT.md).
5. Rename verified integration entities to the dashboard's generic IDs; absent/unsupported sensors remain unavailable. The Camper dashboard is the default at `/lovelace`.
6. Optionally pair the dedicated T1000-E over BLE and privately authorise your two portable radios: [MESHTASTIC](docs/MESHTASTIC.md). Mesh status, confirmed AC commands, camper GPS and repeat encounters work locally. Run the offline reboot test.

The installer preserves existing local files and runs downloads while the initial SSH network is still connected. Network switching starts **after reboot**. Never put real credentials or identifiers in tracked files.

## What runs

* Home Assistant with local SQLite: 7 days of detailed history, 30 s commit interval, automatic purge/repack; statistics may persist longer.
* Host BlueZ/D-Bus, NetworkManager, Avahi and DHCP-only dnsmasq.
* A bounded Python network controller supervised by systemd, plus an independent rescue timer.
* Official BLUETTI v1.0.5 with small [offline patches](docs/BLUETTI.md); read-only BMS_BLE-HA 2.17.0; native Aranet.
* Pinned Meshtastic v0.6.1 and a small HA companion, disabled until configured. Private bounded GPS/encounter SQLite; no additional daemon or BLE client.

No MQTT or automation servers beyond HA are installed. No unattended updates. AC/DC dashboard controls are deliberate manual actions; optional mesh AC commands require verified keys and confirmation. **No SDR is required or started**: fridge sensors and ADS-B remain future work.

## Network behaviour

On boot, `Camper-HA` is the safe fallback. Every 10 minutes (backing off to 60 minutes after failures), the single radio briefly leaves AP mode to try the configured 2.4 GHz Starlink WLAN. Successful association, DHCP and 30 s of local gateway reachability are required. A failed trial recreates the AP. Loss of a previously working LAN for 60 s also recreates it. WAN outages alone do not cause switching.

There is **no AP/client concurrency and no NAT**. The local WLAN deliberately supplies no Internet gateway or DNS server. Android mobile data and `.local` behaviour still depend on the phone/app; direct-IP recovery is always documented. See [NETWORKING](docs/NETWORKING.md).

## Operations

* [Installation](docs/INSTALL.md) · [research and version pins](docs/RESEARCH.md)
* [Dashboard/entity mapping](docs/DASHBOARD.md) · [resource limits](docs/RESOURCES.md)
* [Meshtastic/GPS/authorised commands](docs/MESHTASTIC.md)
* [Updates/rollback](docs/UPDATES.md) · [backup/rebuild](docs/BACKUP-RESTORE.md)
* [Troubleshooting](docs/TROUBLESHOOTING.md) · [future rtl_433](docs/RTL433.md)
* [Test results and hardware checklist](docs/TESTING.md) · [privacy](docs/PRIVACY.md)

Run `python3 tools/validate.py` and `python3 -m unittest discover -s tests -v` before changing/publicising configuration. Run `sudo tools/health.sh` on the Pi for resource and container status. See the docs for HA's own configuration checker and ShellCheck.
