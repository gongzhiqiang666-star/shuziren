"""Browser validation for preparation preview, re-review, rotation handoff and report."""

import argparse
import json
from pathlib import Path
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore


def wait_text(page, selector, expected, timeout=10_000):
    page.locator(selector).filter(has_text=expected).wait_for(timeout=timeout)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-dir', type=Path, required=True)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit('local Chrome is missing')
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='preparation-ui-', ignore_cleanup_errors=True) as temporary:
        data = Path(temporary) / 'data'
        ConfigStore(data).save({'version': 1, 'runtime_root': '', 'port': 5158})
        store = ProductStore(data)
        product = store.save(title='青瓷杯', content='530毫升青瓷杯，青绿色。', product_index=1,
                             product_facts={'容量': {'status': 'verified', 'value': '530毫升',
                                                       'source': '商品标签'}})
        first_script = store.add_script(product, '青瓷材质，530毫升容量，装水泡茶都够用。')
        store.select_script(product['id'], first_script)

        server = create_server(ConfigStore(data), port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 1000})
                page.goto(base, wait_until='networkidle')
                page.locator('a[href="#preparation-panel"]').click()
                checkbox = page.locator('#preparation-products input[value="' + product['id'] + '"]')
                checkbox.check()
                values = {
                    'goal': '完成青瓷杯讲解', 'audience': '喜欢喝茶的用户',
                    'promotion': '无未核实优惠', 'stock': '库存已核对',
                    'shipping': '48小时内发货', 'constraints': '不编造价格',
                }
                for name, value in values.items():
                    page.locator('#preparation-' + name).fill(value)
                page.locator('#preparation-form button[type="submit"]').click()
                wait_text(page, '#preparation-status', '条件已填齐')
                page.locator('#preparation-preview').click()
                page.locator('#preparation-package-panel').wait_for(state='visible')
                initial_review = page.locator('#preparation-package').input_value()
                if '青瓷杯' not in initial_review or first_script not in initial_review:
                    raise RuntimeError('prepared package did not show the selected product and script')
                page.locator('#preparation-package').fill(initial_review + '\n人工审阅：不编造价格。')
                page.locator('#preparation-review-save').click()
                wait_text(page, '#preparation-status', '审阅稿已保存')
                page.locator('#preparation-apply').click()
                wait_text(page, '#preparation-status', '已载入轮播顺序')

                current = store.get(product['id'])
                replacement = store.add_script(current, '青瓷材质，530毫升，本场仅介绍已核实信息。')
                store.select_script(product['id'], replacement)
                page.locator('#preparation-apply').click()
                wait_text(page, '#preparation-error', '已变化')
                stale_error = page.locator('#preparation-error').text_content()

                page.locator('#preparation-preview').click()
                page.locator('#preparation-package').fill(
                    page.locator('#preparation-package').input_value() + '\n人工重新审阅通过。')
                page.locator('#preparation-review-save').click()
                wait_text(page, '#preparation-status', '审阅稿已保存')
                page.locator('#preparation-apply').click()
                wait_text(page, '#preparation-status', '已载入轮播顺序')

                package = store.build_live_preparation()
                store.record_live_session('browser-preparation-scene', time.time(), started_at=time.time(),
                                          ended_at=time.time() + 1, status='stopped', frames=25)
                store.record_preparation_application('browser-preparation-scene',
                    store.live_preparation_rotation(package['revision'], include_improvements=True))
                store.record_rotation_completion('browser-preparation-scene', 'spoken-1',
                    package['items'][0], 0, sample_start=0, sample_end=24000)

                page.locator('#live-event-refresh').click()
                page.locator('#live-event-scene').select_option('browser-preparation-scene')
                page.locator('#live-report').click()
                try:
                    wait_text(page, '#live-report-output', package['revision'])
                except Exception as error:
                    raise RuntimeError('session report UI failed: ' + json.dumps({
                        'output': page.locator('#live-report-output').text_content(),
                        'live_error': page.locator('#live-error').text_content(),
                        'selected_session': page.locator('#live-event-scene').input_value(),
                        'report_disabled': page.locator('#live-report').is_disabled(),
                    }, ensure_ascii=False)) from error
                report_text = page.locator('#live-report-output').text_content()
                if replacement not in report_text or package['revision'] not in report_text:
                    raise RuntimeError('session report did not preserve the reviewed script and frame count')
                screenshot = report_dir / 'preparation-review-report.png'
                page.screenshot(path=str(screenshot), full_page=True)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    result = {
        'passed': True,
        'prepared_package_previewed': True,
        'initial_review_saved_and_loaded': True,
        'stale_review_rejected': True,
        'stale_error': stale_error,
        'replacement_script_id': replacement,
        'replacement_reviewed_and_loaded': True,
        'session_report_verified': True,
        'screenshot': str(screenshot),
    }
    (report_dir / 'result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
