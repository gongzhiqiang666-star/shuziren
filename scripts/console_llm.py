"""Explicit console LLM adapter; no implicit legacy credential reads."""
import os
from urllib.parse import urlsplit

from scripts.product_store import Conflict, ProductError, product_prompt_info


class LLMError(ValueError):
    pass


def environment_config(environ=None):
    env = os.environ if environ is None else environ
    config = {key: env.get('SHUZIREN_LLM_' + name, '').strip() for key, name in
              [('endpoint', 'ENDPOINT'), ('api_key', 'API_KEY'), ('model', 'MODEL')]}
    if not all(config.values()):
        raise LLMError('尚未配置控制台LLM，请设置专用地址、模型和API Key')
    try:
        url = urlsplit(config['endpoint'])
        timeout = float(env.get('SHUZIREN_LLM_TIMEOUT', '30'))
        if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
                or url.query or url.fragment or not url.path or not 0 < timeout <= 60):
            raise ValueError()
        if url.scheme == 'http' and url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError()
        if any(ord(c) < 33 or ord(c) > 126 for c in config['api_key']):
            raise ValueError()
    except ValueError:
        raise LLMError('LLM配置无效：使用HTTPS或本机HTTP完整接口地址，超时须在0至60秒内') from None
    config.update(timeout=timeout, allow_redirects=False)
    return config


def status():
    try:
        environment_config()
        return {'configured': True}
    except LLMError:
        return {'configured': False}


def generate(store, product_id, expected_version, instructions='', *, config=None):
    if type(expected_version) is not int or expected_version < 1:
        raise ProductError('请提供有效商品版本')
    if not isinstance(instructions, str) or len(instructions) > 10000:
        raise ProductError('生成要求必须为不超过10000字的文本')
    snapshot = store.get(product_id)
    if snapshot['version'] != expected_version:
        raise Conflict('商品已修改，请重新读取后生成')
    settings = environment_config() if config is None else config
    try:
        from recovered.generate_structured_speech import generate_structured_speech_with_config
        result = generate_structured_speech_with_config(product_prompt_info(snapshot),
                                            instructions, llm_config=settings)
    except Exception:
        # Upstream exceptions can contain URLs, response bodies or credentials.
        raise LLMError('话术生成失败，请检查服务授权、超时及模型返回；未保存话术，可重试') from None
    script_id = store.add_script(snapshot, result, source='llm')
    return {'id': script_id, 'product_id': snapshot['id'], 'product_version': snapshot['version'], 'text': result}
