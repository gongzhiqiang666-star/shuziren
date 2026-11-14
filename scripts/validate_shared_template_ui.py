"""Validate cross-shop preparation templates through two real Chrome pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
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


def create_product(page, index: str, title: str, content: str) -> None:
    page.locator('a[href="#products-panel"]').click()
    page.locator('#product-index').fill(index)
    page.locator('#product-title').fill(title)
    page.locator('#product-content').fill(content)
    page.locator('#product-form button[type="submit"]').click()
    message = wait_until(
        lambda: ((page.locator('#product-message').text_content() or ''),
                 (page.locator('#product-error').text_content() or '')),
        lambda value: bool(value[0] or value[1]), 'product save returned no status')
    if '商品已保存' not in message[0]:
        raise RuntimeError('product save failed: ' + message[1])


def save_preparation(page, values: dict[str, str]) -> None:
    page.locator('a[href="#preparation-panel"]').click()
    checkbox = page.locator('#preparation-products input[type="checkbox"]')
    checkbox.first.check()
    for field, value in values.items():
        page.locator('#preparation-' + field).fill(value)
    page.locator('#preparation-form button[type="submit"]').click()
    wait_until(lambda: page.locator('#preparation-status').text_content(),
               lambda value: bool(value and '草稿已保存' in value),
               'preparation draft was not saved')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit('local Chrome is missing')
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix='shared-template-ui-', ignore_cleanup_errors=True) as raw:
        root = Path(raw) / 'data'
        servers = []
        workers = []
        bases = []
        for shop_id in ('first', 'second'):
            store = ConfigStore(shop_data_directory(root, shop_id))
            server = create_server(store, port=0, shop_id=shop_id)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            servers.append(server); workers.append(worker)
            bases.append(f'http://127.0.0.1:{server.server_port}')
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                first = browser.new_page(viewport={'width': 1280, 'height': 1000})
                second = browser.new_page(viewport={'width': 1280, 'height': 1000})
                first.goto(bases[0], wait_until='networkidle')
                second.goto(bases[1], wait_until='networkidle')

                create_product(first, '1', '一店青瓷杯', '一店活动 99 元，库存 12')
                save_preparation(first, {
                    'goal': '提高讲解清晰度', 'audience': '新客',
                    'promotion': '一店满减 99 元', 'stock': '一店库存 12',
                    'shipping': '一店当日发货', 'constraints': '先讲使用场景',
                })
                first.locator('#preparation-template-name').fill('新客讲解结构')
                first.locator('#preparation-template-save').click()
                first.get_by_text('已保存通用模板；商品和本店经营事实未写入模板').wait_for()

                create_product(second, '2', '二店亚麻桌布', '二店赠品活动，库存 88')
                save_preparation(second, {
                    'goal': '旧目标', 'audience': '老客',
                    'promotion': '二店赠品活动', 'stock': '二店库存 88',
                    'shipping': '二店次日发货', 'constraints': '旧限制',
                })
                # Templates are shared by the installation, so reload their list after first-shop save.
                second.reload(wait_until='networkidle')
                second.locator('a[href="#preparation-panel"]').click()
                second.locator('#preparation-template-list').select_option(label='新客讲解结构')
                second.locator('#preparation-template-apply').click()
                second.get_by_text('已应用「新客讲解结构」；本店商品、活动、库存和发货条件保持不变').wait_for()

                fields = {name: second.locator('#preparation-' + name).input_value()
                          for name in ('goal', 'audience', 'promotion', 'stock', 'shipping', 'constraints')}
                checked = second.locator('#preparation-products input[type="checkbox"]:checked').count()
                product_text = second.locator('#preparation-products').text_content() or ''
                expected = {
                    'goal': '提高讲解清晰度', 'audience': '新客',
                    'promotion': '二店赠品活动', 'stock': '二店库存 88',
                    'shipping': '二店次日发货', 'constraints': '先讲使用场景',
                }
                if fields != expected or checked != 1 or '二店亚麻桌布' not in product_text:
                    raise RuntimeError(json.dumps({
                        'fields': fields, 'checked': checked, 'products': product_text,
                    }, ensure_ascii=False))
                if '一店青瓷杯' in product_text or '99' in json.dumps(fields, ensure_ascii=False):
                    raise RuntimeError('first-shop facts leaked into the second-shop preparation')
                screenshot = report_dir / 'second-shop-template-applied.png'
                second.locator('#preparation-panel').screenshot(path=str(screenshot))
                browser.close()

            template_path = root / 'shared-preparation-templates.sqlite3'
            with sqlite3.connect(template_path) as database:
                stored_name, stored_body = database.execute(
                    'SELECT name, body FROM preparation_templates').fetchone()
            template_text = stored_name + stored_body
            if any(secret in template_text for secret in ('一店青瓷杯', '99 元', '库存 12', '当日发货')):
                raise RuntimeError('shop facts were persisted in the shared template file')
            report = {
                'passed': True,
                'shops': ['first', 'second'],
                'template_shared': True,
                'second_shop_fields': fields,
                'second_shop_product_preserved': True,
                'source_shop_facts_absent': True,
                'template_file': str(template_path),
                'screenshot': str(screenshot),
            }
        finally:
            for server in servers:
                server.shutdown(); server.server_close()
            for worker in workers:
                worker.join(timeout=5)

    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
