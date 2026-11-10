"""Do not carry green results after changing the corpus, gates or speech code."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.migrate_quality_run import migrate
from scripts.validate_quality_corpus import CORPUS


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'old';self.source.mkdir()
        self.corpus=json.loads(CORPUS.read_text(encoding='utf-8'))

    def seed(self,corpus,hashes=None):
        (self.source/'config.json').write_text(json.dumps({'source_sha256':hashes or {}}))
        (self.source/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False),encoding='utf-8')

    def test_changed_speed_and_thresholds_rejected_before_copy(self):
        changed=copy.deepcopy(self.corpus);changed['items'][0]['speed']=1.5;self.seed(changed)
        with self.assertRaisesRegex(ValueError,'门槛变化'):migrate(self.source,self.root/'out','test')
        changed=copy.deepcopy(self.corpus);changed['thresholds']['max_normalized_cer']=.99;self.seed(changed)
        with self.assertRaises(ValueError):migrate(self.source,self.root/'out','test')
        self.assertFalse((self.root/'out').exists())

    def test_changed_speech_code_rejected_including_windows_hash_keys(self):
        self.seed(self.corpus,{'scripts\\tts_worker.py':'wrong-hash'})
        with self.assertRaisesRegex(ValueError,'语音或评分实现变化'):migrate(self.source,self.root/'out','test')


if __name__=='__main__':unittest.main()
