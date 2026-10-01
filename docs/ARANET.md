# Aranet4

Use Home Assistant's [native Aranet integration](https://www.home-assistant.io/integrations/aranet/). No custom driver or additional container.

Update firmware to at least 1.2.0 using the Aranet application and enable **Smart Home integration** in its settings. Then close the phone app and add the discovered Aranet entry in HA with Bluetooth enabled. Keep the device's normal measurement interval initially; do not add a second polling loop.

Expected Aranet4 telemetry: CO₂ (ppm), temperature (°C), relative humidity (%), atmospheric pressure (hPa) and battery level when supplied. Inspect actual entities after discovery and rename them using DASHBOARD.md. Recorder includes sensors automatically. The readings and history work without Internet after the native integration and its Python requirement are installed.

Verify measurements against the device's display after boot with Starlink off and while the Pi switches networks. Measure battery impact before shortening measurement cadence. There is no automatic CO₂ calibration or threshold alarm in this initial build; calibration remains the device manufacturer's procedure.
