import json
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.local_console import InstanceLock, create_server
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

    def test_shutdown_requires_explicit_request_and_stops_server(self):
        self.assertEqual(self.call('/api/shutdown', {})[0], 400)
        self.assertEqual(self.call('/api/state')[0], 200)
        self.assertEqual(self.call('/api/shutdown', {'confirm': True})[0], 200)
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def test_os_lock_rejects_second_process_and_releases(self):
        code = ('from scripts.local_console import InstanceLock; '
                'import sys; lock=InstanceLock(sys.argv[1]); lock.__enter__(); lock.__exit__()')
        with InstanceLock(self.directory.name):
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, self.directory.name],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, self.directory.name],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_port_conflict_does_not_disrupt_existing_service(self):
        with self.assertRaises(OSError):
            create_server(self.store, port=self.server.server_port)
        self.assertEqual(self.call('/api/state')[0], 200)

    def test_product_edit_selection_scripts_and_conflict(self):
        def create(index, name):
            status, value = self.call('/api/products', {'title': name, 'content': name + '商品信息', 'product_index': index})
            self.assertEqual(status, 200)
            return value['product']
        a, b = create('008', '茶杯'), create(3, '毛巾')
        self.assertEqual(self.call('/api/products/select', {'product_id':a['id']})[0], 200)
        self.assertEqual(self.call('/api/products')[1]['selected'], a['id'])
        self.assertEqual(self.call('/api/scripts', {'snapshot':a, 'text':'茶杯话术'})[0], 201)
        self.assertEqual(self.call('/api/scripts?product_id=' + b['id'])[1]['scripts'], [])
        update = {'product_id':a['id'], 'version':a['version'], 'title':a['title'],
                  'content':'容量更新', 'product_index':a['product_index']}
        self.assertEqual(self.call('/api/products', update)[0], 200)
        self.assertEqual(self.call('/api/products', update)[0], 409)
        self.assertEqual(self.call('/api/scripts', {'snapshot':a, 'text':'过期话术'})[0], 409)
        self.assertEqual(len(self.call('/api/scripts?product_id=' + a['id'])[1]['scripts']), 1)

    def test_invalid_product_requests_visible(self):
        for path, value in [('/api/products', {}), ('/api/products/select', {}), ('/api/scripts', {}),
                            ('/api/products', {'title':'', 'content':'x', 'product_index':1})]:
            self.assertEqual(self.call(path, value)[0], 400)
        self.assertEqual(self.call('/api/scripts')[0], 400)


if __name__ == '__main__':
    unittest.main()
