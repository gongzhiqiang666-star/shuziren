import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from scripts.product_store import ProductStore,Conflict,ProductError
from scripts.tts_tasks import TTSTasks
from scripts.voice_store import VoiceStore


class TTSStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.products=ProductStore(self.root)
        self.product=self.products.save(title='测试商品',content='版本一',product_index=8)
        self.script=self.products.add_script(self.product,'状态测试话术')
        self.products.select_script(self.product['id'],self.script)
        self.voices=VoiceStore(self.root);self.voice_id=str(uuid.uuid4())
        directory=self.voices.root/self.voice_id;directory.mkdir()
        (directory/'ref_audio.wav').write_bytes(b'fingerprint-fixture-not-audio')
        (directory/'ref_text.txt').write_text('测试文字',encoding='utf-8')
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        self.audio_hash=sha(directory/'ref_audio.wav');self.text_hash=sha(directory/'ref_text.txt')
        with sqlite3.connect(self.voices.path) as db:
            db.execute('INSERT INTO voices VALUES(?,?,?,?,?,?)',(self.voice_id,'状态测试','测试文字',self.audio_hash,self.text_hash,2))
        self.voices.select(self.voice_id)
        self.tasks=TTSTasks(self.root/'no-runtime',self.root)
        self.addCleanup(self.tasks.close)
        self.tasks.task={'id':'state-fixture','status':'succeeded','product_id':self.product['id'],'product_version':1,
            'script_id':self.script,'voice_id':self.voice_id,'voice_audio_sha256':self.audio_hash,
            'voice_text_sha256':self.text_hash,'result':{'output':'state-fixture-not-an-actual-output'}}

    def test_product_change_invalidates_completed_result(self):
        self.assertEqual(self.tasks.state()['status'],'succeeded')
        self.products.save(title='测试商品',content='版本二',product_index=8,product_id=self.product['id'],version=1)
        state=self.tasks.state();self.assertEqual(state['status'],'failed');self.assertNotIn('result',state)
        self.assertIn('previous_result',state)

    def test_script_selection_change_invalidates_completed_result(self):
        script=self.products.add_script(self.product,'选用第二稿');self.products.select_script(self.product['id'],script)
        self.assertEqual(self.tasks.state()['status'],'failed')

    def test_reference_replacement_invalidates_completed_result(self):
        (self.voices.root/self.voice_id/'ref_text.txt').write_text('替换',encoding='utf-8')
        self.assertEqual(self.tasks.state()['status'],'failed')

    def test_unselected_script_cannot_dispatch_worker(self):
        self.tasks.task=None
        with self.assertRaises(Conflict): self.tasks.start(self.product['id'],'wrong-script',self.voice_id)
        self.assertIsNone(self.tasks.process)

    def test_audio_requires_current_task_owned_path_and_unchanged_hash(self):
        output=self.root/'tts'/'test.wav';output.parent.mkdir(exist_ok=True);content=b'audio-access-fixture'
        output.write_bytes(content)
        self.tasks.task['result']={'output':str(output),'sha256':hashlib.sha256(content).hexdigest()}
        self.assertEqual(self.tasks.audio('state-fixture'),content)
        with self.assertRaises(Conflict): self.tasks.audio('other-task')
        output.write_bytes(b'changed')
        with self.assertRaises(Conflict): self.tasks.audio('state-fixture')
        self.tasks.task['result']['output']=str(self.root/'outside.wav')
        with self.assertRaises(ProductError): self.tasks.audio('state-fixture')

    def test_exclusive_snapshot_and_hash_failure_cleanup(self):
        output=self.root/'tts'/'source.wav';output.parent.mkdir();output.write_bytes(b'snapshot fixture')
        self.tasks.task['result']={'output':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
        target=self.root/'snapshot.wav';state=self.tasks.snapshot_audio('state-fixture',target)
        self.assertEqual(target.read_bytes(),output.read_bytes());self.assertEqual(state['id'],'state-fixture')
        with self.assertRaises(FileExistsError):self.tasks.snapshot_audio('state-fixture',target)
        self.assertEqual(target.read_bytes(),b'snapshot fixture')
        output.write_bytes(b'changed')
        rejected=self.root/'rejected.wav'
        with self.assertRaises(Conflict):self.tasks.snapshot_audio('state-fixture',rejected)
        self.assertFalse(rejected.exists())


if __name__=='__main__': unittest.main()
