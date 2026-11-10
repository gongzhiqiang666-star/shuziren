import dataclasses
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import wave
from scripts.live_speech_queue import LiveSpeechQueue,SpeechOrigin
from scripts.speech_chunks import iter_wav_chunks
from scripts.speech_assembler import SpeechAssembler


class AssemblerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.assembler=SpeechAssembler(self.root);self.addCleanup(self.assembler.close)
        self.queue=LiveSpeechQueue();self.session=self.queue.start({'product_id':'p','product_version':1,'voice_id':'v','avatar_id':'a'})

    def packets(self,task='one'):
        pcm=bytes(range(256))*25;stream=io.BytesIO()
        with wave.open(stream,'wb') as writer:writer.setparams((1,2,24000,0,'NONE','not compressed'));writer.writeframes(pcm)
        packets=[]
        for chunk in iter_wav_chunks(stream.getvalue(),1200):
            origin=SpeechOrigin(task,'script',chunk.source_sha256,chunk.start_sample,chunk.total_samples,chunk.original_pcm_sha256)
            self.queue.put(self.session,chunk.audio,origin=origin);packets.append(self.queue.take(self.session))
        return packets,pcm

    def test_exact_reconstruction_and_multiple_utterances(self):
        for name in ['first','second']:
            packets,pcm=self.packets(name);utterance=None
            for packet in packets:utterance=self.assembler.push(packet)
            self.assertEqual(utterance.task_id,name);self.assertEqual(utterance.pcm_sha256,hashlib.sha256(pcm).hexdigest())
            with wave.open(str(utterance.path),'rb') as source:self.assertEqual(source.readframes(source.getnframes()),pcm)
            utterance.path.unlink()

    def test_missing_or_duplicate_packet_removes_incomplete_file(self):
        packets,_=self.packets();self.assembler.push(packets[0])
        with self.assertRaises(ValueError):self.assembler.push(packets[0])
        self.assertEqual(list(self.root.glob('*.wav')),[])

    def test_changed_pcm_fingerprint_and_stop_cleanup(self):
        packets,_=self.packets();self.assembler.push(packets[0]);self.assembler.close()
        self.assertEqual(list(self.root.glob('*.wav')),[])
        packets,_=self.packets('third')
        altered=dataclasses.replace(packets[-1],pcm=bytes(len(packets[-1].pcm)))
        for packet in packets[:-1]:self.assembler.push(packet)
        with self.assertRaisesRegex(ValueError,'fingerprint'):self.assembler.push(altered)
        self.assertEqual(list(self.root.glob('*.wav')),[])

    def test_missing_provenance_cleans_existing_partial_audio(self):
        packets,_=self.packets();self.assembler.push(packets[0])
        with self.assertRaises(ValueError):self.assembler.push(dataclasses.replace(packets[1],origin=None))
        self.assertEqual(list(self.root.glob('*.wav')),[])
