import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mesh_core", ROOT / "integrations/camper_mesh/core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
# Explicit synthetic IDs/keys only. Never replace these with real radio data.
KEY = bytes(range(32))
KEY2 = bytes(range(32, 64))


def settings():
    return {"enabled": True, "gateway_node": 101, "keys": {102: KEY, 103: KEY2},
            "ac_control_enabled": True, "independent_pi_power_confirmed": True}


def packet(text="status", sender=102):
    return {"from": sender, "to": 101, "id": 1, "pkiEncrypted": True,
            "publicKey": base64.b64encode(KEY if sender == 102 else KEY2).decode(),
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": base64.b64encode(text.encode()).decode()}}


class MeshPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = core.Policy(settings())

    def test_both_radios_are_independently_authorised(self):
        for sender in (102, 103):
            self.assertEqual(self.policy.authenticate(packet(sender=sender), 101), (sender, "status"))

    def test_spoofed_ids_channel_messages_other_gateways_and_mqtt_rejected(self):
        mutations = ({"pkiEncrypted": False}, {"publicKey": base64.b64encode(KEY2).decode()},
                     {"to": 0xFFFFFFFF}, {"from": 104}, {"viaMqtt": True},
                     {"publicKey": "bad"}, {"id": 0}, {"id": "1"})
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertIsNone(self.policy.authenticate(packet() | mutation, 101))
        self.assertIsNone(self.policy.authenticate(packet(), 999))
        missing = packet()
        del missing["pkiEncrypted"]
        self.assertIsNone(self.policy.authenticate(missing, 101))

    def test_malformed_and_oversized_text_rejected(self):
        for payload in ("!!!!", base64.b64encode(b"\xff").decode(), base64.b64encode(b"x" * 221).decode()):
            bad = packet()
            bad["decoded"]["payload"] = payload
            self.assertIsNone(self.policy.authenticate(bad, 101))

    def test_ac_requires_matching_one_time_confirmation(self):
        action, challenge = self.policy.command(102, "ac off", 100)
        self.assertEqual(action, "challenge")
        self.assertEqual(self.policy.command(103, "confirm " + challenge[1], 105)[0], "drop")
        self.assertEqual(self.policy.command(102, "confirm " + challenge[1], 110), ("set", "off"))
        self.assertEqual(self.policy.command(102, "confirm " + challenge[1], 111)[0], "drop")

    def test_expired_or_restarted_challenge_never_switches(self):
        _, challenge = self.policy.command(102, "ac on", 100)
        self.assertEqual(self.policy.command(102, "confirm " + challenge[1], 191)[0], "drop")
        restarted = core.Policy(settings())
        self.assertEqual(restarted.command(102, "confirm " + challenge[1], 110)[0], "drop")

    def test_output_control_requires_both_explicit_enable_flags(self):
        for flag in ("ac_control_enabled", "independent_pi_power_confirmed"):
            config = settings()
            config[flag] = False
            self.assertEqual(core.Policy(config).command(102, "ac off", 100)[0], "denied")

    def test_no_toggle_dc_bms_arbitrary_service_or_reply_flood(self):
        for text in ("toggle", "dc off", "set bms voltage 99", "switch.turn_off anything", "hello"):
            self.assertEqual(self.policy.command(102, text, 100)[0], "drop")
        self.assertEqual(self.policy.command(102, "status", 100)[0], "status")
        self.assertEqual(self.policy.command(102, "status", 101)[0], "drop")
        self.assertEqual(self.policy.command(103, "status", 101)[0], "status")

    def test_missing_disabled_and_invalid_private_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "camper_mesh.json"
            self.assertEqual(core.read_config(path), {"enabled": False})
            path.write_text((ROOT / "meshtastic/config.example.json").read_text())
            self.assertEqual(core.read_config(path), {"enabled": False})
            data = json.loads(path.read_text())
            data["enabled"] = True
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                core.read_config(path)
            data.update(gateway_node=101, authorised_radios=[{"node": 102, "public_key": base64.b64encode(KEY).decode()}])
            path.write_text(json.dumps(data))
            self.assertEqual(core.read_config(path)["keys"], {102: KEY})
            data["authorised_radios"].append({"node": 103, "public_key": base64.b64encode(KEY).decode()})
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                core.read_config(path)
        for invalid in ("!ffffffff", "!00000000", True, -1):
            with self.assertRaises(ValueError):
                core.node_number(invalid)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "mesh.sqlite"
        self.history = core.History(self.path, days=1)

    def tearDown(self):
        self.history.close()
        self.folder.cleanup()

    def test_private_replay_guard_survives_restart(self):
        self.assertTrue(self.history.consume(102, 1, "ac off", 100))
        self.history.close()
        self.history = core.History(self.path)
        self.assertFalse(self.history.consume(102, 1, "ac off", 120))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_repeat_encounters_and_distinct_position_sources(self):
        own = {"latitude": 0.5, "longitude": 0.5, "time": 100, "precision_bits": 32}
        remote = {"latitude": 1.5, "longitude": 1.5, "time": 90, "precision_bits": 16}
        self.history.record(102, "Synthetic radio", 100, {"hopStart": 3, "hopLimit": 3}, own, remote)
        self.history.record(102, "Synthetic radio", 200, {}, None, None)
        self.history.record(102, "Synthetic radio", 2001, {}, None, None)
        data = self.history.snapshot()
        self.assertEqual((data["count"], data["repeats"]), (1, 1))
        self.assertEqual(data["nodes"][0]["sessions"], 2)
        self.assertEqual(data["encounters"][1]["own_time"], 100)
        self.assertEqual(data["encounters"][1]["remote_time"], 90)
        self.assertIsNone(data["nodes"][0]["remote_lat"])
        self.assertEqual(data["nodes"][0]["via"], "relayed or unknown")

    def test_retention_route_debounce_and_response_limit(self):
        for index in range(10):
            self.history.record(102 + index, "Synthetic", 100 + index, {})
            self.history.route({"latitude": 0.5, "longitude": 0.5, "time": 100 + index, "precision_bits": 32})
        self.assertEqual(len(self.history.snapshot(3)["nodes"]), 3)
        self.assertEqual(len(self.history.snapshot()["route"]), 1)
        self.history.prune(100000)
        self.assertEqual(self.history.snapshot()["count"], 0)
        self.assertEqual(self.history.snapshot()["route"], [])

    def test_stale_future_invalid_and_missing_positions_rejected(self):
        position = {"latitude": 0.5, "longitude": 0.5, "time": 100}
        self.assertIsNotNone(core.valid_position(position, 101, 300))
        for bad in ({}, position | {"latitude": 91}, position | {"time": 102},
                    position | {"longitude": float("nan")}, position | {"time": 0}):
            self.assertIsNone(core.valid_position(bad, 1000, 300))


class OptionalHardwareTests(unittest.TestCase):
    def test_compose_needs_no_sdr_usb_mapping_or_mqtt(self):
        import yaml
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
        self.assertEqual(set(compose["services"]), {"homeassistant"})
        self.assertNotIn("devices", compose["services"]["homeassistant"])
        self.assertNotIn("depends_on", compose["services"]["homeassistant"])
        self.assertNotIn("/dev/bus/usb", json.dumps(compose))
        config = (ROOT / "homeassistant/configuration.yaml").read_text()
        self.assertNotIn("mqtt:", config)
        self.assertNotIn("rtl_433", config)
