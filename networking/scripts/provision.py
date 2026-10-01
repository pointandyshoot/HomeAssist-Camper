#!/usr/bin/env python3
"""Write NM keyfiles without exposing WPA secrets in process lists."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from controller import AP, STA, DEFAULT_CONFIG, read_config


def escaped(value):
    # GLib KeyFile string escaping; leading/trailing spaces matter in SSIDs/PSKs.
    return value.replace("\\", "\\\\").replace(" ", "\\s")


def profiles(cfg):
    interface = cfg["interface"]
    ap = f"""[connection]
id=camper-ap
uuid={AP}
type=wifi
interface-name={interface}
autoconnect=true
autoconnect-priority=100

[wifi]
mode=ap
band=bg
channel={cfg['ap_channel']}
ssid={escaped(cfg['ap_ssid'])}
powersave=2

[wifi-security]
key-mgmt=wpa-psk
proto=rsn;
pairwise=ccmp;
group=ccmp;
psk={escaped(cfg['ap_password'])}

[ipv4]
method=manual
address1=192.168.42.1/24
never-default=true

[ipv6]
method=disabled
"""
    sta = f"""[connection]
id=camper-starlink
uuid={STA}
type=wifi
interface-name={interface}
autoconnect=false

[wifi]
mode=infrastructure
band=bg
ssid={escaped(cfg['starlink_ssid'])}
powersave=2

[wifi-security]
key-mgmt=wpa-psk
psk={escaped(cfg['starlink_password'])}

[ipv4]
method=auto
may-fail=false

[ipv6]
method=disabled
"""
    return {"camper-ap.nmconnection": ap, "camper-starlink.nmconnection": sta}


def dhcp_config(cfg):
    return f"""# Dedicated process; not NetworkManager shared mode. No DNS, router or NAT.
port=0
user=dnsmasq
group=nogroup
interface={cfg['interface']}
bind-dynamic
dhcp-range=192.168.42.20,192.168.42.100,255.255.255.0,12h
dhcp-option=3
dhcp-option=6
dhcp-authoritative
dhcp-leasefile=/run/camper-ha-dhcp/leases
"""


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    # Create before writing, so sensitive contents are never world-readable.
    import os
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value)
    temp.replace(path)
    path.chmod(0o600)


def activate(cfg):
    # Disable other saved WLANs so NM cannot race the single-radio controller.
    # Keep their files and original autoconnect setting for manual recovery.
    backup = Path("/etc/camper-ha/original-autoconnect.json")
    original = json.loads(backup.read_text()) if backup.exists() else {}
    result = subprocess.run(["nmcli", "-g", "UUID", "connection", "show"],
                            capture_output=True, text=True, check=True, timeout=15)
    for uuid in result.stdout.splitlines():
        if uuid in (AP, STA):
            continue
        def field(name):
            return subprocess.run(["nmcli", "-g", name, "connection", "show", "uuid", uuid],
                                  capture_output=True, text=True, check=True, timeout=15).stdout.strip()
        if field("connection.type") != "802-11-wireless":
            continue
        bound = field("connection.interface-name")
        if bound not in ("", "--", cfg["interface"]):
            continue
        original.setdefault(uuid, field("connection.autoconnect"))
        write_private(backup, json.dumps(original, indent=2) + "\n")
        subprocess.run(["nmcli", "connection", "modify", "uuid", uuid,
                        "connection.autoconnect", "no"], check=True, timeout=15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    cfg = read_config(args.config)
    if args.activate:
        activate(cfg)
        return
    for name, value in profiles(cfg).items():
        write_private(Path("/etc/NetworkManager/system-connections") / name, value)
    write_private("/etc/camper-ha/dnsmasq.conf", dhcp_config(cfg))
    subprocess.run(["nmcli", "connection", "reload"], check=True, timeout=15)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        sys.exit("Network provisioning failed; check local config and NetworkManager (values hidden)")
