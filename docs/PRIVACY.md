# Public repository privacy policy

Real local files: ignored `.env`, `networking/config.json`, `homeassistant/secrets.yaml`; runtime `/opt/camper-ha` and `/etc/camper-ha` are outside the checkout. These contain device/account data and must never enter public Git history. `.storage`, native libraries/protocol files, databases, logs, backups, device identifiers, Wi-Fi secrets and MQTT credentials are private even when not conventionally called a password.

Examples have conspicuous fake credentials and no real device suffix/MAC/account/location. Generic `192.168.42.0/24`, fixed profile UUIDs, the project URL, hardware model names and the configurable Australian timezone are reproducible configuration, not personal identifiers. Tests use explicitly synthetic node numbers, key bytes and coordinates only.

Optional Meshtastic logging is disabled until commissioned. Real node IDs/keys go in root-only `/opt/camper-ha/config/camper_mesh.json` (ignored anywhere); private GPS/encounters live in `.storage/camper_mesh.sqlite`. No data is exported to publicly accessible `www`; the frontend code obtains history through authenticated HA. Coordinates/node identities, radio exports, route history and public-key ACLs must never enter Git, issues, screenshots or public backups. The finite retention and recorder exclusions are documented in MESHTASTIC.md. Treat a portable key compromise as a reason to revoke its ACL entry and replace/verify keys; rotate channel/Bluetooth secrets if exposed.

Before **every public commit**:

```sh
git status --short
python3 tools/validate.py
git diff --cached --check
git diff --cached
```

Run a recognised secret scanner as an additional check when available, then review the complete staged diff manually for personal names, network/device identifiers and location/account context. Automated patterns cannot prove absence of personal information. The CI validator catches common credential patterns and forbidden runtime paths; it is not an exhaustive detector.

Do not share raw integration diagnostics/logs or private backups in issues. A real credential committed once is compromised even if removed in a later commit: rotate it, revoke the applicable token/key/session and clean history under an explicit recovery plan. Never claim a later deletion revoked access. BLE identifiers aren't generally rotatable passwords but still require privacy handling.
