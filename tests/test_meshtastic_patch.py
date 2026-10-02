"""Check the pinned real source without requiring a radio or HA import."""
import ast
import asyncio
import base64
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from meshtastic_patch import patch


@unittest.skipUnless(os.environ.get("MESHTASTIC_SOURCE"), "Set MESHTASTIC_SOURCE to pinned component")
class MeshtasticPatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.component = Path(self.folder.name) / "meshtastic"
        shutil.copytree(os.environ["MESHTASTIC_SOURCE"], self.component)
        patch(self.component)

    def tearDown(self):
        self.folder.cleanup()

    def test_patch_refuses_unreviewed_source(self):
        before = (self.component / "api.py").read_text()
        with self.assertRaises(ValueError):
            patch(self.component)
        self.assertEqual((self.component / "api.py").read_text(), before)

    async def test_cosmetic_hardware_lookup_is_fully_local(self):
        tree = ast.parse((self.component / "helpers.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "fetch_meshtastic_hardware_names")
        node.returns = None
        node.args.args[0].annotation = None
        ns = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "<patched helper>", "exec"), ns)
        self.assertEqual(await ns[node.name](object()), {})

    def test_no_host_time_write_to_gps_radio(self):
        tree = ast.parse((self.component / "api.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MeshtasticApiClient")
        connect = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "connect")
        calls = [n for n in ast.walk(connect) if isinstance(n, ast.Call)]
        self.assertFalse(any(isinstance(n.func, ast.Attribute) and n.func.attr == "_add_background_task" for n in calls))

    async def test_secure_reply_forces_pki_and_refuses_unknown_or_changed_key(self):
        tree = ast.parse((self.component / "api.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MeshtasticApiClient")
        method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_send_secure_text")
        # Real vendored protobuf modules, synthetic transport boundary only.
        modules = {}
        for suffix, path in (("", self.component.parent), (".meshtastic", self.component),
                             (".meshtastic.aiomeshtastic", self.component / "aiomeshtastic"),
                             (".meshtastic.aiomeshtastic.protobuf", self.component / "aiomeshtastic/protobuf")):
            name = "custom_components" + suffix
            modules[name] = ModuleType(name)
            modules[name].__path__ = [str(path)]
        ns = {"__package__": "custom_components.meshtastic", "asyncio": asyncio}
        with mock_patch.dict(sys.modules, modules):
            exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "<patched upstream>", "exec"), ns)
            key = bytes(range(32))
            nodes = {102: {"user": {"publicKey": base64.b64encode(key).decode()}}}
            sent = []
            async def send(packet):
                sent.append(packet)
                return True
            own = {"user": {"publicKey": "synthetic"}}
            subject = SimpleNamespace(get_own_node=lambda: own,
                _interface=SimpleNamespace(nodes=lambda: nodes, _connection=SimpleNamespace(send_packet=send)))
            self.assertTrue(await ns[method.name](subject, "status", 102, key))
            self.assertTrue(sent[0].packet.pki_encrypted)
            self.assertEqual(sent[0].packet.public_key, key)
            self.assertEqual(sent[0].packet.to, 102)
            self.assertEqual(sent[0].packet.decoded.payload, b"status")
            self.assertFalse(await ns[method.name](subject, "status", 102, bytes(32)))
            self.assertFalse(await ns[method.name](subject, "status", 999, key))
            own["user"]["isLicensed"] = True
            self.assertFalse(await ns[method.name](subject, "status", 102, key))
            self.assertEqual(len(sent), 1)
