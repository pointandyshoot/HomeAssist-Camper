#!/usr/bin/env bash
# Stop HA for a coherent SQLite + config snapshot. Destination must be off the Pi.
set -euo pipefail
umask 077
if [[ $EUID -ne 0 || $# -ne 1 ]]; then
  echo 'Usage: sudo tools/backup.sh /mounted-private-destination/camper-backup.tar.gz' >&2
  exit 2
fi
dest=$(realpath -m -- "$1")
case "$dest" in
  /opt/camper-ha/*|/etc/camper-ha/*) echo 'Choose a separate private backup destination.' >&2; exit 2 ;;
esac
if [[ -e "$dest" ]]; then
  echo 'Destination already exists; refusing to overwrite it.' >&2
  exit 2
fi
running=$(docker compose --project-directory /opt/camper-ha ps --status running --services)
resume() {
  if [[ "$running" == *homeassistant* ]]; then
    docker compose --project-directory /opt/camper-ha up -d --pull never
  fi
}
trap resume EXIT
docker compose --project-directory /opt/camper-ha stop -t 90 homeassistant
swap_paths=()
for path in etc/rpi/swap.conf etc/rpi/swap.conf.d etc/default/zramswap; do
  if [[ -e "/$path" ]]; then
    swap_paths+=("$path")
  fi
done
tar --acls --xattrs -czf "$dest" -C / \
  opt/camper-ha etc/camper-ha etc/NetworkManager/system-connections \
  etc/sysctl.d/90-camper-local.conf "${swap_paths[@]}"
chmod 600 "$dest"
echo 'Private backup created. Encrypt it and copy it off the microSD; never commit it.'
