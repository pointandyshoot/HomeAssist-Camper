# Backup and rebuild

The public repository reproduces code/templates. It does not protect local pairing, encryption keys, HA users/history or Wi-Fi passwords. Store a private copy away from the microSD after commissioning and before each update. Syncthing can transfer a **completed backup archive**; do not sync a live SQLite DB and expect transactional consistency.

## Coherent private backup

Mount a private destination with enough space, then:

```sh
sudo tools/backup.sh /mounted-private-destination/camper-backup.tar.gz
```

The script refuses existing destinations, stops HA cleanly for SQLite consistency, archives `/opt/camper-ha` (config/.storage/history/custom components/secrets/Compose/.env), `/etc/camper-ha`, NM keyfiles, the installed native rpi-swap or zram-tools policy, and local-forwarding configuration, then restarts HA if it was previously running. Database collection has a short gap while HA is stopped. It does not stop Wi-Fi control or DHCP.

The archive is plaintext with restrictive permissions, **not encryption**. Encrypt it on a trusted machine/storage using your existing backup encryption tool (for example age/GPG), store recovery keys separately, verify extraction periodically and delete unwanted plaintext copies. Do not put backups, diagnostic logs or Docker images in this public repo. A backup on the same SD card is not protection against storage loss.

## Offline-capable container snapshot

Normal offline Pi reboot reuses the provisioned container's Python packages. A **new/recreated** stock HA container may need Internet for custom integration requirements. YAML backup alone does not preserve the writable container layer. After successful commissioning, optionally retain a private Docker snapshot for offline rebuild:

```sh
cd /opt/camper-ha
sudo docker compose stop -t 90 homeassistant
container_id=$(sudo docker compose ps --all --quiet homeassistant)
sudo docker commit "$container_id" camper-ha-provisioned:known-good
sudo docker image save -o /mounted-private-destination/camper-ha-image.tar camper-ha-provisioned:known-good
sudo chmod 600 /mounted-private-destination/camper-ha-image.tar
sudo docker compose up -d --pull never
```

Mounted `/config` is not included by Docker commit, so **both** config backup and image archive are needed. Images are large and private; encrypt/copy off-card. Keep date/version/architecture notes privately and check that `docker image load` succeeds on a compatible ARM64 host. A full microSD image is the simplest fully offline recovery (OS/packages/firmware, config and Docker together); keep a spare tested card. Neither stock image save alone nor Docker commit alone is a full backup.

## Fresh card with Internet available

1. Flash the same/current supported OS Lite 64-bit with your private SSH/initial Wi-Fi settings.
2. Clone this repo, copy/edit local examples and bootstrap as in INSTALL.md.
3. Stop HA and network controller (AP restoration runs). Extract your trusted private backup into a temporary private directory for inspection. Copy the matching `/opt/camper-ha` and `/etc/camper-ha` back; preserve root ownership/permissions. Do not merge new and old SQLite databases.
4. Restore the desired NM keyfiles. Run `sudo python3 /usr/local/lib/camper-ha/provision.py` and `sudo systemctl daemon-reload`. New hardware MACs may differ; the profiles bind by interface, not device MAC.
5. Pull the **matching** pinned HA image while online, or load the private provisioned image and set `HA_IMAGE=camper-ha-provisioned:known-good` in **runtime** `/opt/camper-ha/.env`. Use `docker compose up -d --pull never`; give a recreated stock image Internet for dependency installation.
6. Reboot. Confirm AP fallback, all sensors, actual AC/DC control and preserved history. Audit BLUETTI artefacts and repeat offline acceptance. A different BLE adapter/device firmware may need pairing/key renewal online.

## Fresh card without Internet

Use a tested full-card image/spare card. An archive plus public repo is not by itself a completely offline installer: OS APT packages, Docker image and custom integration requirements must already be available. This limitation is explicit; don't discover it at camp after the only SD has failed.

Store private `dpkg-query -W`, OS version, HA image ID/digest and a copy of the public repo commit reference with each backup. Test recovery on another card before deleting an older known good backup.

Meshtastic: the same stopped-HA backup includes private `config/camper_mesh.json`, `.storage/camper_mesh.sqlite`, both custom components, local card code and upstream node storage. Also keep private firmware/radio configuration exports and independently verified public-key pins for all three T1000-E devices off-card. After restore, validate the camper BLE pairing and both portable key pins; do not re-enable AC control until authenticated offline status/control and stale-value rejection are confirmed. Pending AC confirmations deliberately do not survive a restart/restore.
