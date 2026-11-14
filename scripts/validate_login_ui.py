"""Validate local account login, refresh persistence, role display and logout in Chrome."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import threading

from playwright.sync_api import sync_playwright

from scripts.local_accounts import LocalAccountStore
from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore, shop_data_directory


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

    with tempfile.TemporaryDirectory(prefix='login-ui-', ignore_cleanup_errors=True) as raw:
        root = Path(raw) / 'data'
        shop_id = 'chrome-shop'
        account_database = root / 'accounts.sqlite3'
        LocalAccountStore(account_database).set_account(
            'chrome-admin', 'temporary browser password', shop_id, 'admin')
        config = ConfigStore(shop_data_directory(root, shop_id))
        server = create_server(config, port=0, shop_id=shop_id, require_login=True,
                               account_database=account_database)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 800})
                page.goto(base, wait_until='networkidle')
                page.locator('#login-panel').wait_for(state='visible')
                page.locator('#login-account').fill('chrome-admin')
                page.locator('#login-password').fill('wrong browser password')
                page.locator('#login-form button').click()
                page.locator('#login-error').get_by_text('账号、密码或店铺权限无效').wait_for()
                page.locator('#login-password').fill('temporary browser password')
                page.locator('#login-form button').click()
                page.locator('#workspace').wait_for(state='visible')
                page.locator('#data-directory').get_by_text('账号：chrome-admin').wait_for()
                identity = page.locator('#data-directory').text_content() or ''
                if '店铺 chrome-shop' not in identity or '角色：管理员' not in identity:
                    raise RuntimeError('authenticated identity was not rendered')
                page.screenshot(path=str(report_dir / 'authenticated.png'), full_page=False)
                page.reload(wait_until='networkidle')
                page.locator('#workspace').wait_for(state='visible')
                if page.locator('#login-panel').is_visible():
                    raise RuntimeError('refresh lost the authenticated cookie session')
                page.locator('#logout').click()
                page.locator('#login-panel').wait_for(state='visible')
                page.screenshot(path=str(report_dir / 'logged-out.png'), full_page=False)
                state = page.evaluate("""async () => {
                    const response = await fetch('/api/products', {cache:'no-store'});
                    return {status:response.status, body:await response.json()};
                }""")
                if state['status'] != 401 or '登录' not in state['body'].get('error', ''):
                    raise RuntimeError('logout did not revoke protected API access')
                browser.close()

            events = [json.loads(line) for line in
                      (config.directory / 'authorization-audit.jsonl').read_text(encoding='utf-8').splitlines()]
            report = {
                'passed': True,
                'wrong_password_rejected': True,
                'identity': {'account_id': 'chrome-admin', 'shop_id': shop_id, 'role': 'admin'},
                'refresh_kept_session': True,
                'logout_revoked_session': True,
                'audit_actions': [event['path'] for event in events],
                'screenshots': [str(report_dir / 'authenticated.png'), str(report_dir / 'logged-out.png')],
            }
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)

    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
