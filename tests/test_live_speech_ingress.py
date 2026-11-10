"""Real stores/WAV handoff with explicit completed-task fixtures, no model claim."""
import hashlib
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import wave
import cv2
import numpy as np

from scripts.avatar_store import AvatarStore
from scripts.live_speech_ingress import LiveSpeechIngress
from scripts.live_speech_queue import LiveSpeechQueue,StaleSession
from scripts.product_store import ProductStore,Conflict
from scripts.tts_tasks import TTSTasks
from scripts.voice_store import VoiceStore


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.products=ProductStore(self.root)
        self.product=self.products.save(title='交接夹具',content='本机测试',product_index=1);self.products.select(self.product['id'])
        self.voices=VoiceStore(self.root);self.voice_id=str(uuid.uuid4());directory=self.voices.root/self.voice_id;directory.mkdir()
        (directory/'ref_audio.wav').write_bytes(self.wav(2400));(directory/'ref_text.txt').write_text('合成夹具',encoding='utf-8')
        self.voice_hashes=[hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ['ref_audio.wav','ref_text.txt']]
        with sqlite3.connect(self.voices.path) as db:db.execute('INSERT INTO voices VALUES(?,?,?,?,?,?)',(self.voice_id,'夹具音色','合成夹具',*self.voice_hashes,.1))
        self.voices.select(self.voice_id)
        source=self.root/'avatar-source';(source/'frames').mkdir(parents=True);(source/'positions').mkdir()
        cv2.imwrite(str(source/'frames/000000.jpg'),np.zeros((32,24,3),np.uint8))
        (source/'positions/000000.txt').write_text('fps: 25\nwidth: 24\nheight: 32\nis_no_face: False\nbounding_box: [2, 20, 3, 22]\n')
        self.avatars=AvatarStore(self.root);self.avatar=self.avatars.import_prepared(source,'交接夹具');self.avatars.select(self.avatar['id'])
        self.tts=TTSTasks(self.root/'no-runtime',self.root);self.addCleanup(self.tts.close)
        self.ingress=LiveSpeechIngress(self.tts,self.avatars,self.root,LiveSpeechQueue(max_items=1,max_seconds=.1,max_utterance_seconds=.1))
        self.addCleanup(self.ingress.stop);self.session=self.ingress.start()

    @staticmethod
    def wav(samples):
        stream=io.BytesIO()
        with wave.open(stream,'wb') as output:
            output.setparams((1,2,24000,0,'NONE','not compressed'))
            output.writeframes((np.arange(samples)%32000).astype('<i2').tobytes())
        return stream.getvalue()

    def complete(self,samples):
        script=self.products.add_script(self.product,'新话术'+str(uuid.uuid4()));self.products.select_script(self.product['id'],script)
        task_id=str(uuid.uuid4());path=self.root/'tts'/(task_id+'.wav');path.parent.mkdir(exist_ok=True);path.write_bytes(self.wav(samples))
        self.tts.task={'id':task_id,'status':'succeeded','product_id':self.product['id'],'product_version':1,
            'script_id':script,'voice_id':self.voice_id,'voice_audio_sha256':self.voice_hashes[0],'voice_text_sha256':self.voice_hashes[1],
            'result':{'output':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
        return task_id,path,script

    def test_snapshot_provenance_and_duplicate_rejection(self):
        task,path,script=self.complete(1200);receipt=self.ingress.capture(task)
        self.assertEqual(receipt['samples'],1200)
        with self.assertRaises(Conflict):self.ingress.capture(task)
        packet=self.ingress.take();self.assertEqual(packet.origin.task_id,task);self.assertEqual(packet.origin.script_id,script)
        self.assertEqual(packet.origin.original_sha256,hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(Conflict):self.ingress.capture(task)
        self.assertEqual(list(self.ingress.root.rglob('*.wav')),[])
        another,_,_=self.complete(1200);self.ingress.capture(another)
        self.assertEqual(self.ingress.take().origin.task_id,another)

    def test_long_audio_backpressure_and_new_task_after_snapshot(self):
        task,path,_=self.complete(6501);self.ingress.capture(task)
        self.assertEqual(self.ingress.state()['queued_items'],1);self.assertEqual(self.ingress.state()['pending_task_id'],task)
        following,_,_=self.complete(1000)
        with self.assertRaises(Conflict):self.ingress.capture(following)
        packets=[self.ingress.take() for _ in range(3)]
        with wave.open(str(path),'rb') as source:original=source.readframes(source.getnframes())
        self.assertEqual(b''.join(packet.pcm for packet in packets),original)
        self.assertEqual([packet.origin.start_sample for packet in packets],[0,2400,4800])
        self.assertEqual(list(self.ingress.root.rglob('*.wav')),[])
        self.ingress.capture(following);self.assertEqual(self.ingress.take().origin.task_id,following)
        with self.assertRaises(Conflict):self.ingress.capture(task)

    def test_product_change_stops_and_removes_pending_snapshot(self):
        task,_,_=self.complete(6501);self.ingress.capture(task)
        self.products.save(title='交接夹具',content='已改版',product_index=1,product_id=self.product['id'],version=1)
        state=self.ingress.state();self.assertEqual(state['status'],'stopped');self.assertEqual(state['queued_items'],0)
        self.assertFalse(self.ingress.queue.is_current(self.session));self.assertEqual(list(self.ingress.root.rglob('*.wav')),[])
        with self.assertRaises(StaleSession):self.ingress.take()

    def test_reference_tamper_invalidates_session(self):
        task,_,_=self.complete(6501);self.ingress.capture(task)
        (self.voices.root/self.voice_id/'ref_text.txt').write_text('更换参考',encoding='utf-8')
        self.assertEqual(self.ingress.state()['status'],'stopped');self.assertEqual(self.ingress.state()['queued_items'],0)

    def test_stop_rejects_late_source_and_cleans_files(self):
        task,_,_=self.complete(6501);self.ingress.capture(task);self.ingress.stop()
        self.assertEqual(list(self.ingress.root.rglob('*.wav')),[])
        with self.assertRaises(StaleSession):self.ingress.capture(task)
        self.assertEqual(self.ingress.state()['queued_items'],0)

    def test_corrupt_source_rejected_without_partial_queue(self):
        task,path,_=self.complete(6501);path.write_bytes(path.read_bytes()[:-2])
        with self.assertRaises(Conflict):self.ingress.capture(task)
        self.assertEqual(list(self.ingress.root.rglob('*.wav')),[]);self.assertEqual(self.ingress.state()['queued_items'],0)

    def test_foreign_product_task_rejected(self):
        task,_,_=self.complete(1200)
        other=self.products.save(title='另一商品',content='不属于场次',product_index=2)
        script=self.products.add_script(other,'另一商品话术');self.products.select_script(other['id'],script)
        self.tts.task.update(product_id=other['id'],script_id=script)
        with self.assertRaises(Conflict):self.ingress.capture(task)
        self.assertEqual(self.ingress.state()['queued_items'],0);self.assertEqual(list(self.ingress.root.rglob('*.wav')),[])

    def test_stream_error_stops_entire_partial_delivery(self):
        task,_,_=self.complete(6501);self.ingress.capture(task)
        self.ingress.pending['iterator'].close()
        def broken():
            raise OSError('simulated snapshot read failure')
            yield
        self.ingress.pending['iterator']=broken()
        with self.assertRaises(OSError):self.ingress.take()
        self.assertEqual(self.ingress.state()['status'],'stopped');self.assertEqual(self.ingress.state()['queued_items'],0)
        self.assertEqual(list(self.ingress.root.rglob('*.wav')),[])
