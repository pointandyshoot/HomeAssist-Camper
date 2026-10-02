"""Local HA adapter for the pinned Meshtastic integration; optional hardware."""
import asyncio
import base64
from datetime import timedelta
import logging
import time

import voluptuous as vol

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import SupportsResponse, callback
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.event import async_track_time_interval

from .core import History, Policy, read_config, valid_position

DOMAIN = "camper_mesh"
CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): vol.Schema({})}, extra=vol.ALLOW_EXTRA)
LOGGER = logging.getLogger(__name__)


class Bridge:
    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self.policy = Policy(config) if config.get("enabled") else None
        self.history = None
        self.status = "Not configured"
        self.gps = None
        self.count = self.repeats = self.dropped = 0
        self.last_command = "None"
        self.batch = {}
        self.commands = asyncio.Queue(maxsize=16)
        self.worker = None
        self.unsubscribers = []
        self.last_prune = 0
        self.flushing = asyncio.Lock()
        self.client_entry = None

    def client(self):
        if not self.config.get("enabled"):
            return None
        for entry in self.hass.config_entries.async_entries("meshtastic"):
            data = getattr(entry, "runtime_data", None)
            client = getattr(data, "client", None)
            if (entry.data.get("connection_type") == "bluetooth" and client and
                    client._interface._connection.is_connected and
                    client.get_own_node().get("num") == self.config["gateway_node"]):
                return entry.entry_id, client
        return None

    def fresh_gps(self):
        return valid_position(self.gps or {}, time.time(), self.config.get("gps_max_age_seconds", 300))

    @callback
    def notify(self):
        self.hass.bus.async_fire("camper_mesh_updated")

    @callback
    def packet(self, event):
        try:
            match = self.client()
            if not match or match[0] != event.data.get("config_entry_id"):
                return
            packet = event.data["data"]
            sender = packet.get("from")
            if type(sender) is not int or not 0 < sender < 0xFFFFFFFF:
                return
            now = time.time()
            remote = None
            if packet.get("decoded", {}).get("portnum") == "POSITION_APP":
                from custom_components.meshtastic.aiomeshtastic.protobuf import mesh_pb2
                position = mesh_pb2.Position()
                position.ParseFromString(base64.b64decode(packet["decoded"]["payload"], validate=True))
                # Timestamp is the radio's position measurement, not reception time.
                remote = valid_position({"latitude": position.latitude_i / 1e7,
                    "longitude": position.longitude_i / 1e7, "time": position.time,
                    "precision_bits": position.precision_bits}, now, self.config["gps_max_age_seconds"])
                if sender == self.config["gateway_node"]:
                    if position.location_source == mesh_pb2.Position.LOC_INTERNAL and remote:
                        self.gps = remote
                    return
            if sender == self.config["gateway_node"] or packet.get("viaMqtt") is True:
                return
            peer = match[1]._interface.nodes().get(sender, {})
            name = peer.get("user", {}).get("longName", "Unnamed radio")
            # One aggregate sample/node/minute, never the cached startup node DB.
            if sender in self.batch or len(self.batch) < 256:
                old = self.batch.get(sender)
                self.batch[sender] = (sender, name, now, packet, self.fresh_gps(), remote or (old[5] if old else None))
            else:
                self.dropped += 1
            authenticated = self.policy.authenticate(packet, self.config["gateway_node"])
            if authenticated:
                try:
                    self.commands.put_nowait((match[0], packet, authenticated))
                except asyncio.QueueFull:
                    self.dropped += 1
        except Exception:
            # Untrusted radio payloads must never break HA or reveal packet data.
            self.dropped += 1

    async def flush(self, _now=None):
        async with self.flushing:
            match = self.client()
            entry = match[0] if match else None
            if entry != self.client_entry:
                self.policy.pending.clear()
                self.client_entry = entry
            self.status = "Connected" if match else "Radio unavailable"
            batch, self.batch = self.batch, {}
            gps = self.fresh_gps()
            now = time.time()
            def save():
                for row in batch.values():
                    self.history.record(*row)
                if gps:
                    self.history.route(gps)
                if now - self.last_prune >= 3600:
                    self.history.prune(now)
                    self.last_prune = now
                return self.history.snapshot(1)
            try:
                summary = await self.hass.async_add_executor_job(save)
                self.count, self.repeats = summary["count"], summary["repeats"]
            except Exception:
                self.status = "History unavailable"
                LOGGER.error("Camper mesh history unavailable; inspect private storage permissions/free space")
            self.notify()

    def reading(self, entity):
        state = self.hass.states.get(entity)
        if (not state or state.state in ("unknown", "unavailable") or
            not 0 <= time.time() - state.last_reported.timestamp() <= self.config["telemetry_max_age_seconds"]):
            return None
        return state.state

    def status_text(self):
        config = self.config
        def watts(entities):
            try:
                if not entities:
                    return "unavailable"
                values = [self.reading(entity) for entity in entities]
                return f"{sum(float(value) for value in values):.0f}W" if all(value is not None for value in values) else "unavailable"
            except (TypeError, ValueError):
                return "unavailable"
        soc = self.reading(config["soc_sensor"])
        ac = self.reading(config["ac_switch"])
        return f"BLUETTI SOC {soc + '%' if soc else 'unavailable'}; in {watts(config['input_sensors'])}; out {watts(config['output_sensors'])}; AC {ac or 'unavailable'}"

    async def reply(self, sender, text):
        match = self.client()
        if match and hasattr(match[1], "async_send_secure_text"):
            try:
                return await match[1].async_send_secure_text(text, sender, self.config["keys"][sender])
            except Exception:
                return False
        return False

    async def process_command(self, entry_id, packet, authenticated):
        match = self.client()
        if not match or match[0] != entry_id:
            self.policy.pending.clear()
            return
        sender, text = authenticated
        if not await self.hass.async_add_executor_job(self.history.consume, sender, packet["id"], text, time.time()):
            return
        action, value = self.policy.command(sender, text, time.monotonic())
        if action == "drop":
            return
        if action == "help":
            result = "Commands: status; ac on; ac off. AC requests need confirm TOKEN within 90s. No BMS/DC settings."
        elif action == "status":
            result = self.status_text()
        elif action == "denied":
            result = "AC mesh control disabled. Use the local HA dashboard."
        elif action == "challenge":
            result = f"Confirm AC {value[0].upper()}: confirm {value[1]} (90s). Only continue if powering the Pi independently."
        elif action == "set":
            # Consume challenge BEFORE attempting control. Never retry a power change.
            current = self.reading(self.config["ac_switch"])
            if current not in ("on", "off"):
                result = "AC not changed: fresh switch telemetry unavailable."
            elif current == value:
                result = f"AC already {value} (observed)."
            else:
                try:
                    await asyncio.wait_for(self.hass.services.async_call("switch", "turn_" + value,
                        {"entity_id": self.config["ac_switch"]}, blocking=True), timeout=20)
                    result = "AC command sent; state not yet confirmed. Check HA before relying on it."
                    for _ in range(15):
                        if self.reading(self.config["ac_switch"]) == value:
                            result = f"AC {value} (observed in HA)."
                            break
                        await asyncio.sleep(1)
                except Exception:
                    result = "AC command failed or timed out; state unknown. Check HA."
            self.last_command = "AC " + value + " requested"
        else:
            return
        self.notify()
        await self.reply(sender, result)

    async def run(self):
        while True:
            item = await self.commands.get()
            try:
                await self.process_command(*item)
            except Exception:
                LOGGER.error("Camper mesh command rejected after internal failure; no automatic retry")
            finally:
                self.commands.task_done()

    async def stop(self, _event):
        for unsubscribe in self.unsubscribers:
            unsubscribe()
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        if self.history:
            await self.flush()
            await self.hass.async_add_executor_job(self.history.close)


