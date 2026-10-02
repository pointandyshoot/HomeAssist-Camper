# The 512 MB memory constraint

Zero 2 W is ARM64-capable, but it is not on Home Assistant's current recommended Pi hardware list. No measured RAM claim is made here. Image architecture support is separate from memory sufficiency.

Keep the initial workload to HA, BlueZ, NM, DHCP/Avahi and the small host services. Do not install HACS, ESPHome build tools, MariaDB, InfluxDB, Grafana, Node-RED or an MQTT broker until they are needed and measured. The selected YAML replaces default_config with a small explicit set; HA can still load required dependencies internally.

The installer uses native `rpi-swap` on current Pi OS: pure zram at 50% of RAM, capped at 256 MiB, with no SD writeback. On older Bookworm without rpi-swap it uses zram-tools/LZ4 at 50%. It disables `dphys-swapfile` for the next boot if installed and never starts a competing zram manager. Zram uses actual RAM and compression/CPU; 256 MB compressed swap does not mean 256 MB extra physical RAM. Check `swapon --show`: no SD swap should be active. Other pre-existing swap units/files must be reviewed manually. Do not impose an arbitrary HA cgroup memory limit that simply causes repeated OOMs.

Use `sudo tools/health.sh`, `free -m`, `vmstat 5`, `docker stats --no-stream` and kernel OOM logs during onboarding and a 24 h run. Host metrics appear on the Pi health dashboard. HA/container health is an HTTP readiness check, not proof every integration is functioning. Docker only restarts exited containers; unhealthy alone doesn't restart HA. Watch device last-updated timestamps separately.

Acceptance: no OOM kills, no repeated HA/container restarts, stable SSH/dashboard response, and sufficient MemAvailable/zram headroom during all four BLE integrations (including the optional persistent T1000-E connection), database purge and browsing. There is no universal safe threshold; sustained near-exhaustion or swap churn is a failure even if nothing crashed during a brief test. Reduce optional entities/graphs first; if the core workload cannot fit, use a Pi with more RAM rather than wearing the SD with disk swap.

Recorder retains 7 days of detailed history; state-class long-term statistics remain longer. Automatic purge/repack and log rotation reduce growth but do not promise a strict byte cap. Keep at least database-size free space for rebuild/repack plus OS/container update headroom. A monthly disk check and a 32 GB+ high-endurance card are sensible. Unused Docker images are removed only explicitly after a successful update/backup, keeping a known good rollback image.

Use a stable power supply, good ventilation and a location away from metal shielding/high-power wiring. Compare BLE reliability at different placements before tuning kernel/firmware. Update radio firmware/kernel deliberately while online and retest; no unverified coexistence parameter is applied.

Meshtastic adds no container or daemon. Its companion caps nodes/encounters/route/replay rows, batches one reception sample per node per minute and serves only 200 rows to the card. Keep upstream HA entity selection to the three owned radios, disable extra notifications/web/TCP/MQTT proxies, and leave the mesh tab closed when unused. Re-measure memory/BLE latency with this extra connection; four-device coexistence has not been demonstrated on the physical Zero 2 W.
