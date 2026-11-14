"""Validate DeepSeek configuration guidance and secret redaction in real Chrome."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=False)
    secret = 'browser-secret-must-not-appear'
    with tempfile.TemporaryDirectory(prefix='llm-status-ui-', ignore_cleanup_errors=True) as temporary:
        server = create_server(ConfigStore(Path(temporary) / 'data'), port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={'width': 1200, 'height': 850})
                with patch.dict(os.environ, {
                    'SHUZIREN_LLM_ENDPOINT': '', 'SHUZIREN_LLM_MODEL': '',
                    'SHUZIREN_LLM_API_KEY': '',
                }):
                    page.goto(base + '/#products-panel', wait_until='networkidle')
                    missing = page.locator('#llm-configured').text_content() or ''
                    if 'DeepSeek 尚未配置' not in missing or 'SHUZIREN_LLM_API_KEY' not in missing:
                        raise RuntimeError(f'missing configuration guidance is incomplete: {missing}')
                    page.locator('#products-panel').screenshot(path=str(report_dir / 'missing.png'))
                with patch.dict(os.environ, {
                    'SHUZIREN_LLM_ENDPOINT': 'https://api.deepseek.com/chat/completions',
                    'SHUZIREN_LLM_MODEL': 'deepseek-chat', 'SHUZIREN_LLM_API_KEY': secret,
                }):
                    page.reload(wait_until='networkidle')
                    configured = page.locator('#llm-configured').text_content() or ''
                    content = page.locator('body').text_content() or ''
                    if 'DeepSeek 已配置' not in configured or 'deepseek-chat' not in configured:
                        raise RuntimeError(f'configured service identity is missing: {configured}')
                    if secret in content or secret in json.dumps(page.evaluate('performance.getEntries().map(x => x.name)')):
                        raise RuntimeError('DeepSeek API key leaked into the browser page or request URLs')
                    page.locator('#products-panel').screenshot(path=str(report_dir / 'configured.png'))
                browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=5)
    report = {
        'passed': True, 'missing_text': missing, 'configured_text': configured,
        'secret_absent_from_page_and_urls': True,
        'screenshots': ['missing.png', 'configured.png'],
    }
    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
