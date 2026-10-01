# Explicit updates and rollback

Update while Starlink is stable, not just before needing the system offline. Nothing here schedules application updates. The installer disables dedicated-host unattended APT timers; you remain responsible for deliberate security updates.

## Before every update

Create a private backup using BACKUP-RESTORE.md, inspect free disk/RAM, record the current container image ID/digest and preserve a known good image. A database migration can make the new DB incompatible with the old HA; rollback means **old image plus matching pre-update config/database**, not merely changing the image tag. Test all three integrations and offline reboot afterwards.

## Raspberry Pi OS

```sh
sudo apt-get update
apt list --upgradable
sudo apt-get full-upgrade
sudo reboot
```

This may update kernel, BLE/Wi-Fi firmware, NetworkManager and Docker if its APT repository is configured. Review the proposed transaction. If you need separate Docker scheduling, use `apt-mark hold docker-ce docker-ce-cli containerd.io docker-compose-plugin` and unhold them for an explicit Docker update. Package downgrades are not a dependable OS rollback; keep a pre-update card image/spare card.

## Docker

Review [Docker's Debian instructions](https://docs.docker.com/engine/install/debian/). List versions with `apt-cache policy docker-ce docker-ce-cli containerd.io docker-compose-plugin`; install selected versions explicitly. Existing `docker.io` is a separate distribution package; don't mix it with Docker CE without reviewing the migration. Bootstrap never silently replaces an existing Docker installation. Runtime `.env` and HA config remain separate from Docker upgrades.

## Home Assistant

1. Read release notes, especially Python/architecture and custom integration compatibility.
2. Edit **private** `/opt/camper-ha/.env` to a reviewed exact release; keep the old file in private backup.
3. Run from `/opt/camper-ha`:

   ```sh
   sudo docker compose config --quiet
   sudo docker compose pull
   sudo docker compose stop -t 90 homeassistant
   sudo docker compose run --rm --no-deps homeassistant python -m homeassistant --script check_config --config /config
   sudo docker compose up -d --pull never
   ```

4. Give the new container Internet during first start. **Custom integration Python requirements install into the container's writable layer**, so recreation may require downloads even when BLE files/config are backed up. It is distinct from an offline reboot of the same provisioned container.
5. Native BLUETTI libraries are Python/libc/architecture-specific. Provision any changed ABI online. The cache patch does not reuse a differently named ABI library; don't rename an old `.so` to pretend compatibility.
6. Audit caches, test controls, take a fresh private backup/snapshot, then perform offline restart/cold-boot testing.

HA's healthcheck marks readiness; an unhealthy container is not automatically restarted. Inspect logs and resource usage instead of installing a restart loop that masks failures.

## Custom integrations

Version pins in `tools/integrations.py` are intentional. No HACS auto-updates. For a new upstream version, review the source/release, update its tag **and full SHA**, re-evaluate the BLUETTI patch anchors, run tests and privacy review. Do not force a patch onto unrelated code.

On the Pi: back up first, stop HA, move the existing component to a private directory **outside `custom_components`**, then run `sudo python3 tools/integrations.py install`. It skips other existing components. Preserve the old BLUETTI `ble/lib` native files and `downloads/proto` in backup; only restore caches after confirming ABI/protocol/version compatibility. Restart online and reprovision as needed. Never copy private protocol/key paths back into Git.

## Repository configuration

`git pull --ff-only` updates the public templates/tools, not runtime YAML/secrets. Compare files, back up, copy selected non-secret changes to `/opt/camper-ha/config` and run HA's checker. Rerun bootstrap only to deploy reviewed host scripts/units; it intentionally preserves existing runtime YAML/Compose/.env and custom integrations. Copy a revised Compose file deliberately after backup.

Network/controller updates must preserve AP/STA UUIDs or explicitly migrate keyfiles. After copying reviewed services/scripts, `sudo systemctl daemon-reload` and restart the controller; this briefly drops network access and returns to AP dwell.

## Rollback

Stop HA. Restore the full matching `/opt/camper-ha` private snapshot, including DB and old custom components. Restore the recorded old image (or private provisioned image snapshot), then `docker compose up -d --pull never`. Restore network JSON/keyfiles and old host scripts/units if these changed, reload NM profiles/units, then reboot. Never overwrite current databases without first preserving a private failure snapshot for diagnosis.
