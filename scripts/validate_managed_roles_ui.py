"""Validate managed viewer/operator/admin boundaries in real Chrome pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore, shop_data_directory


def wait_until(read, predicate, message, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.05)
    raise RuntimeError(message)


def submit_product(page, role):
    page.locator('a[href="#products-panel"]').click()
    page.locator('#product-index').fill('1')
    page.locator('#product-title').fill(role + ' 商品')
    page.locator('#product-content').fill('权限页面验证')
    page.locator('#product-form button[type="submit"]').click()
    return wait_until(
        lambda: ((page.locator('#product-message').text_content() or ''),
                 (page.locator('#product-error').text_content() or '')),
        lambda value: bool(value[0] or value[1]), role + ' product submit returned no status')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit('local Chrome is missing')
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix='managed-roles-ui-', ignore_cleanup_errors=True) as raw:
        root = Path(raw) / 'data'
        servers, workers, bases = [], [], {}
        for role in ('viewer', 'operator', 'admin'):
            directory = shop_data_directory(root, role)
            server = create_server(ConfigStore(directory), port=0, shop_id=role,
                                   access_role=role, access_account='account-' + role)
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            servers.append(server); workers.append(worker)
            bases[role] = f'http://127.0.0.1:{server.server_port}'
        try:
            statuses = {}
            headers = {}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                for role, label in (('viewer', '只读'), ('operator', '运营'), ('admin', '管理员')):
                    page = browser.new_page(viewport={'width': 1200, 'height': 800})
                    page.goto(bases[role], wait_until='networkidle')
                    header = page.locator('header').text_content() or ''
                    state = page.locator('#scope').text_content() or ''
                    # Session identity is rendered in the startup status after initial API loading.
                    identity = wait_until(
                        lambda: page.locator('#data-directory').text_content() or '',
                        lambda value: ('角色：' + label) in value and ('账号：account-' + role) in value,
                        role + ' identity was not rendered')
                    headers[role] = {'header': header, 'identity': identity, 'scope': state}
                    statuses[role] = submit_product(page, role)
                    page.screenshot(path=str(report_dir / (role + '.png')), full_page=True)
                    page.close()
                browser.close()

            for role in ('viewer', 'operator'):
                if '无权执行' not in statuses[role][1] or statuses[role][0]:
                    raise RuntimeError(role + ' write was not rejected: ' + repr(statuses[role]))
            if '商品已保存' not in statuses['admin'][0] or statuses['admin'][1]:
                raise RuntimeError('admin write did not succeed: ' + repr(statuses['admin']))

            audits = {}
            for role in ('viewer', 'operator', 'admin'):
                path = shop_data_directory(root, role) / 'authorization-audit.jsonl'
                events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
                product_events = [event for event in events if event['path'] == '/api/products']
                if not product_events or product_events[-1]['allowed'] != (role == 'admin'):
                    raise RuntimeError(role + ' audit does not match the browser action')
                audits[role] = product_events[-1]
            report = {
                'passed': True,
                'roles': {'viewer': 'write denied', 'operator': 'write denied', 'admin': 'write allowed'},
                'identity_rendered': headers,
                'audit_matches_browser_actions': True,
                'screenshots': {role: str(report_dir / (role + '.png'))
                                for role in ('viewer', 'operator', 'admin')},
            }
        finally:
            for server in servers:
                server.shutdown(); server.server_close()
            for worker in workers:
                worker.join(timeout=5)

    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
