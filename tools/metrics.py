#!/usr/bin/env python3
"""Cheap host metrics; HA container reads a single JSON file once a minute."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0])
    disk = shutil.disk_usage('/opt/camper-ha')
    temperature = Path('/sys/class/thermal/thermal_zone0/temp')
    try:
        result = subprocess.run(['docker', 'compose', '--project-directory', '/opt/camper-ha',
                                 'ps', '--all', '--format', 'json'], timeout=15, check=True,
                                capture_output=True, text=True)
        # Compose versions emit JSON lines or a JSON array.
        content = result.stdout.strip()
        items = json.loads(content) if content.startswith('[') else [json.loads(x) for x in content.splitlines()]
        health = next((x.get('Health') or x.get('State', 'unknown') for x in items
                       if x.get('Service') == 'homeassistant'), 'absent')
    except (ValueError, OSError, subprocess.SubprocessError):
        health = 'unknown'
    data = {
        'memory_percent': round(100 * (1 - memory['MemAvailable'] / memory['MemTotal']), 1),
        'load_per_core': round(os.getloadavg()[0] / (os.cpu_count() or 1), 2),
        'disk_percent': round(disk.used / disk.total * 100, 1),
        'cpu_temperature': round(int(temperature.read_text()) / 1000, 1) if temperature.exists() else None,
        'ha_health': health,
        'sampled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    folder = Path('/run/camper-ha')
    folder.mkdir(exist_ok=True)
    temp = folder / 'metrics.json.tmp'
    temp.write_text(json.dumps(data))
    temp.chmod(0o644)
    temp.replace(folder / 'metrics.json')


if __name__ == '__main__':
    main()
