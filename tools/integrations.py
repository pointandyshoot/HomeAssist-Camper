#!/usr/bin/env python3
"""Install reviewed source commits; never publish their private runtime state."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from bluetti_patch import patch

PINS = {
    "bluetti": ("https://github.com/bluetti-official/bluetti-home-assistant.git",
                "v1.0.5", "f1df72b9642ebb60cb1c56100f2ad3c3a5b60157"),
    "bms_ble": ("https://github.com/patman15/BMS_BLE-HA.git",
                "2.17.0", "23ba216aea103220be2fc66ba3fe21092391219b"),
}


def install(name, config):
    target = config / "custom_components" / name
    if target.exists():
        print(f"Preserving existing {name}; updates require explicit backup/review (UPDATES.md)")
        return
    url, tag, sha = PINS[name]
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / "source"
        subprocess.run(["git", "clone", "--depth", "1", "--branch", tag, url, str(repo)], check=True)
        actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        if actual != sha:
            raise ValueError(f"{name} tag changed; refusing unreviewed source")
        component = repo / "custom_components" / name
        if name == "bluetti":
            patch(component)
        # Retain original upstream licence with downloaded component.
        shutil.copyfile(repo / "LICENSE", component / "UPSTREAM-LICENSE")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = target.with_name(name + ".installing")
        if stage.exists():
            shutil.rmtree(stage)
        shutil.copytree(component, stage)
        stage.rename(target)
    print(f"Installed {name} pinned to {sha[:12]}")


def audit(config):
    """Check critical provisioning artefacts without printing secrets/identifiers."""
    component = config / "custom_components/bluetti"
    issues = []
    if not component.exists():
        issues.append("BLUETTI custom integration missing")
    else:
        for relative, changes in __import__('bluetti_patch').CHANGES.items():
            content = (component / relative).read_text()
            if not all(new in content for _, new in changes):
                issues.append(f"Expected camper patch missing in {relative}")
        libs = list((component / "ble/lib").glob("*bluetti_ble_linux_aarch64_314_musl.so"))
        if not libs or not any(p.stat().st_size > 0 for p in libs):
            issues.append("ARM64/Python 3.14 musl BLE library not provisioned")
        deps = ["libcpsrt.so", "libmbedcrypto.so.3.6.4", "libmbedtls.so.3.6.4", "libmbedx509.so.3.6.4"]
        if not all((component / "ble/lib" / name).exists() for name in deps):
            issues.append("One or more ARM64 BLE dependency libraries missing")
        entries_file = config / ".storage/core.config_entries"
        if not entries_file.exists():
            issues.append("HA integration entries not provisioned")
        else:
            entries = json.loads(entries_file.read_text())["data"]["entries"]
            matched = [e for e in entries if e["domain"] == "bluetti"]
            selected = [p for e in matched for p in e.get("data", {}).get("products", [])
                        if p.get("sn") in e.get("options", {}).get("devices", [])]
            if not selected:
                issues.append("No selected BLUETTI device")
            for product in selected:
                if product.get("control_mode") != "bluetooth":
                    issues.append("A selected BLUETTI device is not in BLE mode")
                if not product.get("server_key"):
                    issues.append("A BLUETTI encryption key is missing")
                sn = product.get("sn", "")
                if not sn or Path(sn).name != sn:
                    issues.append("Unexpected protocol identifier")
                elif not (component / "downloads/proto" / (sn + ".bin")).exists():
                    issues.append("A selected device protocol file is missing")
    for issue in issues:
        print(issue)
    if issues:
        raise SystemExit(1)
    print("Critical local artefacts present. This does not prove device/key validity; perform offline cold-boot acceptance.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "audit"])
    parser.add_argument("--config", type=Path, default=Path("/opt/camper-ha/config"))
    args = parser.parse_args()
    if args.action == "install":
        for name in PINS:
            install(name, args.config)
    else:
        audit(args.config)
