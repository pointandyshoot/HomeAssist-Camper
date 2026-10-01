# Validation and physical acceptance

## Development results — 2 October 2026

Performed in an x86_64 development environment, with no Pi/batteries/SDR attached:

| Check | Result / scope |
|---|---|
| Compose | Docker Compose v2.40.3 `config --quiet` accepted example environment; missing `HA_IMAGE` is rejected. No actual ARM64 container launched here. |
| ARM64 image | Registry index for HA 2026.9.4 includes linux/arm64. Digest recorded in RESEARCH.md. |
| YAML/Python/includes/docs/privacy patterns | Public-tree validator checks YAML, duplicate keys, local includes, Python syntax, doc links, forbidden private paths and common secrets/identifiers. Manual full-diff review also required. |
| Home Assistant configuration | HA **2026.9.4** under Python **3.14** ran its native `--script check_config` successfully on a temporary copy with fake timezone secrets. The checker loaded an unrelated camera dependency which warned about missing host libturbojpeg; this was nonfatal and no camera is configured. This is schema validation, not successful BLE startup. |
| Shell | ShellCheck 0.9.0 accepted bootstrap/health/backup scripts. |
| systemd | `systemd-analyze verify` passed on identical unit copies with only the dnsmasq executable path adjusted to its extracted development binary. Default host paths/dependencies are checked in CI with dnsmasq-base and on the Pi. No watchdog/recovery unit was executed against a real systemd/NM host here. |
| DHCP | dnsmasq 2.90 accepted the generated DHCP-only configuration using `--test`. No real lease/packet-routing test performed. |
| Derived template | HA template engine computed 700 W from four known power readings and made availability false when an input was unavailable. |
| Automated tests | **21 tests passed**, including four against actual pinned upstream BLUETTI source. No hardware/network radio was attached. |
| Controller policy | Tests cover boot AP, dwell, failed association, unusable gateway, brief network, stable promotion, loss debounce/reset, backoff cap, failed AP retry, reboot and bounded command failure. NetworkManager/radio are simulated. |
| Private provisioning | Tests reject missing/example secrets, reject newline injection, preserve existing installer files, enforce 0600 private output and render DHCP without router/DNS/shared mode. They exercise provisioning primitives, not a complete OS installation twice. |
| BLUETTI patches | Exact v1.0.5 source accepted patches and compiled with Python 3.14. Tests execute patched cached-library and BLE setup paths using isolated boundaries; protocol retention and refusal to repatch changed source checked. No encryption/native-library/device exchange tested. |
| Credentials | No real credentials were supplied to development. Provided device suffix is deliberately absent from all public files. Patterns and full diff reviewed before each commit; not a mathematical guarantee of no secrets. |

Run:

```sh
python3 tools/validate.py
python3 -m unittest discover -s tests -v
shellcheck tools/*.sh
docker compose --env-file .env.example config --quiet
systemd-analyze verify --man=no networking/systemd/* tools/camper-metrics.service tools/camper-metrics.timer
```

Optional full upstream patch tests: fetch the exact v1.0.5 component into a temporary directory, verify SHA from RESEARCH.md, then set `BLUETTI_SOURCE=/temporary/source/custom_components/bluetti` for unittest. CI does this and uses a stock AMD64 HA image for schema checks. Public CI uses fake example secrets only; it never touches private device credentials.

## Mandatory Pi commissioning (record results privately)

- [ ] Bootstrap clean supported 64-bit OS; confirm onboard BLE/AP capability, country, DHCP and no USB adapters.
- [ ] Run bootstrap twice: local Wi-Fi credentials, runtime YAML, HA accounts, custom components and database remain unchanged. Initial SSH connection survives until reboot.
- [ ] Missing credentials on a clean install fail before OS changes. Correct local inputs allow a rerun after an interrupted install.
- [ ] Starlink off at cold boot: AP visible, DHCP in `.20`–`.100`, HA/browser reachable at `.1:8123`, no DHCP default gateway/DNS/NAT. Phone stays connected.
- [ ] Smartphone mobile Internet and local HA work together, or document phone-specific fallback. `.local` works on both LANs or direct-IP/app switching procedure is confirmed.
- [ ] Starlink on: wait for trial; wrong password and DHCP/router failures return AP; correct LAN remains stable overnight. A brief SSID/radio appearance doesn't promote.
- [ ] Starlink WAN outage with LAN up does not return AP. Power router off: debounced AP fallback is reachable. Reboot in each state recovers AP first.
- [ ] Kill the controller during a trial: `ExecStopPost`/restart restore AP. Stop/fail the controller: independent rescue timer works. Deliberately corrupt only config (keeping NM AP profile) and confirm recovery; restore private config immediately.
- [ ] All three BLE devices supply valid readings simultaneously. Compare known loads/readings against displays/meters; verify SmartBat current sign and type-A limitations.
- [ ] BLUETTI native library imports on ARM64 and actual AC/DC controls work over BLE with no WAN. Pi has independent power for these tests.
- [ ] Run cache audit; with Starlink off restart HA, reload BLUETTI and cold boot. Repeat after OAuth expiry and extended offline use; verify key validity. Test failure/recovery after actual firmware changes online.
- [ ] Aranet/SmartBat readings and Recorder/history charts continue offline and through Wi-Fi transitions; unavailable/stale readings are visible, not treated as zero.
- [ ] 24 h combined workload: no OOM/restart loop, responsive SSH/dashboard, reasonable RAM/zram headroom, no SD swap churn, thermals/power stable. Observe purge/repack too.
- [ ] Private backup/image/spare card restored successfully; cached pairing/control/history recovered. New stock-container recreation needs Internet unless provisioned image is restored.
- [ ] HA update and matching image/config/DB rollback rehearsed.

The system is **not physically accepted until this checklist passes**. Outstanding hardware/firmware limits are explicit, rather than claimed tested from simulation.
