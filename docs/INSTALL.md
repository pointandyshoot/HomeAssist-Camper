# Installation

## Before starting

Use a dedicated Pi Zero **2** W (not original Zero W), a good 32 GB or larger high-endurance microSD, stable 5 V power and current Raspberry Pi OS Lite **64-bit**. Keep the OTG USB port free. Set Wi-Fi country in Imager, enable SSH with your own account/key and provision an initial usable 2.4 GHz WLAN. Do not commit Imager credentials. The initial install needs Internet; routine collection later does not.

The installer manages this host's WLAN profiles and disables unattended APT timers. It sets the host name to `homeassistant`, creates zram and disables `dphys-swapfile` if present. Use it on a dedicated camper Pi. Take an existing private backup before rerunning it on an established system.

## Bootstrap

```sh
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/pointandyshoot/HomeAssist-Camper.git
cd HomeAssist-Camper
cp .env.example .env
cp networking/config.example.json networking/config.json
cp homeassistant/secrets.example.yaml homeassistant/secrets.yaml
chmod 600 .env networking/config.json homeassistant/secrets.yaml
nano networking/config.json
python3 tools/install.py --check
sudo ./tools/bootstrap.sh
sudo reboot
```

Use real local Starlink credentials and a unique strong AP password in **networking/config.json only**. The examples are deliberately rejected until replaced. This version supports WPA2 PSK (8–63 ASCII characters), 2.4 GHz, nonempty broadcast SSIDs. AP and Starlink SSIDs must differ. Adjust AP channel 1–11 for local interference if useful. Do not change subnet without also changing DHCP/addressing/documentation.

`.env` holds an explicit HA release and timezone. Never use `latest/stable` for travel deployments. `secrets.yaml` initially contains just the timezone; real device pairing credentials are entered through HA UI and stored privately in `.storage`.

The installer validates inputs before system changes, installs signed APT packages and source-pinned custom integrations, creates profiles without showing passwords in command arguments, starts HA, and **enables** network services for the next boot. It avoids restarting NetworkManager or activating WLAN profiles during the SSH session. `nmcli connection reload` reads profiles without intentionally dropping the current connection.

Existing `/opt/camper-ha/.env`, HA YAML, secrets and `/etc/camper-ha/network.json` are preserved. Existing custom components are preserved. Repeated bootstrap is recovery/provisioning, not configuration synchronisation; use [UPDATES](UPDATES.md) for deliberate changes. Full host idempotency still requires hardware testing.

## First HA start

Allow up to 10 minutes on this small Pi. On `Camper-HA`, open `http://192.168.42.1:8123`. On Starlink, try `http://homeassistant.local:8123`, or find the Pi's DHCP address in the router/Starlink device list. Create the HA owner account locally. Do not configure cloud remote access for basic operation. Browser HTTP is local; WLAN encryption protects the radio link but local LAN clients can reach HA, so use a strong HA password.

The controller tries Starlink immediately at boot. It requires DHCP/router access stable for 30 seconds, then stays on Starlink; Internet is not required. If association or stability fails, it creates Camper-HA and retries after 10 minutes, with backoff for subsequent failures. A controller restart also makes an immediate bounded Starlink trial. See NETWORKING.md for timing/recovery and UPDATES.md for updating an older installation.

In Settings → Devices & services:

1. Confirm Bluetooth detects the onboard adapter.
2. Add **BLUETTI**, perform OAuth while online, bind/select Elite 200 V2 and choose **Bluetooth Control**. Use 30 or 60 s polling, default timeout/retries. See BLUETTI.md for mandatory cache audit.
3. Add native **Aranet** after enabling its Smart Home setting.
4. Add **BLE Battery Management System**. Select the locally discovered SmartBat device; confirm Offgridtec/OGT detection. No BMS controls should exist.
5. Map/rename entities using DASHBOARD.md. Camper is the default `/lovelace` dashboard; update previously saved phone shortcuts if needed.
6. Optionally add Meshtastic over **Bluetooth** for the dedicated T1000-E. Follow MESHTASTIC.md to verify and privately authorise your other two radios. The root-only mesh example is already installed disabled; real keys/IDs go only in `/opt/camper-ha/config/camper_mesh.json`.

No SDR needs to be attached: there is no USB device mapping, rtl_433 service or MQTT dependency. The future fridge placeholder remains visible. ADS-B is deferred.

HA may download integration Python requirements during first setup. Keep Starlink available until all integrations have loaded and supplied real data. Backup the private config afterwards, then perform the offline cold-boot/reload checks in TESTING.md.

## Host resource readiness

```sh
sudo ./tools/health.sh
sudo python3 tools/integrations.py audit
cd /opt/camper-ha
sudo docker compose exec homeassistant python -m homeassistant --script check_config --config /config
```

Initial dependency downloads and image unpacking can be slow. If HA OOMs or the Pi becomes unresponsive, the 512 MB workload has failed acceptance; use RESOURCES.md. Do not hide persistent OOMs with SD-backed swap.
