# Troubleshooting and local recovery

## No Camper-HA WLAN

Wait for Pi boot. Power/radio/SD failure cannot be repaired by the controller. From any remaining SSH path inspect `systemctl status camper-network.service camper-dhcp.service`, journal, `nmcli device status`, `rfkill list`, Wi-Fi country/regulatory settings and profile presence. NM must own the configured interface. A missing/wrong AP password/profile requires re-running private provisioning. If entirely inaccessible, mount the SD on a trusted computer and correct `/etc/camper-ha/network.json`/NM profiles or restore the tested card image.

The controller retries AP activation; watchdog/ExecStopPost/rescue recover software failures. A rescue service failing because a driver cannot enter AP mode is a hardware/OS commissioning failure, not a successful fallback.

## AP connects but no address

Check `camper-dhcp.service` and `/etc/camper-ha/dnsmasq.conf`. This dedicated dnsmasq process uses DNS port 0 and supplies no router/DNS. Another existing DHCP server on the interface is a conflict. Only `.20`–`.100` are dynamically leased. Android should obtain a `192.168.42.x` address; direct HA IP is `.1`.

## Starlink trial never succeeds

Verify 2.4 GHz WPA2 SSID/password privately, not in a public issue. A visible SSID is insufficient. The controller needs DHCP, default gateway and an ARP response stable for 30 s. Inspect local profile/network status; no WAN connection is required. Backoff can reach an hour after repeated failures. Restart the controller to reset dwell/backoff (AP returns, first trial 10 minutes later).

## Hostname/app fails but IP works

Check Avahi, duplicate hostnames, Starlink multicast/client isolation and Android local network permissions. Follow NETWORKING.md's direct-IP/app fallback. HA access does not require an Internet gateway. If Android routes HTTP/mDNS through mobile data, temporarily disable mobile data to diagnose; its routing behaviour is outside the Pi's control.

## BLUETTI unavailable offline

Run `sudo python3 tools/integrations.py audit`. Check that every product uses Bluetooth Control, that patches remain installed, native libraries/protocol files are present, and that the vendor app is closed. Don't edit `.storage` manually while HA runs. Inspect logs privately for missing key/protocol/import/ABI errors. A rejected BLE key needs online reconfiguration; the cache patch cannot repair it. Missing voltage/temperature/cell entities are not automatically communication failures.

## BLE connections conflict

Close BLUETTI/SmartBat-Pro/Aranet apps; don't leave a second scan process running. Ensure host BlueZ and D-Bus are running and the Compose D-Bus bind/capabilities are intact. Keep default BMS polling and 30–60 s BLUETTI polling. Try placement away from metal/wiring/router; verify Wi-Fi traffic isn't excessive. Reboot after a deliberate kernel/firmware update and retest. Do not install a USB adapter to satisfy this project's baseline.

## HA slow, restarts or won't start

`sudo tools/health.sh`; check kernel OOM, `docker stats`, disk free space, zram and PSU throttling. HA can take minutes on this Pi. 512 MB is an acceptance risk; persistent memory exhaustion means the workload needs reduction or more RAM. Config checker instructions are in INSTALL.md. `docker compose logs --tail 100 homeassistant` can contain serials/keys/account details: keep it private and redact before sharing.

## Emergency manual WLAN recovery

To suspend camper management while using a previously saved OS WLAN:

```sh
sudo systemctl disable --now camper-network-rescue.timer
sudo systemctl stop camper-network.service
```

Stopping restores AP once. Then manually activate the desired original profile by UUID with `sudo nmcli connection up uuid <original-uuid>`. Restore saved original autoconnect flags from private `/etc/camper-ha/original-autoconnect.json` if retiring the camper controller. To resume, enable/start the rescue timer and start the controller. Don't delete the only working profile over SSH without a recovery route.
