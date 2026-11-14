"""Validate business CSV upload, correction, reload, and zero-vs-unknown in Chrome."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import threading
import time

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


def upload_csv(page, path: Path) -> None:
    page.locator('#business-import-form button[type="submit"]').wait_for(state='visible')
    wait_until(lambda: page.locator('#business-import-form button[type="submit"]').is_enabled(),
               bool, 'CSV import button did not become enabled')
    page.locator('#metrics-csv').set_input_files(str(path))
    page.locator('#business-import-form button[type="submit"]').click()
    state = wait_until(
        lambda: ((page.locator('#metrics-status').text_content() or ''),
                 (page.locator('#metrics-error').text_content() or '')),
        lambda value: bool(value[0] or value[1]), 'CSV import returned no status')
    if '已导入 1 行经营数据' not in state[0]:
        raise RuntimeError('CSV import failed: ' + state[1])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit('local Chrome is missing')
    report_dir = args.report_dir.resolve(); report_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix='business-csv-ui-', ignore_cleanup_errors=True) as raw:
        root = Path(raw)
        first_csv = root / '经营报表.csv'
        corrected_csv = root / '经营报表-更正.csv'
        header = 'source,period_start,period_end,scope,clicks,orders,refunds,stock\n'
        first_csv.write_text(header + '商家导出,2026-11-01,2026-11-01,自然流量,,0,0,0\n', encoding='utf-8')
        corrected_csv.write_text(header + '商家导出,2026-11-01,2026-11-01,自然流量,,3,1,0\n', encoding='utf-8')
        store = ConfigStore(root / 'data')
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 1000})
                page.goto(base, wait_until='networkidle')
                page.locator('a[href="#products-panel"]').click()
                page.locator('#product-index').fill('1')
                page.locator('#product-title').fill('经营报表验证商品')
                page.locator('#product-content').fill('仅用于本机 CSV 验证')
                page.locator('#product-form button[type="submit"]').click()
                page.get_by_text('商品已保存').wait_for()

                upload_csv(page, first_csv)
                first_text = page.locator('#metrics-records').text_content() or ''
                for expected in ('点击 未知', '订单 0', '退款 0', '库存 0'):
                    if expected not in first_text:
                        raise RuntimeError('first import lost zero/unknown semantics: ' + first_text)

                page.reload(wait_until='networkidle')
                page.locator('a[href="#products-panel"]').click()
                page.locator('#product-list').select_option(index=1)
                reloaded_text = wait_until(
                    lambda: page.locator('#metrics-records').text_content() or '',
                    lambda value: '点击 未知' in value and '订单 0' in value and '库存 0' in value,
                    'business metrics did not survive browser reload')

                upload_csv(page, corrected_csv)
                corrected_text = wait_until(
                    lambda: page.locator('#metrics-records').text_content() or '',
                    lambda value: '订单 3' in value and '退款 1' in value and '点击 未知' in value,
                    'corrected business metrics were not rendered')
                if page.locator('#metrics-records li').count() != 1:
                    raise RuntimeError('corrected snapshot was duplicated instead of replaced')
                screenshot = report_dir / 'business-csv-corrected.png'
                page.locator('#business-metrics').screenshot(path=str(screenshot))
                browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=5)

    report = {
        'passed': True, 'utf8_file_upload': True, 'reload_preserved_record': True,
        'zero_vs_unknown': {'clicks': 'unknown', 'orders_initial': 0,
                            'refunds_initial': 0, 'closing_stock': 0},
        'correction': {'orders': 3, 'refunds': 1, 'record_count': 1},
        'rendered_after_reload': reloaded_text,
        'rendered_after_correction': corrected_text,
        'screenshot': str(screenshot),
    }
    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
