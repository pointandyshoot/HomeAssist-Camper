from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from install import copy_missing


class InstallerTests(unittest.TestCase):
    def test_mesh_install_preserves_private_config_and_existing_component(self):
        from integrations import install_companion
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)
            install_companion(config)
            private = config / 'camper_mesh.json'
            private.write_text('{"enabled": false, "private-test": "preserve"}')
            component = config / 'custom_components/camper_mesh/manifest.json'
            before = component.read_text()
            install_companion(config)
            self.assertIn('preserve', private.read_text())
            self.assertEqual(component.read_text(), before)
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertTrue((config / 'www/camper-mesh-card.js').exists())

    def test_rerun_preserves_secret_and_user_config(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            target = Path(folder) / 'config/secrets.yaml'
            source.write_text('initial')
            self.assertTrue(copy_missing(source, target))
            target.write_text('private-user-value')
            source.write_text('new-template')
            self.assertFalse(copy_missing(source, target))
            self.assertEqual(target.read_text(), 'private-user-value')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_failed_copy_never_publishes_partial_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            target = Path(folder) / 'config/secrets.yaml'
            source.write_text('private-test-value')
            with patch('install.os.fsync', side_effect=OSError('simulated storage failure')):
                with self.assertRaises(OSError):
                    copy_missing(source, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.iterdir()), [])
