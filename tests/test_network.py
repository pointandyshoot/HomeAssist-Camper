import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'networking/scripts'))
from controller import AP, STA, Controller, Network, command, main, read_config
from provision import profiles, dhcp_config, write_private


def config():
    cfg = json.loads((ROOT / 'networking/config.example.json').read_text())
    cfg.update(starlink_ssid='TEST-WLAN', starlink_password='fake-only-password', ap_password='fake-ap-password')
    return cfg


class FakeNetwork:
    def __init__(self):
        self.current = ''
        self.reachable = False
        self.association = False
        self.ap_success = True
        self.calls = []

    def active(self):
        return self.current

    def up(self, uuid):
        self.calls.append(uuid)
        ok = self.association if uuid == STA else self.ap_success
        self.current = uuid if ok else ''
        return ok

    def viable(self):
        return self.current == STA and self.reachable


class Tests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.network = FakeNetwork()
        self.cfg = config()
        self.controller = Controller(self.cfg, self.network, lambda: self.now, self.advance, lambda _: None)

    def advance(self, seconds):
        self.now += seconds

    def test_boot_without_starlink_falls_back_and_dwells(self):
        self.assertFalse(self.controller.startup())
        self.controller.step()
        self.assertEqual(self.network.calls, [STA, AP])
        self.assertEqual(self.controller.next_probe, 600)

    def test_boot_with_starlink_does_not_activate_ap(self):
        self.network.association = self.network.reachable = True
        self.assertTrue(self.controller.startup())
        self.assertEqual(self.network.calls, [STA])
        self.assertEqual(self.controller.state, 'STARLINK')
        self.assertGreaterEqual(self.now, 30)

    def test_boot_association_without_gateway_restores_ap(self):
        self.network.association = True
        self.assertFalse(self.controller.startup())
        self.assertEqual(self.network.calls, [STA, AP])
        self.assertEqual(self.controller.next_probe, 600)

    def test_failed_association_restores_ap_backoff(self):
        self.controller.fallback()
        self.advance(600)
        self.controller.step()
        self.assertEqual(self.network.calls, [AP, STA, AP])
        self.assertEqual(self.network.current, AP)
        self.assertEqual(self.controller.next_probe, 1800)
        for _ in range(8):
            self.now = self.controller.next_probe
            self.controller.step()
        self.assertEqual(self.controller.backoff, 3600)

    def test_associated_but_unusable_gateway_falls_back(self):
        self.network.association = True
        self.assertFalse(self.controller.trial())
        self.assertEqual(self.network.current, AP)

    def test_stable_lan_promotes_after_hysteresis(self):
        self.network.association = self.network.reachable = True
        self.assertTrue(self.controller.trial())
        self.assertGreaterEqual(self.now, 30)
        self.assertEqual(self.controller.state, 'STARLINK')
        self.advance(3600)
        self.controller.step()  # No WAN check exists; a healthy LAN stays connected.
        self.assertEqual(self.network.calls, [STA])

    def test_briefly_visible_network_does_not_promote(self):
        self.network.association = self.network.reachable = True
        def drop(seconds):
            self.advance(seconds)
            self.network.reachable = False
        self.controller.sleep = drop
        self.assertFalse(self.controller.trial())
        self.assertEqual(self.network.current, AP)

    def test_loss_debounce_recovers(self):
        self.network.association = self.network.reachable = True
        self.controller.trial()
        self.network.reachable = False
        self.controller.step()
        self.advance(45)
        self.controller.step()
        self.assertEqual(self.controller.state, 'STARLINK')
        self.advance(15)
        self.controller.step()
        self.assertEqual(self.network.current, AP)

    def test_intermittent_loss_resets_debounce(self):
        self.network.association = self.network.reachable = True
        self.controller.trial()
        self.network.reachable = False
        self.controller.step()
        self.advance(45)
        self.network.reachable = True
        self.controller.step()
        self.network.reachable = False
        self.advance(45)
        self.controller.step()
        self.assertEqual(self.controller.state, 'STARLINK')

    def test_restart_while_connected_preserves_starlink(self):
        self.network.current = STA
        self.network.reachable = True
        self.assertTrue(self.controller.startup())
        self.assertEqual(self.network.calls, [])
        self.assertEqual(self.network.current, STA)
        self.assertGreaterEqual(self.now, 30)

    def test_restart_on_broken_starlink_restores_ap(self):
        self.network.current = STA
        self.assertFalse(self.controller.startup())
        self.assertEqual(self.network.calls, [AP])
        self.assertEqual(self.network.current, AP)

    def test_boot_brief_starlink_connection_does_not_promote(self):
        self.network.association = self.network.reachable = True
        def drop(seconds):
            self.advance(seconds)
            self.network.reachable = False
        self.controller.sleep = drop
        self.assertFalse(self.controller.startup())
        self.assertEqual(self.network.current, AP)
        self.assertEqual(self.controller.backoff, 600)

    def test_ready_notifies_only_after_initial_network_selection(self):
        events = []
        self.controller.heartbeat = events.append
        with patch.object(self.controller, 'step', side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                self.controller.run()
        self.assertEqual(self.network.current, AP)
        self.assertEqual(events[-1], 'READY=1')

    def test_rescue_leaves_starting_controller_alone(self):
        for state in ('active', 'activating', 'reloading'):
            with self.subTest(state=state), patch('controller.read_config', return_value=self.cfg), \
                    patch('controller.Network', return_value=self.network), \
                    patch('controller.command', return_value=(True, state)), \
                    patch('sys.argv', ['controller.py', '--rescue']):
                main()
                self.assertEqual(self.network.calls, [])

    def test_rescue_recovers_failed_controller(self):
        with patch('controller.read_config', return_value=self.cfg), \
                patch('controller.Network', return_value=self.network), \
                patch('controller.command', return_value=(True, 'failed')), \
                patch('sys.argv', ['controller.py', '--rescue']):
            main()
        self.assertEqual(self.network.current, AP)

    def test_failed_ap_is_retried(self):
        self.network.ap_success = False
        self.controller.fallback()
        self.network.ap_success = True
        self.controller.step()
        self.assertEqual(self.network.current, AP)

    def test_manual_profile_no_routing_and_escape(self):
        cfg = config()
        cfg['starlink_ssid'] = ' Test \\ WLAN '
        rendered = profiles(cfg)
        self.assertIn('method=manual', rendered['camper-ap.nmconnection'])
        self.assertNotIn('method=shared', ''.join(rendered.values()))
        self.assertIn(r'ssid=\sTest\s\\\sWLAN\s', rendered['camper-starlink.nmconnection'])
        self.assertIn('dhcp-option=3\n', dhcp_config(cfg))
        self.assertIn('dhcp-option=6\n', dhcp_config(cfg))
        self.assertIn('port=0', dhcp_config(cfg))

    def test_missing_secrets_and_placeholders_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'network.json'
            with self.assertRaises(FileNotFoundError):
                read_config(path)
            path.write_text((ROOT / 'networking/config.example.json').read_text())
            with self.assertRaises(ValueError):
                read_config(path)
            for malformed in ([], {'interface': 42}):
                path.write_text(json.dumps(malformed))
                with self.assertRaises(ValueError):
                    read_config(path)
            cfg = config()
            path.write_text(json.dumps(cfg))
            self.assertEqual(read_config(path)['ap_channel'], 6)
            cfg['starlink_ssid'] = 'bad\n[connection]'
            path.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                read_config(path)

    def test_secret_permissions_atomic_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'secret'
            write_private(path, 'first')
            write_private(path, 'second')
            self.assertEqual(path.read_text(), 'second')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_name('secret.tmp').exists())

    def test_nm_command_timeout_is_failure(self):
        import subprocess
        with patch('controller.subprocess.run', side_effect=subprocess.TimeoutExpired('nmcli', 55)):
            self.assertEqual(command('nmcli'), (False, ''))

    def test_link_local_address_rejected(self):
        with patch('controller.command', side_effect=[(True, STA), (True, '[{"addr_info":[{"local":"169.254.1.2","scope":"global"}]}]')]):
            self.assertFalse(Network('wlan0').viable())

    def test_arp_unreachable_rejected(self):
        results = [(True, STA), (True, '[{"addr_info":[{"local":"192.168.1.10","scope":"global"}]}]'),
                   (True, '[{"gateway":"192.168.1.1"}]'), (False, '')]
        with patch('controller.command', side_effect=results):
            self.assertFalse(Network('wlan0').viable())


if __name__ == '__main__':
    unittest.main()
