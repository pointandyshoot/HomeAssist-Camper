#!/usr/bin/env python3
"""Single-radio NetworkManager controller. No secrets in arguments or logs."""
import argparse
import json
import logging
import os
import re
import socket
import subprocess
import time

AP = "2fbc64af-5a8e-4473-a32c-16b21ed635a1"
STA = "cda9aab1-59d9-41a2-b8ea-2c080f1d22b8"
DEFAULT_CONFIG = "/etc/camper-ha/network.json"
LOG = logging.getLogger("camper-network")


def read_config(path=DEFAULT_CONFIG):
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    if not isinstance(cfg, dict):
        raise ValueError("Network config must be an object")
    interface = cfg.get("interface", "")
    if not isinstance(interface, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", interface):
        raise ValueError("Invalid Wi-Fi interface")
    for key in ("starlink_ssid", "ap_ssid"):
        value = cfg.get(key, "")
        if not isinstance(value, str) or not 1 <= len(value.encode()) <= 32 or any(ord(c) < 32 for c in value):
            raise ValueError(f"Invalid {key}")
        if value.startswith("EXAMPLE-"):
            raise ValueError(f"Replace example {key}")
    for key in ("starlink_password", "ap_password"):
        value = cfg.get(key, "")
        if not isinstance(value, str) or not 8 <= len(value) <= 63 or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError(f"{key} needs an 8–63 character ASCII WPA password")
        if value.startswith("REPLACE-"):
            raise ValueError(f"Replace example {key}")
    if cfg["ap_ssid"] == cfg["starlink_ssid"]:
        raise ValueError("AP and Starlink SSIDs must differ")
    for key, default, lower, upper in (
        ("ap_channel", 6, 1, 11), ("probe_interval", 600, 300, 3600),
        ("maximum_backoff", 3600, 600, 7200), ("stability_seconds", 30, 30, 120),
        ("loss_seconds", 60, 30, 300), ("tick_seconds", 15, 5, 30),
    ):
        value = cfg.setdefault(key, default)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"Invalid {key}")
    if cfg["maximum_backoff"] < cfg["probe_interval"]:
        raise ValueError("maximum_backoff must be >= probe_interval")
    return cfg


def command(*args, timeout=10):
    try:
        result = subprocess.run(args, timeout=timeout, capture_output=True, text=True, check=False)
        return result.returncode == 0, result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return False, ""


class Network:
    def __init__(self, interface):
        self.interface = interface

    def active(self):
        ok, output = command("nmcli", "-g", "GENERAL.CON-UUID", "device", "show", self.interface)
        return output if ok else ""

    def up(self, uuid):
        command("nmcli", "radio", "wifi", "on")
        command("nmcli", "device", "set", self.interface, "managed", "yes")
        ok, _ = command("nmcli", "--wait", "45", "connection", "up", "uuid", uuid,
                        "ifname", self.interface, timeout=55)
        return ok and self.active() == uuid

    def viable(self):
        # WAN reachability is irrelevant. Verify DHCP + local layer-2 gateway.
        if self.active() != STA:
            return False
        ok, output = command("ip", "-j", "-4", "address", "show", "dev", self.interface)
        try:
            ips = [a["local"] for d in json.loads(output) for a in d.get("addr_info", [])
                   if a.get("scope") == "global"] if ok else []
            if not ips or any(ip.startswith("169.254.") for ip in ips):
                return False
            ok, output = command("ip", "-j", "-4", "route", "show", "default", "dev", self.interface)
            gateways = [r["gateway"] for r in json.loads(output) if "gateway" in r] if ok else []
        except (ValueError, KeyError, TypeError):
            return False
        if not gateways:
            return False
        ok, _ = command("arping", "-I", self.interface, "-c", "1", "-w", "3", gateways[0], timeout=5)
        return ok


def notify(message):
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), address)
    except OSError:
        pass


class Controller:
    def __init__(self, cfg, network, clock=time.monotonic, sleeper=time.sleep, heartbeat=notify):
        self.cfg, self.network = cfg, network
        self.clock, self.sleep, self.heartbeat = clock, sleeper, heartbeat
        self.state = "AP"
        self.backoff = cfg["probe_interval"]
        self.next_probe = 0
        self.lost_since = None

    def fallback(self):
        self.state = "AP"
        self.lost_since = None
        self.next_probe = self.clock() + self.backoff
        LOG.info("Restoring local access point")
        if not self.network.up(AP):
            LOG.error("AP activation failed; retrying next tick (check radio/regulatory settings)")
            return False
        return True

    def trial(self, *, startup=False):
        LOG.info("Bounded Starlink association trial; local AP temporarily unavailable")
        self.heartbeat("WATCHDOG=1")
        # A controller restart must not tear down an already-associated Starlink
        # profile. It still has to pass the same local-LAN stability checks.
        associated = startup and self.network.active() == STA
        if associated or self.network.up(STA):
            deadline = self.clock() + self.cfg["stability_seconds"]
            while True:
                self.heartbeat("WATCHDOG=1")
                if not self.network.viable():
                    break
                if self.clock() >= deadline:
                    self.state = "STARLINK"
                    self.lost_since = None
                    self.backoff = self.cfg["probe_interval"]
                    LOG.info("Starlink LAN confirmed stable")
                    return True
                self.sleep(self.cfg["tick_seconds"])
        # A failed first boot attempt gets the normal AP dwell, not an immediate
        # doubled delay. Subsequent failed trials retain exponential backoff.
        if not startup:
            self.backoff = min(self.backoff * 2, self.cfg["maximum_backoff"])
        self.heartbeat("WATCHDOG=1")
        self.fallback()
        return False

    def startup(self):
        LOG.info("Trying Starlink immediately at controller startup")
        return self.trial(startup=True)

    def step(self):
        self.heartbeat("WATCHDOG=1")
        if self.state == "AP":
            if self.network.active() != AP:
                self.fallback()
            elif self.clock() >= self.next_probe:
                self.trial()
        elif self.network.viable():
            self.lost_since = None
        else:
            if self.lost_since is None:
                self.lost_since = self.clock()
            if self.clock() - self.lost_since >= self.cfg["loss_seconds"]:
                self.fallback()

    def run(self):
        self.startup()  # One bounded Starlink trial, then AP if it is unusable.
        self.heartbeat("READY=1")
        while True:
            self.step()
            self.sleep(self.cfg["tick_seconds"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--rescue", action="store_true")
    parser.add_argument("--force-ap", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        cfg = read_config(args.config)
    except (ValueError, KeyError, OSError):
        if not (args.rescue or args.force_ap):
            raise SystemExit("Invalid local network config; recovery will use installed AP profile")
        ok, interface = command("nmcli", "-g", "connection.interface-name", "connection", "show", "uuid", AP)
        if not ok or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", interface):
            raise SystemExit("No installed AP recovery profile; repair configuration from SD card")
        cfg = {"interface": interface}
    network = Network(cfg["interface"])
    if args.rescue:
        ok, state = command("systemctl", "show", "--property=ActiveState", "--value",
                            "camper-network.service")
        # Type=notify is 'activating' during the initial association/stability
        # trial. The watchdog/start timeout bound it; don't race that trial.
        if ok and state in ("active", "activating", "reloading"):
            return
        if network.active() == AP:
            return
    if args.rescue or args.force_ap:
        if not network.up(AP):
            raise SystemExit("Local AP recovery failed; rescue timer will retry")
    else:
        Controller(cfg, network).run()


if __name__ == "__main__":
    main()
