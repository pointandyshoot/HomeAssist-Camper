#!/usr/bin/env bash
set -euo pipefail
free -m
swapon --show
df -h /opt/camper-ha
cat /sys/class/thermal/thermal_zone0/temp
docker compose --project-directory /opt/camper-ha ps --all
docker stats --no-stream
systemctl --no-pager status camper-network.service camper-dhcp.service || true
journalctl -k -b --no-pager -g 'oom|Out of memory|throttl' -n 20
