# BLUETTI Elite 200 V2

## Selected driver and scope

Use vendor-maintained [bluetti-official/bluetti-home-assistant v1.0.5](https://github.com/bluetti-official/bluetti-home-assistant/releases/tag/v1.0.5), installed as a custom component without requiring HACS. Its model table lists Elite 200 V2 BLE, SOC, AC/DC output switches, PV/DC input, grid/AC input and AC/DC output power. Remaining-time entities appear in its BLE protocol handling but the actual firmware's advertised entity set must be checked.

Battery voltage and temperatures are **not guaranteed** by the model table. The source contains a placeholder `battery_voltage` property using random data; never use it or derive a real battery reading from it. The supplied dashboard deliberately omits voltage/temperature estimates. Only map a genuine measured entity with validated units if exposed by your firmware. Keep all genuine upstream sensors enabled/recorded where useful, even if they are not on the main dashboard.

## Provision online, operate over BLE

Initial setup needs an online BLUETTI account, device bound to that account, OAuth authorisation, the cloud's device encryption key and protocol binary, and the vendor's platform BLE/dependency libraries. The pinned image uses ARM64/musl/Python 3.14. The vendor's release notes mark this binary platform physically untested; it must import and communicate successfully on the Pi before acceptance.

Choose **Bluetooth Control**, never Cloud Control, for every selected camper device. The BLE path calls the device reader for telemetry and commands; it does not send AC/DC writes via the cloud when that device is configured BLE. OAuth access-token expiry is distinct from BLE encryption-key validity. A BLE key can be rejected/expire according to the driver, so uninterrupted indefinite offline control cannot be certified from source alone.

## Local lifecycle patches

`tools/bluetti_patch.py` applies exact source substitutions to the verified v1.0.5 SHA. Any unexpected source change aborts installation. Upstream files are downloaded to a private runtime directory, with their original MIT licence retained. No native library/protocol binary is committed.

| Patch | Why |
|---|---|
| Cached library before network checksum lookup | Cold offline startup uses the existing ELF file and does not silently replace it. Only a missing library follows upstream download/provisioning. |
| Preserve protocol downloads at unload/removal | Integration reload, HA shutdown and offline reboot must not erase required protocol files. Removal also preserves cache; securely delete private remnants manually when retiring hardware. |
| Skip OAuth refresh scheduler for BLE-only selections | Avoid cloud refresh/reload activity during normal local operation. Mixed/cloud entries retain upstream behaviour; they are outside the camper's local guarantee. |
| Parenthesise BLE/missing-key condition | Keep missing-key retrieval scoped to BLE products. Actual key rejection/reprovisioning still follows upstream logic. |

These changes do **not** bypass encryption, invent keys, extend key lifetime, change BLE protocol or guarantee the vendor's service will always remain available for provisioning. For a missing/rejected key, restore Starlink, use the vendor integration's reconfigure/pairing flow and perform offline tests again. Firmware updates may alter validity/protocol; do them deliberately with a backup.

The upstream loader still downloads missing dependencies, and HA may fetch Python requirements on initial setup. All such files must be installed while online and retained in private backup. After HA updates change Python/libc ABI, provision the correct new native library online and repeat the cold-boot tests.

## Commissioning

1. Power the Pi independently of any output you intend to switch off. Turning off the Pi's own supply removes all remote control. No software can wake a fully powered-down station unless its hardware keeps a BLE control path alive.
2. Enable Bluetooth on the station. Close the BLUETTI phone app while HA is connecting (the station may limit simultaneous sessions).
3. In HA → Settings → Devices & services → BLUETTI, authorise online and select Elite 200 V2 / Bluetooth Control. Use 30–60 s polling. Keep default timeout/retries initially; a long timeout may delay entity recovery.
4. Check genuine SOC, AC input, DC input and outputs against the front panel under known loads. DC input can be vehicle charging: do not label all DC energy as solar unless it actually is solar.
5. Use deliberate AC/DC switching with a safe test load. Return to desired output state manually. There are no battery output automations in this project.
6. Run `sudo python3 tools/integrations.py audit` from the repository. This checks key/config/cache presence without printing identifiers. It is an artefact check, not proof of valid encryption keys or installed Python dependencies.
7. Switch Starlink off, confirm AP access and live readings, then restart HA, reload the integration and cold-boot the Pi **while Starlink remains off**. Repeat after OAuth expiry and during an extended offline stay. Log commands and results privately, not public diagnostics containing serials/keys.

If any offline restart/control test fails, this requirement is not met yet. Keep local front-panel/app control available and diagnose cache/key/native-library errors. Do not report the system as travel-ready just because cloud-mode readings worked once.
