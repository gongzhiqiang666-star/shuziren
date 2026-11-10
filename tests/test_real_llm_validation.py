import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts.validate_real_llm import run


class RealLLMValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def test_prepare_does_not_claim_real_generation(self):
        report,root,code=run(self.directory.name,prepare_only=True)
        self.assertEqual(code,0)
        self.assertEqual(report['status'],'prepared-no-network')
        self.assertFalse(report['real_requests_started'])
        self.assertEqual(report['human_review'],'pending')
        self.assertEqual(len(report['products']),2)
        self.assertEqual(json.loads((root/'report.json').read_text(encoding='utf-8')),report)

    def test_missing_config_is_failed_gate_not_success(self):
        with patch.dict(os.environ,{'SHUZIREN_LLM_API_KEY':''}):
            report,root,code=run(self.directory.name)
        self.assertEqual(code,2)
        self.assertEqual(report['status'],'not-passed')
        self.assertFalse(report['real_requests_started'])

    def test_protocol_fixture_cannot_be_accepted_as_real_model(self):
        env={'SHUZIREN_LLM_API_KEY':'not-a-real-secret', 'SHUZIREN_LLM_MODEL':'protocol-fixture-not-a-model',
             'SHUZIREN_LLM_ENDPOINT':'http://127.0.0.1:1/chat/completions'}
        with patch.dict(os.environ,env): report,root,code=run(self.directory.name)
        self.assertEqual(code,2)
        self.assertFalse(report['real_requests_started'])
        self.assertNotIn(env['SHUZIREN_LLM_API_KEY'],(root/'report.json').read_text(encoding='utf-8'))


if __name__=='__main__': unittest.main()
