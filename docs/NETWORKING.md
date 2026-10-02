# Single-radio networking

NetworkManager owns `wlan0`; no simultaneous AP/client interfaces, hostapd service or USB network adapter. The two profiles use fixed non-device UUIDs, private keyfiles and onboard 2.4 GHz Wi-Fi. The local AP is manual IPv4, **not NM shared mode**.

| State | Pi | Phone access | Next action |
|---|---|---|---|
| Boot/restart | Try Starlink immediately; retain an already-associated Starlink profile | Starlink LAN if viable; otherwise AP after bounded failure | No initial 600 s wait; same 30 s stability check |
| AP dwell | `192.168.42.1/24`; DHCP `.20`–`.100` | Direct local access | No scanning storm |
| Trial | AP disappears; NM attempts Starlink | Brief interruption | Association bounded to 45 s; process timeout 55 s |
| Stability check | DHCP IP + router responds to ARP | Starlink LAN | 30 s stable checks before promotion |
| Failed startup trial | Activate AP | Direct local access returns | First retry after 10 minutes |
| Failed later trial | Reactivate AP | Direct local access returns | Backoff 20, 40, then 60 minutes |
| Starlink | DHCP on Starlink LAN | Hostname or Starlink IP | No WAN probes; monitor local gateway |
| LAN failure | 60 s debounced loss | AP restored | New 10 minute dwell |

Each switch can take roughly 1–2 minutes including fallback association; these are software bounds, not measured radio performance. A full Starlink outage can include the 60 s loss delay. Gateway checks use ARP rather than ICMP/Internet, so a router that refuses ping can still be usable. DHCP and local router access do not prove phone client isolation is disabled; test phone→Pi on Starlink during commissioning.

On boot the controller issues a bounded NetworkManager association immediately, without relying on an SSID scan. If Starlink is absent, association fails and Camper-HA is restored. If Starlink is already associated when the controller starts, it checks that LAN in place instead of disconnecting it. A successful association must stay locally viable for `stability_seconds` (default 30); this remains distinct from Starlink Internet becoming available. Defaults for later AP probing/backoff remain 600/3600 seconds and can be set privately within the validated limits. Restarting the controller makes one immediate new trial.

We deliberately try a bounded association periodically even when an AP-mode scan would report no SSID. Some firmware cannot reliably scan while hosting an AP. This trades one short AP interruption per backoff period for eventual discovery without adding another radio. Merely seeing an SSID never promotes the connection. A short disappearance does not flip state immediately. Hidden SSIDs and unusual enterprise/WPA3-only WLANs are outside this initial configuration.

## Recovery layers

* `camper-activate.service` disables autoconnect for competing saved WLAN profiles, recording original flags privately. Profiles/files remain available for rollback.
* NM can autoconnect the AP itself; Starlink autoconnect is disabled so the controller owns promotion.
* The controller tries Starlink on every service start, restores AP on failure, retries failed AP activation, and uses bounded subprocess calls. systemd's 180 s watchdog kills a wedged loop. The 360 s startup timeout accommodates configured stability checks plus bounded AP recovery; it is not an intentional boot delay.
* `ExecStopPost` restores AP if the controller exits/crashes. An independent 60 s rescue timer retries AP activation while the controller is inactive/failed. It leaves an `activating` controller alone so it cannot interrupt the initial Starlink trial; the startup timeout/watchdog still bound that phase. A corrupted config can still recover through the already-installed AP profile.
* A blocked radio, driver failure, deleted profiles, failing SD card or power loss can still defeat software recovery. Keep fresh-card rebuild instructions/private backup available.

Commands (generic status only; device addresses in detailed diagnostics are private):

```sh
systemctl status camper-network.service camper-network-rescue.timer camper-dhcp.service
journalctl -u camper-network.service -b --no-pager
nmcli -g GENERAL.STATE,GENERAL.CONNECTION device show wlan0
ip -4 address show dev wlan0
```

To force local access and suspend future trials:

```sh
sudo systemctl stop camper-network.service
sudo python3 /usr/local/lib/camper-ha/controller.py --force-ap
```

Stopping invokes AP restoration too. The rescue timer keeps this AP available. To resume: `sudo systemctl start camper-network.service`. Changes to WPA credentials require editing private `/etc/camper-ha/network.json`, running `sudo python3 /usr/local/lib/camper-ha/provision.py`, then restarting the controller; this disconnects clients.

## Android Home Assistant app

1. Pair the Companion app with `http://homeassistant.local:8123`. Avahi advertises the same hostname in both modes (set by installer). Enable the usual Android local network permissions when requested.
2. Leave remote/external URL unconfigured unless separately provisioned. If asked for connection security, trust only your own local network; do not publish an HTTP URL externally.
3. Test both networks **with mobile data enabled**. `.local` resolution varies by Android/WebView/app routing and router multicast behaviour. The hostname may be renamed to `homeassistant-2.local` if another host already owns it; resolve collisions at commissioning.
4. If mDNS fails, use browser `http://192.168.42.1:8123` in AP mode, and `http://<Pi-Starlink-IP>:8123` in Starlink mode. Find/set the Starlink DHCP lease if the router supports it. In the app's Settings → Companion app → server connection settings, change the local/Home Assistant URL to the reachable address. Names/options can vary by app version.
5. Some Companion versions support internal URL selection by Wi-Fi SSID. This requires Android's permission to read the SSID and only helps if both URLs are correct. A single working hostname is simpler; this project does not promise automatic two-IP selection on every app version.

The AP supplies **no DHCP router option and no DNS option** and runs no DNS proxy/NAT. Android can keep mobile data as its Internet path while using the WLAN for local access, but behaviour is device/version dependent. If Android warns "no Internet", choose to stay connected. Disable automatic switching away from this WLAN if needed. If the app chooses the cellular route for local HTTP, use the browser or temporarily disable mobile data to diagnose it. Neither mDNS nor mobile-data coexistence is claimed tested.

HA itself does not depend on the phone's Internet choice. BLE recording continues through AP/STA transitions while the container remains running. Network outages do not deliberately restart HA or BlueZ.
