# Meshtastic: local camper radio, GPS and AC commands

One **Seeed SenseCAP T1000-E** stays in the camper, connected over onboard BLE to HA. The other two connect to their respective Android phones and send direct messages over LoRa. Starlink, MQTT and the Pi's USB port are not involved. HA Wi-Fi access still works as documented in NETWORKING.md. Mesh range/delivery is variable; it is an additional access method.

The installer fetches **meshtastic/home-assistant v0.6.1**, verifies full SHA `b641e747c17dc03aec3ef4d020b6573bff3d71d1`, retains its licence and applies `tools/meshtastic_patch.py`. A small authored `camper_mesh` companion uses that integration's raw packet events. We do not implement another BLE protocol or open a second BLE connection. Missing/disabled configuration or an absent radio leaves HA running; AC mesh control is disabled initially.

## Commission the three radios

1. Use compatible current stable Meshtastic firmware on all three. Configure the correct LoRa region, same modem preset and your chosen channel settings using the phone app. Save a **private** radio configuration/key backup. Modern authenticated PKI direct messages are required for commands; legacy shared-channel encryption is insufficient. Do not configure the HA automation as a remote-admin key or expose BMS settings.
2. Give the camper radio continuous independent power and an adequate GPS view. Use a normal client role with Bluetooth/GPS enabled; avoid sleep policies which break its persistent BLE connection. Begin with position updates around 2–5 minutes and telemetry around 5 minutes, respecting airtime limits. Determine actual GPS-update behaviour and reception in the camper during commissioning.
3. Record each node's numeric/`!xxxxxxxx` ID and each portable radio's **32-byte public key, encoded in base64**, locally. Verify keys directly in your possession using the app's security settings or an exported radio configuration, rather than trusting an overheard name, ID or new key advertisement. Never publish exports, real IDs, keys, channels or BLE addresses. Replacing/resetting a radio/key requires a deliberate private ACL update.
4. Configure the camper radio with the Android app first, then disconnect/close that app's BLE connection. In HA, Settings → Devices & services → Add integration → **Meshtastic**, choose **Bluetooth**, and select the camper T1000-E. The dedicated radio should have one active BLE client, the Pi. Keep the other two radios paired to their phones. Linux pairing may require `sudo bluetoothctl`, `agent KeyboardDisplay`, `default-agent`, then `pair` and `trust` with the address shown locally and the radio's configured pairing PIN. Do this privately; do not post terminal captures. Do not assume a default PIN is suitable.
5. Select only the camper and two portable nodes for upstream HA entities. Set node notifications to **None** (or only selected nodes), disable channel notifications, leave **web client** and **TCP proxy** disabled. The upstream web client is unauthenticated when enabled. Do not add every passing node as HA entities: the companion's bounded history handles them. Leave radio MQTT/proxy-to-client features disabled for this local deployment.
6. Edit the installed **root-only** `/opt/camper-ha/config/camper_mesh.json`. It starts as [the disabled example](../meshtastic/config.example.json). Replace gateway/portable IDs and verified keys, set `enabled: true`, and restart HA. An empty `authorised_radios` list permits logging without command access. Missing or malformed configuration produces a visible status without failing HA; details/values are never logged.
7. Rename verified BLUETTI entities as in DASHBOARD.md, or update the private mesh entity mapping. From each portable device, send **a direct message to the camper node** containing `status`. Group-channel messages and other radios are rejected. Status includes SOC, total terminal input/output and AC state; stale/unsupported values say unavailable.
8. Test offline status from both radios. Only after confirming independent Pi power, actual BLE control and the rejection tests below, set both `ac_control_enabled` and `independent_pi_power_confirmed` to `true`, then restart HA. Keep DC/BMS configuration controls absent.

## Commands and protection

| Direct message | Behaviour |
|---|---|
| `status` | Fresh BLUETTI SOC, terminal input/output and AC state |
| `help` | Available command syntax |
| `ac on` / `ac off` | Returns `confirm TOKEN` challenge; changes no output yet |
| `confirm TOKEN` | Same authorised radio, within 90 seconds; sets explicit AC state once |

Only packets from the configured BLE gateway, addressed to it, with firmware **`pkiEncrypted=true` and matching `publicKey`** are accepted. Sender ID/name alone is never authority. MQTT-originated packets are rejected. Firmware supplies these fields after authenticated PKI decryption; if your firmware/client stops exposing them, commands fail closed. Replies explicitly force PKI and require the destination's currently known key to match the private pin; there is no shared-channel fallback.

Confirmation tokens are random, temporary and consumed before control. Restart/disconnection loses pending confirmations. Persistent packet replay guards, per-radio response limiting and a bounded command queue avoid repeat actions. Delayed requests can only create a new challenge; an old confirmation cannot execute after its 90-second window. No toggle, arbitrary service, DC or BMS command is accepted. This is application policy layered over Meshtastic PKI, not a replacement for it.

