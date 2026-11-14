"""Validate the bounded cache-cleanup button in a real Chrome page."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore


def wait_until(read, predicate, message, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.05)
    raise RuntimeError(message)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit('local Chrome is missing')
    report_dir = args.report_dir.resolve(); report_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix='cache-cleanup-ui-', ignore_cleanup_errors=True) as raw:
        root = Path(raw)
        cache_root = root / 'controlled-temp'; cache_root.mkdir()
        first = cache_root / 'short_video'; first.mkdir(); (first / 'one.bin').write_bytes(b'a' * 17)
        second = cache_root / 'voice_infer'; second.mkdir(); (second / 'two.bin').write_bytes(b'b' * 23)
        unrelated = cache_root / 'operator-notes.txt'; unrelated.write_text('keep', encoding='utf-8')
        store = ConfigStore(root / 'data')
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with patch('recovered.cache_cleanup.tempfile.gettempdir', return_value=str(cache_root)):
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                    page = browser.new_page(viewport={'width': 1200, 'height': 850})
                    page.goto(base, wait_until='networkidle')
                    page.locator('#cache-clear').click()
                    status = wait_until(lambda: page.locator('#cache-clear-status').text_content() or '',
                                        lambda value: '缓存清理完成' in value,
                                        'cache cleanup did not report success')
                    error = page.locator('#cache-clear-error').text_content() or ''
                    if error or '文件 2 个' not in status or '40 字节' not in status:
                        raise RuntimeError(json.dumps({'status': status, 'error': error}, ensure_ascii=False))
                    screenshot = report_dir / 'cache-cleaned.png'
                    page.locator('#system-maintenance-panel').screenshot(path=str(screenshot))
                    browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=5)
        if first.exists() or second.exists() or unrelated.read_text(encoding='utf-8') != 'keep':
            raise RuntimeError('cleanup escaped the two owned cache directories')

    report = {
        'passed': True, 'removed_files': 2, 'removed_bytes': 40,
        'known_cache_directories_removed': ['short_video', 'voice_infer'],
        'unrelated_file_preserved': True, 'status': status, 'screenshot': str(screenshot),
    }
    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
