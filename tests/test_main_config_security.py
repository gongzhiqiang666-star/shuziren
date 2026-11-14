from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from recovered.main_config import (
    UserConfigError, clear_private_config, extract_private_config,
    load_effective_config, load_user_config, save_user_config, write_user_config,
)


class MainConfigSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user = self.root/'user'/'user_config.yaml'

    def test_corrupt_user_config_is_not_silently_overwritten(self):
        self.user.parent.mkdir()
        original = b'private_config: [unterminated\n'
        self.user.write_bytes(original)
        with self.assertRaisesRegex(UserConfigError, '损坏'):
            load_user_config(self.user)
        with self.assertRaises(UserConfigError):
            save_user_config(self.user, {'token': 'new'})
        self.assertEqual(self.user.read_bytes(), original)

    def test_replace_failure_preserves_old_config_and_removes_scratch(self):
        write_user_config(self.user, {'token': 'old'})
        with patch('recovered.main_config.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                write_user_config(self.user, {'token': 'new'})
        self.assertEqual(load_user_config(self.user), {'token': 'old'})
        self.assertEqual(list(self.user.parent.glob('*.tmp')), [])

    def test_private_aliases_are_extracted_and_cleared_recursively(self):
        config = {'service': {'client_secret': 'one', 'ark-api-key': 'two',
                              'nested': [{'session_token': 'three', 'model': 'x'}]},
                  'public': 'keep'}
        private = extract_private_config(config)
        self.assertEqual(private['service']['client_secret'], 'one')
        self.assertEqual(private['service']['ark-api-key'], 'two')
        self.assertEqual(private['service']['nested'][0]['session_token'], 'three')
        clear_private_config(config)
        self.assertEqual(config['service']['client_secret'], '')
        self.assertEqual(config['service']['ark-api-key'], '')
        self.assertEqual(config['service']['nested'][0]['session_token'], '')
        self.assertEqual(config['public'], 'keep')

    def test_legacy_private_migration_prefers_user_and_scrubs_delivery_config(self):
        runtime = self.root/'runtime'; (runtime/'config').mkdir(parents=True)
        base = {'environment': 'production', 'service': {'api_key': 'legacy', 'model': 'm'}}
        (runtime/'config/config.yaml').write_text(yaml.safe_dump(base), encoding='utf-8')
        write_user_config(self.user, {'private_config': {'service': {'api_key': 'user'}}})
        effective = load_effective_config(runtime, self.user)
        self.assertEqual(effective['service']['api_key'], 'user')
        delivered = yaml.safe_load((runtime/'config/config.yaml').read_text(encoding='utf-8'))
        self.assertEqual(delivered['service']['api_key'], '')
        persisted = load_user_config(self.user)
        self.assertEqual(persisted['private_config']['service']['api_key'], 'user')


if __name__ == '__main__':
    unittest.main()
