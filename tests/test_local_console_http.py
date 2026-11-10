import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore


class ConsoleHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ConfigStore(self.directory.name)
        self.server = create_server(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port
        self.addCleanup(self.stop)
        self.token = self.call('/api/session')[1]['token']

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def call(self, path, value=None, **headers):
        if value is not None:
            headers = {'Origin': self.base, 'Content-Type': 'application/json',
                       'X-Console-Token': getattr(self, 'token', ''), **headers}
        req = Request(self.base + path, data=None if value is None else json.dumps(value).encode(), headers=headers)
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_refresh_does_not_create_config_or_live_session(self):
        for _ in range(3):
            status, value = self.call('/api/state')
            self.assertEqual(status, 200)
            self.assertEqual(value['live_status'], '未启动')
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_save_reload_and_read_only_preflight(self):
        config = {'version': 1, 'runtime_root': self.directory.name, 'port': 5168}
        self.assertEqual(self.call('/api/config', config)[0], 200)
        self.assertEqual(self.call('/api/state')[1]['config'], config)
        self.assertEqual(self.call('/api/preflight', config)[1]['ready'], False)
        self.assertEqual([p.name for p in Path(self.directory.name).iterdir()], ['console.json'])

    def test_cross_origin_token_and_host_checks(self):
        config = self.store.load()
        for headers in ({'Origin': 'https://example.com'}, {'X-Console-Token': 'bad'}, {'Host':'example.com'}):
            self.assertEqual(self.call('/api/config', config, **headers)[0], 403)
        self.assertFalse(self.store.path.exists())

    def test_corrupt_state_visible_and_can_be_explicitly_repaired(self):
        self.store.path.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.call('/api/state')[0], 400)
        self.assertEqual(self.store.path.read_text(), '{broken')
        self.assertEqual(self.call('/api/config', {'version':1,'runtime_root':'','port':5158})[0], 200)

    def test_static_and_unknown_paths(self):
        with urlopen(self.base + '/', timeout=3) as response:
            self.assertIn('数字人工作台', response.read().decode())
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(self.call('/console.json')[0], 404)


if __name__ == '__main__':
    unittest.main()