async def async_setup(hass, config):
    try:
        settings = await hass.async_add_executor_job(read_config, hass.config.path("camper_mesh.json"))
        bridge = Bridge(hass, settings)
        if settings.get("enabled"):
            bridge.history = await hass.async_add_executor_job(History, hass.config.path(".storage/camper_mesh.sqlite"), settings["history_days"])
            bridge.status = "Radio unavailable"
            bridge.unsubscribers.append(hass.bus.async_listen("meshtastic_api_packet", bridge.packet))
            bridge.unsubscribers.append(async_track_time_interval(hass, bridge.flush, timedelta(seconds=60)))
            bridge.worker = hass.async_create_background_task(bridge.run(), "camper mesh commands")
    except Exception:
        LOGGER.error("Camper mesh disabled: invalid private configuration or inaccessible storage (values hidden)")
        bridge = Bridge(hass, {"enabled": False})
        bridge.status = "Configuration invalid"
    hass.data[DOMAIN] = bridge
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, bridge.stop)

    async def history(call):
        if not bridge.history:
            return {"nodes": [], "encounters": [], "route": [], "count": 0, "repeats": 0, "status": bridge.status}
        data = await hass.async_add_executor_job(bridge.history.snapshot, call.data["limit"])
        data.update({"status": bridge.status, "gps": bridge.fresh_gps()})
        return data
    hass.services.async_register(DOMAIN, "history", history,
        schema=vol.Schema({vol.Optional("limit", default=200): vol.All(cv.positive_int, vol.Range(min=1, max=500))}),
        supports_response=SupportsResponse.ONLY)
    await discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    return True
