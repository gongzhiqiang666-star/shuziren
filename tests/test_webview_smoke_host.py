import json
import tempfile
import unittest
from pathlib import Path

from scripts.webview_smoke_host import SmokeApi


class WebviewSmokeHostTests(unittest.TestCase):
    def test_shutdown_marker_is_atomic_and_counts_calls(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root)/'nested'/'closed.json'
            api = SmokeApi(marker)
            self.assertEqual(api.shutdown(), {'status': 'success'})
            self.assertEqual(json.loads(marker.read_text(encoding='utf-8'))['shutdown_calls'], 1)
            self.assertEqual(list(marker.parent.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
