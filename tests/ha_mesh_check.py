"""Run with the pinned HA Python environment (not the host's generic Python)."""
import asyncio
import base64
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeassistant.core import HomeAssistant
from integrations.camper_mesh import Bridge, async_setup
from integrations.camper_mesh.core import History


async def main():
    with tempfile.TemporaryDirectory() as folder:
        hass = HomeAssistant(folder)
        # The adapter loads with missing or malformed local config and NO radio,
        # SDR, network integration or account. HA stays usable.
        import integrations.camper_mesh as module
        original = module.discovery.async_load_platform
        module.discovery.async_load_platform = AsyncMock()
        try:
            assert await async_setup(hass, {"camper_mesh": {}})
            bridge = hass.data["camper_mesh"]
            assert bridge.status == "Not configured" and bridge.history is None
            response = await hass.services.async_call("camper_mesh", "history", {}, blocking=True, return_response=True)
            assert response["nodes"] == []
            assert not Path(folder, ".storage/camper_mesh.sqlite").exists()
            Path(folder, "camper_mesh.json").write_text('{"enabled": true}')
            assert await async_setup(hass, {"camper_mesh": {}})
            assert hass.data["camper_mesh"].status == "Configuration invalid"
        finally:
            module.discovery.async_load_platform = original
        key = bytes(range(32))
        settings = {"enabled": True, "gateway_node": 101, "keys": {102: key},
            "ac_control_enabled": True, "independent_pi_power_confirmed": True,
            "ac_switch": "switch.camper_bluetti_ac", "soc_sensor": "sensor.camper_bluetti_soc",
            "input_sensors": [], "output_sensors": [], "telemetry_max_age_seconds": 180}
        bridge = Bridge(hass, settings)
        bridge.history = History(Path(folder, "commands.sqlite"))
        connected = True
        client = SimpleNamespace(_interface=SimpleNamespace(nodes=lambda: {}))
        bridge.client = lambda: ("synthetic-entry", client) if connected else None
        bridge.reply = AsyncMock(return_value=True)
        def packet(text, ident):
            return {"from": 102, "to": 101, "id": ident, "pkiEncrypted": True,
                "publicKey": base64.b64encode(key).decode(),
                "decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": base64.b64encode(text.encode()).decode()}}
        # Raw event ingress rejects spoofed ID/group messages, passes verified DM.
        bridge.packet(SimpleNamespace(data={"config_entry_id": "synthetic-entry", "data": packet("status", 1) | {"pkiEncrypted": False}}))
        assert bridge.commands.empty()
        bridge.packet(SimpleNamespace(data={"config_entry_id": "synthetic-entry", "data": packet("status", 2)}))
        assert bridge.commands.qsize() == 1
        await bridge.process_command(*bridge.commands.get_nowait())
        bridge.commands.task_done()
        # AC request alone never calls the appliance; only its live challenge does.
        calls = []
        async def set_ac(call):
            calls.append(call.service)
            hass.states.async_set("switch.camper_bluetti_ac", "off")
        hass.services.async_register("switch", "turn_off", set_ac)
        hass.states.async_set("switch.camper_bluetti_ac", "on")
        await bridge.process_command("synthetic-entry", {"id": 3}, (102, "ac off"))
        # Status rate limiter runs first; deliberately clear only test timing state.
        bridge.policy.replies.clear()
        await bridge.process_command("synthetic-entry", {"id": 4}, (102, "ac off"))
        assert calls == []
        nonce = bridge.policy.pending[102][1]
        await bridge.process_command("synthetic-entry", {"id": 5}, (102, "confirm " + nonce))
        assert calls == ["turn_off"]
        assert "observed" in bridge.reply.call_args.args[1]
        await bridge.process_command("synthetic-entry", {"id": 5}, (102, "confirm " + nonce))
        assert calls == ["turn_off"]
        # Unavailable switch cannot be changed, and a disconnected gateway denies.
        bridge.policy.replies.clear()
        hass.states.async_set("switch.camper_bluetti_ac", "unavailable")
        await bridge.process_command("synthetic-entry", {"id": 6}, (102, "ac on"))
        nonce = bridge.policy.pending[102][1]
        await bridge.process_command("synthetic-entry", {"id": 7}, (102, "confirm " + nonce))
        assert calls == ["turn_off"] and "not changed" in bridge.reply.call_args.args[1]
        connected = False
        await bridge.process_command("synthetic-entry", {"id": 8}, (102, "ac on"))
        assert bridge.policy.pending == {} and calls == ["turn_off"]
        # Exact firmware position protobuf shape is imported by the actual adapter.
        # Hardware GPS reception still needs commissioning.
        bridge.history.close()
        await hass.async_stop()
    # Real HA loader + sensor discovery, beyond the isolated control boundaries.
    import shutil
    from homeassistant import config_entries, loader
    from homeassistant.bootstrap import async_load_base_functionality
    from homeassistant.setup import async_setup_component
    with tempfile.TemporaryDirectory() as folder:
        shutil.copytree(ROOT / "integrations/camper_mesh", Path(folder, "custom_components/camper_mesh"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        hass = HomeAssistant(folder)
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {"camper_mesh": {}})
        await async_load_base_functionality(hass)
        assert await async_setup_component(hass, "camper_mesh", {"camper_mesh": {}})
        await hass.async_block_till_done()
        assert hass.states.get("sensor.camper_mesh_status").state == "Not configured"
        assert hass.states.get("sensor.camper_mesh_gps").state == "No fresh fix"
        await hass.async_stop()
    print("HA adapter: missing/invalid config, response service, raw PKI ingress, confirmation, replay, unavailable switch and disconnected gateway passed")


if __name__ == "__main__":
    asyncio.run(main())
