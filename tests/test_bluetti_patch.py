"""Run against fetched pinned source when BLUETTI_SOURCE is set.

CI uses exact upstream source; local unit policy tests don't need Internet.
"""
import ast
import asyncio
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bluetti_patch import patch


@unittest.skipUnless(os.environ.get('BLUETTI_SOURCE'), 'Set BLUETTI_SOURCE to pinned component directory')
class PatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.component = Path(self.folder.name) / 'bluetti'
        shutil.copytree(os.environ['BLUETTI_SOURCE'], self.component)
        patch(self.component)

    def tearDown(self):
        self.folder.cleanup()

    async def test_cached_library_never_contacts_checksum_server(self):
        tree = ast.parse((self.component / 'ble/lib/bluetti_lib_loader.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BleLibLoader')
        method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'download_ble_lib')
        module = ast.Module(body=[ast.ClassDef(name='Subject', bases=[], keywords=[], body=[method], decorator_list=[])], type_ignores=[])
        namespace = {'asyncio': asyncio, 'Optional': __import__('typing').Optional}
        exec(compile(ast.fix_missing_locations(module), '<patched upstream loader>', 'exec'), namespace)
        subject = namespace['Subject']()
        subject._get_ble_lib_name = lambda: 'test.so'
        subject.get_lib_path = lambda _: '/private/cache/test.so'
        async def plausible(_):
            return True
        subject._is_plausible_library = plausible
        def forbid_network():
            raise AssertionError('Cached startup attempted network')
        subject._get_ble_lib_download_url = forbid_network
        self.assertEqual(await subject.download_ble_lib(), '/private/cache/test.so')

    def test_unload_and_removal_preserve_protocol(self):
        tree = ast.parse((self.component / '__init__.py').read_text())
        for name in ('async_unload_entry', 'async_remove_entry'):
            node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
            calls = [n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
            self.assertNotIn('remove_download_file', calls)

    def test_changed_source_fails_before_writing(self):
        # Applying again is intentionally rejected; unreviewed updates are not guessed.
        before = (self.component / '__init__.py').read_text()
        with self.assertRaises(ValueError):
            patch(self.component)
        self.assertEqual((self.component / '__init__.py').read_text(), before)

    async def test_ble_setup_uses_cached_keys_without_oauth_refresh(self):
        # Execute the patched upstream setup function with HA/network boundaries
        # stubbed; catches ordering mistakes and unexpected cloud provisioning.
        from types import SimpleNamespace
        tree = ast.parse((self.component / '__init__.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'async_setup_entry')
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        # Replace only the relative BLE library import with supplied stub.
        class RemoveImport(ast.NodeTransformer):
            def visit_ImportFrom(self, n):
                return None
        node = RemoveImport().visit(node)
        calls = []
        async def nothing(*args, **kwargs):
            return None
        async def implementation(*args):
            return SimpleNamespace()
        async def start_ble(*args):
            calls.append('ble')
        class Auth:
            def __init__(self, *args):
                pass
            def start_token_check(self):
                calls.append('oauth-refresh')
        class ProductClient:
            def __init__(self, *args):
                pass
            async def get_decrypt_info(self, *args):
                raise AssertionError('Provisioned BLE setup attempted cloud key request')
        class Data:
            def __init__(self, **kwargs):
                self.devices = kwargs['devices']
        class Log:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        selected = SimpleNamespace(sn='TEST-SERIAL', control_mode='bluetooth', server_key='fake-cache-key')
        entry = SimpleNamespace(options={'devices': ['TEST-SERIAL']}, data={'products': [selected]},
                                entry_id='test', async_on_unload=lambda *args: None)
        hass = SimpleNamespace(config=SimpleNamespace(config_dir=self.folder.name), data={},
                               config_entries=SimpleNamespace(async_forward_entry_setups=nothing),
                               bus=SimpleNamespace(async_listen=lambda *args: lambda: None, fire=lambda *args: None))
        async def executor(fn, *args):
            return fn(*args)
        hass.async_add_executor_job = executor
        ns = dict(os=os, asyncio=asyncio, __LOGGER__=Log(),
                  APPLICATION_PROFILE=SimpleNamespace(load_config=nothing), DOMAIN='bluetti',
                  DOWNDIR='downloads', DOWNDIR_DATA_KEY='download_dir',
                  config_entry_oauth2_flow=SimpleNamespace(async_get_config_entry_implementation=implementation,
                      OAuth2Session=lambda *args: SimpleNamespace(token={'access_token': 'fake-expired-token'})),
                  async_get_clientsession=lambda *args: None, AsyncConfigEntryAuth=lambda *args: None,
                  AuthTokenRefresh=Auth, ProductClient=ProductClient, UserProduct=SimpleNamespace(),
                  ControlMode=SimpleNamespace(BLE='bluetooth', CLOUD='cloud'), BluettiData=Data,
                  start_ble_lib=start_ble, EVENT_BLUETTI_SETUP_OK='test', _PLATFORMS=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<upstream setup>', 'exec'), ns)
        self.assertTrue(await ns['async_setup_entry'](hass, entry))
        self.assertEqual(calls, ['ble'])
