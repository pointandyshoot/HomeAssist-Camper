# Dashboard and entity mapping

The mobile YAML **Camper** dashboard is the default at `/lovelace`: battery and CO₂ gauges, BLUETTI input/output/runtime and confirmed AC/DC buttons, SmartBat read-only readings, environment/history, a Mesh tab and Pi health. It uses built-in cards plus one small local mesh card with no external fonts, map tiles or chart service. It works offline once the HA frontend has loaded. Actual driver IDs contain serial numbers or BLE suffixes, so the project uses generic aliases.

Fresh installations get the default automatically. Existing HA users/app shortcuts may retain a previously selected dashboard: open `/lovelace`, select Camper in your profile/sidebar or change your app's saved path. For existing deployments, use UPDATES.md's migration instructions; bootstrap preserves existing YAML. The fridge section is an explanatory placeholder: no absent sensor/receiver is needed to load the dashboard. Unsupported live sensor rows remain unavailable until commissioning, never fabricated zeros.

After integration setup, open Settings → Devices & services → entity → settings and change **entity ID** to the corresponding generic ID. Confirm the source and units, not just similar names. Do not rename hardware or post a real entity registry to GitHub. Battery/environment sensors are retained by the Recorder's sensor include, even if not in this table. Mesh history is kept separately and privately; see MESHTASTIC.md for recorder exclusions.

| Verified source | Generic entity ID |
|---|---|
| BLUETTI SOC | `sensor.camper_bluetti_soc` |
| BLUETTI grid/AC input power (W) | `sensor.camper_bluetti_ac_input` |
| BLUETTI PV/DC input power (W) | `sensor.camper_bluetti_dc_input` |
| BLUETTI AC output power (W) | `sensor.camper_bluetti_ac_output` |
| BLUETTI DC output power (W) | `sensor.camper_bluetti_dc_output` |
| Remaining discharge time (native duration units) | `sensor.camper_bluetti_runtime` |
| Remaining charge time | `sensor.camper_bluetti_charge_time` |
| BLUETTI AC output switch | `switch.camper_bluetti_ac` |
| BLUETTI DC output switch | `switch.camper_bluetti_dc` |
| SmartBat SOC | `sensor.camper_smartbat_soc` |
| SmartBat voltage/current/power | `sensor.camper_smartbat_voltage`, `sensor.camper_smartbat_current`, `sensor.camper_smartbat_power` |
| SmartBat reported temperature | `sensor.camper_smartbat_temperature` |
| SmartBat cycles | `sensor.camper_smartbat_cycles` |
| SmartBat stored energy, if present | `sensor.camper_smartbat_capacity` |
| Aranet CO₂ | `sensor.camper_co2` |
| Aranet temperature/humidity/pressure | `sensor.camper_temperature`, `sensor.camper_humidity`, `sensor.camper_pressure` |
| Aranet battery | `sensor.camper_aranet_battery` |

Remove unsupported rows from the **private runtime** dashboard rather than inventing substitute measurements. The type-A cell-spread note is intentional. If a later verified driver supplies cells, add the real delta entity and cell details to the private dashboard.

The calculated BLUETTI net value is **input power minus output power**, not direct battery power: internal conversion losses/idle consumption are not measured. Positive means more incoming than outgoing terminal power. Availability checks prevent absent input readings from turning into fabricated zero. SmartBat trend uses a ±0.2 A deadband and the verified current sign convention.

The graph view supplies overnight SOC and CO₂ context. Daily DC-input energy, nightly AC/DC consumption, CO₂ min/max and threshold durations were considered but deferred: these require verified source units, gap handling and explicit time windows. When adding them, use native Integral/Utility Meter/statistics/history_stats helpers and name DC input truthfully (vehicle charging is not solar). Do not integrate unavailable readings as zero or carry stale power through a disconnected interval.

To review changes without overriding your configuration: compare repository YAML with `/opt/camper-ha/config`, back up, edit deliberately, run HA's config checker, then restart. Don't copy `.storage` between public and private areas.
