"""Small summary entities; private coordinates stay outside Recorder."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from . import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    bridge = hass.data[DOMAIN]
    async_add_entities([MeshSensor(bridge, key, title, icon) for key, title, icon in (
        ("status", "Status", "mdi:radio-handheld"),
        ("count", "Nodes", "mdi:account-group"),
        ("repeats", "Repeat encounters", "mdi:map-marker-check"),
        ("gps", "GPS", "mdi:crosshairs-gps"),
        ("last_command", "Last command", "mdi:power-plug"),
        ("dropped", "Dropped packets", "mdi:message-alert"),
    )])


class MeshSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, bridge, key, title, icon):
        self.bridge, self.key = bridge, key
        self._attr_name = "Camper mesh " + title
        self._attr_unique_id = "camper_mesh_" + key
        self._attr_icon = icon

    @property
    def native_value(self):
        if self.key == "gps":
            return "Fresh fix" if self.bridge.fresh_gps() else "No fresh fix"
        return getattr(self.bridge, self.key)

    async def async_added_to_hass(self):
        @callback
        def update(_event):
            self.async_write_ha_state()
        self.async_on_remove(self.hass.bus.async_listen("camper_mesh_updated", update))
