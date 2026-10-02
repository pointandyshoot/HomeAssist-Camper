"""Narrow, fail-closed patch for Meshtastic v0.6.1; no cloud or PKI fallback."""
from pathlib import Path

SECURE_SEND = '''    async def async_send_secure_text(self, text: str, destination: int, public_key: bytes) -> bool:
        """Camper: require a pinned destination key and explicitly force PKI."""
        import base64
        import secrets
        from .aiomeshtastic.protobuf import mesh_pb2, portnums_pb2

        own = self.get_own_node()
        peer = self._interface.nodes().get(destination, {})
        try:
            known = base64.b64decode(peer.get("user", {}).get("publicKey", ""), validate=True)
        except (ValueError, TypeError):
            return False
        if (len(public_key) != 32 or known != public_key or
                own.get("user", {}).get("isLicensed", False) or not own.get("user", {}).get("publicKey")):
            return False
        packet = mesh_pb2.ToRadio()
        packet.packet.to = destination
        packet.packet.id = secrets.randbelow(0xFFFFFFFF) + 1
        packet.packet.pki_encrypted = True
        packet.packet.public_key = public_key
        packet.packet.want_ack = True
        packet.packet.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
        packet.packet.decoded.payload = text.encode("utf-8")[:220]
        return await asyncio.wait_for(self._interface._connection.send_packet(packet), timeout=15)

'''


def patch(component):
    component = Path(component)
    api = component / "api.py"
    content = api.read_text()
    anchor = "    @property\n    def metadata(self)"
    time_sync = "        self._add_background_task(send_time())"
    if content.count(anchor) != 1 or content.count(time_sync) != 1 or "async_send_secure_text" in content:
        raise ValueError("Meshtastic API changed; review before patching")
    # Zero 2 W has no battery-backed RTC. Never overwrite GPS radio time with
    # the Pi's potentially stale offline boot clock (nor change radio timezone).
    content = content.replace(time_sync, "        # Camper: retain GPS radio time; no host clock/config writes.")
    api.write_text(content.replace(anchor, SECURE_SEND + anchor))
    helpers = component / "helpers.py"
    content = helpers.read_text()
    anchor = "async def fetch_meshtastic_hardware_names(hass: HomeAssistant) -> typing.Mapping[str, str]:\n"
    if content.count(anchor) != 1:
        raise ValueError("Meshtastic hardware helper changed")
    # Only friendly model labels depend on this remote API; enum names still work.
    helpers.write_text(content.split(anchor)[0] + anchor + '    """Camper: local enum labels, no startup Internet lookup."""\n    return {}\n')
    import json
    manifest = component / "manifest.json"
    data = json.loads(manifest.read_text())
    data["requirements"] = ["pyserial-asyncio==0.6", "aiomqtt==2.5.0", "protobuf==6.32.0"]
    manifest.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", type=Path)
    patch(parser.parse_args().component)
