"""Narrow, fail-closed source patches for exactly official BLUETTI v1.0.5.

No protocol changes or private keys. See docs/BLUETTI.md for rationale.
"""
from pathlib import Path

CHANGES = {
    "__init__.py": [
        ("    authTokenRefresh = AuthTokenRefresh(hass, entry, oAuth2Session)",
         "    selected_products = [p for p in all_products if p.sn in enabled_devices]\n    authTokenRefresh = AuthTokenRefresh(hass, entry, oAuth2Session)"),
        ("    selected_products = [p for p in all_products if p.sn in enabled_devices]\n\n    # check ble key is ok",
         "    # check ble key is ok"),
        ("    authTokenRefresh.start_token_check()", """    # Camper: BLE-only entries use provisioned local keys. Do not periodically
    # refresh OAuth/reload the BLE driver during offline operation.
    if not selected_products or any(p.control_mode != ControlMode.BLE for p in selected_products):
        authTokenRefresh.start_token_check()"""),
        ("if device.control_mode == ControlMode.BLE and device.server_key == None or device.server_key == '':",
         "if device.control_mode == ControlMode.BLE and (device.server_key is None or device.server_key == ''):"),
        ("    await bluetti_devices.remove_download_file(hass)",
         "    # Camper: keep provisioned protocol files on reload/unload for offline restart."),
    ],
    "ble/lib/bluetti_lib_loader.py": [
        ("        ble_lib_download_url = self._get_ble_lib_download_url()\n        checksums =",
         """        # Camper: a provisioned library must not need an online checksum lookup
        # or silently update itself. Version upgrades are explicit operations.
        local = await asyncio.to_thread(self.get_lib_path, self._get_ble_lib_name())
        if local is not None and await self._is_plausible_library(local):
            return local
        ble_lib_download_url = self._get_ble_lib_download_url()
        checksums ="""),
    ],
}


def patch(component):
    component = Path(component)
    replacements = {}
    for relative, changes in CHANGES.items():
        file = component / relative
        content = file.read_text()
        for old, new in changes:
            expected = 2 if old == "    await bluetti_devices.remove_download_file(hass)" else 1
            if content.count(old) != expected:
                raise ValueError(f"Upstream changed: refusing to patch {relative}")
            content = content.replace(old, new)
        replacements[file] = content
    # Validate every match first, then write. Installer operates on a staging dir.
    for file, content in replacements.items():
        file.write_text(content)