A fresh HA switch reading (default within 180 seconds) is required before sending AC control. A reply stating **observed in HA** means the configured entity subsequently reported that state; radio acknowledgement alone does not prove output power. A timeout means check locally; there is no automatic retry. Verify the entity mapping against the actual AC socket before enabling remote control. Never power the Pi from an output it may switch off.

## Private GPS and encounter history

The **Mesh** dashboard tab lists radios by latest reception, highlights repeated encounters and provides an offline coordinate overview with selectable radio/session locations. Blue lines show the camper's sampled route. It uses a small locally served card and an authenticated HA response service; no map tiles, CDN, cloud tracker or `/www` data export is needed.

Only live raw radio packets count as receptions; startup node caches do not. A new encounter requires a reception gap exceeding **30 minutes**. Counts identify radio IDs, not people. Relayed nodes can be far away; the interface explicitly marks direct versus relayed/unknown. Advertised names, IDs and remote positions are unverified claims for history, even though command keys are verified separately. A renamed/reset radio and radio ID collisions can affect matching.

Each encounter retains the camper's fresh GPS position **when it received a packet**, separately from a remote radio's reported coordinate, measurement time and precision bits. Missing/stale/future coordinates do not produce a new pin. Own GPS requires a fresh POSITION_APP with `LOC_INTERNAL`; fixed coordinates aren't claimed as a GPS fix. Check this metadata with your actual T1000 firmware before relying on route recording. Coarse position sharing remains coarse; displayed decimals do not increase accuracy.

Storage is private `/config/.storage/camper_mesh.sqlite`, 0600, included in private backups. A node is aggregated at most once per minute, own route at most once per minute; reception samples are not exact RF packet totals. Default retention is **90 days**, configurable 1–365; caps are 1,000 nodes, 20,000 encounter rows, 100,000 route samples and 10,000 replay records. Hourly pruning and incremental vacuum bound growth. The card shows up to 200 recent rows/route points; the HA `camper_mesh.history` response service permits at most 500. It isn't a full-resolution trip GIS or a claim of nearby travellers.

Mesh summary/upstream `sensor.meshtastic_*` entities are excluded from Recorder; companion coordinates are never entity attributes. Review upstream renamed sensor IDs and recorder exclusions before enabling additional mesh sensors. Device trackers are outside the Recorder's included domains. Upstream integration storage, `.storage`, backups and pairing data are private too. Disable debug packet logging. Deleting this SQLite file while HA is stopped resets the history/replay store; do not do so casually during control tests.

## Offline time and recovery

The Pi Zero 2 W has no battery-backed RTC. Accurate history requires an accurate Pi clock after an offline cold boot. Network time can resume with Starlink; verify `timedatectl` and date before relying on GPS chronology. This release **does not set the host clock from mesh GPS**. A stale host clock rejects future GPS fixes and may affect other sensor/history times. Preserve this limit until a verified GPS-time synchronisation or RTC solution is added.

Our upstream patch suppresses automatic host time/timezone writes to the radio so a stale Pi clock cannot corrupt its GPS time. It also removes a cosmetic Internet hardware-name lookup and pins Python dependencies to the reviewed HA release (including protobuf 6.32.0 and aiomqtt 2.5.0). Initial dependency downloads/firmware provisioning need Internet. Normal BLE reception, history, dashboard and PKI commands use local services; offline stock-container **recreation** still needs provisioned dependencies, as described in UPDATES.md.

Radio loss shows **Radio unavailable**, keeps history readable and leaves HA/BLUETTI/Aranet/SmartBat functioning. Upstream handles BLE reconnect; reselect/pair privately if needed. T1000's extra persistent BLE connection increases coexistence/RAM load: the combined 24-hour Pi test is mandatory. GPS duty cycle also affects the T1000 battery. Don't enable frequent traceroute, neighbour discovery or telemetry requests just to populate the dashboard.

## Sources and acceptance

Reviewed upstream source and primary documentation on 2 October 2026:

* [Meshtastic HA integration and configuration](https://github.com/meshtastic/home-assistant/tree/v0.6.1)
* [Meshtastic encryption: authenticated PKI direct messages versus channels](https://meshtastic.org/docs/overview/encryption/)
* [Firmware Router: authenticated receive metadata and requested destination-key enforcement](https://github.com/meshtastic/firmware/blob/master/src/mesh/Router.cpp)
* [Firmware AdminModule public-key checks](https://github.com/meshtastic/firmware/blob/master/src/modules/AdminModule.cpp)
* [Seeed T1000-E documentation](https://wiki.seeedstudio.com/sensecap_t1000_e/)
* [Meshtastic position configuration](https://meshtastic.org/docs/configuration/radio/position/)

Software checks cover policy, bounded history, actual vendored protobuf/secure-send construction, HA adapter/service operation, missing configuration and absent SDR composition. Real BLE pairing/reconnect, T1000 firmware PKI metadata, LoRa delivery/range, GPS source/precision, actual AC switching and four-device BLE coexistence are **not hardware-tested**. Use TESTING.md's mesh acceptance checklist before enabling AC commands while travelling. ADS-B remains deferred and installs no service.
