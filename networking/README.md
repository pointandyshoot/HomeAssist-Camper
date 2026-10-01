# Networking implementation

See [NETWORKING](../docs/NETWORKING.md) for timing, Android access and recovery. Credentials live only in ignored `config.json`, then root-only `/etc/camper-ha/network.json` and NM keyfiles. Example values are rejected by bootstrap.

`scripts/controller.py` contains the tested policy and bounded NM adapter; `scripts/provision.py` renders profiles safely without passwords in argv. systemd units supervise the controller, provide watchdog/exit recovery and run DHCP separately. Dnsmasq only leases the AP subnet; it does not offer a default gateway/DNS or perform NAT. The Wi-Fi interface is owned exclusively by this arrangement after reboot.
