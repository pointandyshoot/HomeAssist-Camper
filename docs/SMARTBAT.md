# SmartBat / SmartBat-Pro

The supplied advertising family `SmartBat-A…` is matched by the [Offgridtec Smart Pro driver](https://github.com/patman15/aiobmsble/blob/0.28.0/aiobmsble/bms/ogt_bms.py) used by [BMS_BLE-HA 2.17.0](https://github.com/patman15/BMS_BLE-HA/tree/2.17.0). The actual suffix/MAC stays private. Discovery also needs connectable service `0000fff0-0000-1000-8000-00805f9b34fb`; advertising name alone is promising, not conclusive proof of exact firmware compatibility.

Close SmartBat-Pro on the phone before commissioning HA. Install via bootstrap (no HACS needed), restart HA, add **BLE Battery Management System** and choose the locally discovered battery. Confirm Offgridtec/OGT detection and compare readings with SmartBat-Pro and a meter under a known charging/discharging condition. Positive current is expected for charge, negative for discharge; verify the sign on this unit.

## Read-only data

The pinned HA integration exposes **sensor and binary_sensor only**. BLE write-characteristic traffic carries read requests; this is not BMS configuration writing. No charging MOSFET, protection, capacity calibration or other configuration control is added. Status entities are indicators, not switches.

| Information | Pinned type-A implementation |
|---|---|
| SOC, pack voltage, current | Read from device |
| Temperature | One reported value (upstream MOSFET/BMS temperature); don't claim all cells are measured |
| Power | Derived upstream from voltage × current |
| Cycles | Reported cycle count |
| Remaining capacity/runtime | Driver reads remaining charge (Ah), nominal capacity (Ah), discharge time; HA may derive stored energy (Wh) |
| Individual cell voltages/delta | **Unavailable for type A in the pinned OGT driver**; only type B reads cell registers |
| BMS status/faults | Show only values actually returned; generic problem/link indicators are not a complete protection-register decode |

Entity attributes can hold extra details such as temperature arrays, charge capacity and design capacity. Inspect Developer tools → States and record supported useful entities; do not fill absent values with zero. The dashboard's `camper_smartbat_capacity` is mapped to the actual available stored-energy entity, with its original Wh units; if only an Ah entity is exposed, retain Ah and label it clearly.

Keep the integration's default 30 s interval initially, as upstream discourages arbitrary changes. Its keep-alive behaviour is an advanced option; benchmark default concurrent operation with BLUETTI first. Do not run vendor phone connections/scanners concurrently. If detection is wrong, collect private diagnostics and compare the exact BLE service/protocol before adding a new driver.

[syssi/esphome-ogt-bms](https://github.com/syssi/esphome-ogt-bms) is an existing alternative with relevant protocol work, but requires separate ESP32 hardware. It is not needed for the requested onboard-only initial installation and is not installed.
