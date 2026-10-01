#!/usr/bin/env python3
"""Idempotent dedicated-Pi bootstrap; no arbitrary remote install scripts."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "networking/scripts"))
from controller import read_config  # noqa: E402

RUNTIME = Path("/opt/camper-ha")


def run(*args):
    subprocess.run(args, check=True)


def copy_missing(source, destination, mode=0o600):
    destination = Path(destination)
    if destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Publish atomically without overwriting, including concurrent reruns. A
    # failed/interrupted write must not leave an empty 'existing' secrets file.
    import tempfile
    content = Path(source).read_bytes()
    fd, name = tempfile.mkstemp(prefix=".camper-install-", dir=destination.parent)
    temp = Path(name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, destination)
        except FileExistsError:
            return False
        return True
    finally:
        temp.unlink(missing_ok=True)


def validate_inputs():
    read_config(ROOT / "networking/config.json")
    path = ROOT / ".env"
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    import re
    if not re.fullmatch(r"ghcr.io/home-assistant/home-assistant:(\d{4}\.\d{1,2}\.\d+)", values.get("HA_IMAGE", "")):
        raise ValueError("HA_IMAGE must be an explicit HA release tag")
    if not (ROOT / "homeassistant/secrets.yaml").exists():
        raise ValueError("Copy homeassistant/secrets.example.yaml to secrets.yaml")


def install_docker():
    if shutil.which("docker"):
        run("docker", "compose", "version")
        return  # Never upgrade an existing Docker install in bootstrap.
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    codename = release.get("VERSION_CODENAME", "").strip('"')
    if codename not in ("bookworm", "trixie"):
        raise ValueError("Review Docker OS support before installing on this release")
    run("apt-get", "install", "-y", "--no-install-recommends", "ca-certificates", "curl", "gnupg")
    Path("/etc/apt/keyrings").mkdir(exist_ok=True)
    run("curl", "-fsSL", "https://download.docker.com/linux/debian/gpg", "-o", "/etc/apt/keyrings/docker.asc")
    output = subprocess.check_output(["gpg", "--show-keys", "--with-colons", "/etc/apt/keyrings/docker.asc"], text=True)
    if "9DC858229FC7DD38854AE2D88D81803C0EBFCD88" not in output:
        raise ValueError("Docker signing-key fingerprint changed; review upstream")
    Path("/etc/apt/keyrings/docker.asc").chmod(0o644)
    Path("/etc/apt/sources.list.d/camper-docker.sources").write_text(
        f"Types: deb\nURIs: https://download.docker.com/linux/debian\nSuites: {codename}\n"
        "Components: stable\nArchitectures: arm64\nSigned-By: /etc/apt/keyrings/docker.asc\n")
    run("apt-get", "update")
    run("apt-get", "install", "-y", "--no-install-recommends", "docker-ce", "docker-ce-cli",
        "containerd.io", "docker-compose-plugin")


def configure_swap():
    # Current Pi OS has rpi-swap. Never start a second zram manager on zram0.
    if Path("/etc/rpi/swap.conf").exists():
        folder = Path("/etc/rpi/swap.conf.d")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "90-camper.conf").write_text("[Main]\nMechanism=zram\n[Zram]\nRamMultiplier=0.5\nMaxSizeMiB=256\n")
        print("Configured native rpi-swap pure zram; takes effect at reboot.")
    else:
        if Path("/etc/systemd/zram-generator.conf").exists():
            raise ValueError("Existing zram-generator policy; review it before adding zram-tools")
        run("apt-get", "install", "-y", "--no-install-recommends", "zram-tools")
        Path("/etc/default/zramswap").write_text("ALGO=lz4\nPERCENT=50\nPRIORITY=100\n")
        run("systemctl", "enable", "zramswap.service")
        # Start on reboot: avoid swapoff/reconfiguration under install-time pressure.
    if Path("/etc/dphys-swapfile").exists():
        run("systemctl", "disable", "dphys-swapfile.service")


def main():
    validate_inputs()  # Fail before making any system changes, never echo secrets.
    if "--check" in sys.argv:
        print("Local inputs valid; no system changes made.")
        return
    if os.geteuid() != 0 or platform.machine() != "aarch64":
        raise ValueError("Run with sudo on Raspberry Pi OS Lite 64-bit (aarch64)")
    model = Path("/proc/device-tree/model")
    if not model.exists() or "Raspberry Pi" not in model.read_text():
        raise ValueError("Bootstrap is intended for a dedicated Raspberry Pi")
    run("apt-get", "update")
    run("apt-get", "install", "-y", "--no-install-recommends", "network-manager", "bluez", "dbus-broker",
        "avahi-daemon", "dnsmasq-base", "iputils-arping", "git", "python3", "python3-yaml", "rfkill", "iw")
    install_docker()
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    RUNTIME.chmod(0o700)
    Path("/etc/camper-ha").mkdir(exist_ok=True, mode=0o700)
    copy_missing(ROOT / "networking/config.json", "/etc/camper-ha/network.json")
    copy_missing(ROOT / ".env", RUNTIME / ".env")
    config = RUNTIME / "config"
    config.mkdir(exist_ok=True, mode=0o700)
    for source in (ROOT / "homeassistant").rglob("*.yaml"):
        if source.name.endswith("example.yaml"):
            continue
        copy_missing(source, config / source.relative_to(ROOT / "homeassistant"))
    # Examples are copied only once; all auth/.storage/config lives outside git.
    copy_missing(ROOT / "docker-compose.yml", RUNTIME / "docker-compose.yml")
    lib = Path("/usr/local/lib/camper-ha")
    lib.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "networking/scripts").glob("*.py"):
        shutil.copyfile(source, lib / source.name)
        (lib / source.name).chmod(0o644)
    for source in (ROOT / "networking/systemd").glob("*"):
        shutil.copyfile(source, Path("/etc/systemd/system") / source.name)
    for name in ("camper-metrics.service", "camper-metrics.timer"):
        shutil.copyfile(ROOT / "tools" / name, Path("/etc/systemd/system") / name)
    shutil.copyfile(ROOT / "tools/metrics.py", lib / "metrics.py")
    Path("/etc/tmpfiles.d/camper-ha.conf").write_text(
        "d /run/camper-ha 0755 root root -\nd /run/camper-ha-dhcp 0750 dnsmasq nogroup -\n")
    run("systemd-tmpfiles", "--create", "/etc/tmpfiles.d/camper-ha.conf")
    run("python3", str(lib / "provision.py"))
    # DHCP manual mode must never turn this Pi into the phone's Internet router.
    Path("/etc/sysctl.d/90-camper-local.conf").write_text("net.ipv4.ip_forward=0\nnet.ipv6.conf.all.forwarding=0\n")
    # Docker may enable forwarding; DHCP deliberately offers no gateway regardless.
    configure_swap()
    # No unattended package changes while travelling; only on a dedicated Pi.
    for service in ("apt-daily.timer", "apt-daily-upgrade.timer"):
        run("systemctl", "disable", "--now", service)
    if Path("/lib/systemd/system/unattended-upgrades.service").exists():
        run("systemctl", "disable", "--now", "unattended-upgrades.service")
    run("hostnamectl", "set-hostname", "homeassistant")
    run("systemctl", "enable", "NetworkManager.service")
    run("systemctl", "enable", "--now", "bluetooth.service", "avahi-daemon.service", "docker.service")
    run("python3", str(ROOT / "tools/integrations.py"), "install")
    os.chdir(RUNTIME)
    run("docker", "compose", "config", "--quiet")
    run("docker", "compose", "pull")
    run("docker", "compose", "up", "-d", "--pull", "never")
    run("systemctl", "daemon-reload")
    # Enable only: keep the install-time Wi-Fi/SSH alive until the deliberate reboot.
    run("systemctl", "enable", "camper-activate.service", "camper-network.service", "camper-dhcp.service",
        "camper-network-rescue.timer", "camper-metrics.timer")
    print("Installed. Reboot to start AP fallback/network management. Existing private files were preserved.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        sys.exit("Bootstrap failed. Check local inputs, supported OS and preceding command status. Secrets hidden; rerun safely.")
