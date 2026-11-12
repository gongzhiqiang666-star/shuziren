"""Scheduling/sink fixtures, not model or encoded-media quality evidence."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import numpy as np
from recovered.image_clone_video_synthesizer import VideoSynthesizer
from scripts.resident_avatar import ResidentAvatar
from scripts.sample_timeline import SampleTimeline
from dataclasses import asdict


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        provider=object.__new__(ResidentAvatar);self.provider=provider
        provider.internal=self.root;provider.sessions=[object()];provider.frame_offset=0;provider.sample_offset=0;provider.timed_mode=None;provider.wenet_loads=0;provider.session='session';provider.prepared=False;provider.prepare_result=None
        synth=object.__new__(VideoSynthesizer);provider.synth=synth
        synth._closed=False;synth.executor=None;synth.batch_size=4;synth.total_frames=7;synth.current_frame_position=0;synth.is_forward=True;synth.wenet_model=None
        synth.engine=SimpleNamespace(perf_stats={'frames':0,'batches':0,'inference_ms':[],'prepare_ms':[],'paste_ms':[]})
        def features(audio):
            if synth.wenet_model is None:synth.wenet_model=object()
            with wave.open(str(audio),'rb') as source:count=source.getnframes()//960
            return [np.zeros((20,256),np.float32) for _ in range(count)]
        synth.extract_audio_features=features
        synth._load_single_frame=lambda index:(np.full((8,8,3),index,np.uint8),{})
        synth._load_batch_frames=lambda indices:([synth._load_single_frame(index)[0] for index in indices],[{} for _ in indices])
        def process(images,metadata,features):
            synth.engine.perf_stats['frames']+=len(images);return images
        synth._process_batch=process;self.addCleanup(synth.close)
        self.written=[]
        captured=self.written
        class Writer:
            def __init__(inner,ffmpeg,output,*_):inner.output=Path(output);inner.output.write_bytes(b'encoded fixture')
            def write(inner,image):captured.append(int(image[0,0,0]))
            def release(inner):pass
            def abort(inner):inner.output.unlink(missing_ok=True)
        self.addCleanup(patch.stopall)
        patch('scripts.raw_video_writer.RawVideoWriter',Writer).start()
        self.verify=patch('scripts.resident_avatar.verify_media',side_effect=lambda *_:{'frames':synth.engine.perf_stats['frames']}).start()

    def audio(self,frames):
        path=self.root/(str(frames)+'.wav');pcm=bytes(frames*960*2)
        with wave.open(str(path),'wb') as output:output.setparams((1,2,24000,0,'NONE','not compressed'));output.writeframes(pcm)
        return path,hashlib.sha256(pcm).hexdigest()

    def test_batch_bound_and_sequence_survive_utterance_boundary(self):
        audio,sha=self.audio(5);first=self.provider.render('session','one',audio,self.root/'one.mp4',sha)
        audio,sha=self.audio(3);second=self.provider.render('session','two',audio,self.root/'two.mp4',sha)
        self.assertEqual(self.written,[0,1,2,3,4,5,6,5])
        self.assertEqual([first['frame_offset'],second['frame_offset'],second['next_frame_offset']],[0,5,8])
        self.assertEqual(first['wenet_identity'],second['wenet_identity']);self.assertEqual(second['wenet_load_count'],1)
        self.assertLessEqual(first['peak_returned_batch'],4)

    def test_stale_session_rejected_and_media_failure_cleans_output(self):
        audio,sha=self.audio(3);output=self.root/'bad.mp4'
        with self.assertRaisesRegex(ValueError,'Stale'):self.provider.render('old','one',audio,output,sha)
        self.assertFalse(output.exists());self.assertEqual(self.written,[])
        self.verify.side_effect=RuntimeError('invalid encoded media')
        with self.assertRaises(RuntimeError):self.provider.render('session','one',audio,output,sha)
        self.assertFalse(output.exists())

    def test_clock_carry_changes_frame_budget_and_rejects_mode_switch(self):
        path=self.root/'fractional.wav';pcm=bytes(5000*2)
        with wave.open(str(path),'wb') as audio:audio.setparams((1,2,24000,0,'NONE','not compressed'));audio.writeframes(pcm)
        sha=hashlib.sha256(pcm).hexdigest();clock=SampleTimeline('session');results=[]
        for index in range(3):
            span=clock.reserve('session',5000)
            results.append(self.provider.render('session',str(index),path,self.root/f'{index}.mp4',sha,timing=asdict(span)))
        self.assertEqual([result['frames'] for result in results],[5,5,6])
        self.assertEqual(self.provider.sample_offset,15000);self.assertEqual(self.provider.frame_offset,16)
        with self.assertRaisesRegex(ValueError,'mix legacy'):
            self.provider.render('session','legacy',path,self.root/'legacy.mp4',sha)

    def test_warmup_is_idempotent_and_preserves_nonzero_positions(self):
        self.provider.frame_offset=31;self.provider.sample_offset=30000
        self.provider.synth.current_frame_position=5;self.provider.synth.is_forward=False
        result=self.provider.prepare();again=self.provider.prepare()
        self.assertEqual(result['warmed_batch_sizes'],[1,2,3,4]);self.assertFalse(result['output_generated'])
        self.assertTrue(again['reused']);self.assertEqual(again['wenet_load_count'],1)
        self.assertEqual((self.provider.frame_offset,self.provider.sample_offset),(31,30000))
        self.assertEqual((self.provider.synth.current_frame_position,self.provider.synth.is_forward),(5,False))
        self.provider.frame_offset=44;self.provider.sample_offset=42000
        current=self.provider.prepare();self.assertEqual((current['frame_offset'],current['sample_offset']),(44,42000))

    def test_failed_warmup_never_declares_ready(self):
        original=self.provider.synth._process_batch
        def fail(images,metadata,features):
            if len(images)==3:raise RuntimeError('GPU warmup fixture failure')
            return original(images,metadata,features)
        self.provider.synth._process_batch=fail
        with self.assertRaisesRegex(RuntimeError,'warmup fixture'):self.provider.prepare()
        self.assertFalse(self.provider.prepared);self.assertIsNone(self.provider.prepare_result)
        self.assertEqual((self.provider.frame_offset,self.provider.sample_offset),(0,0))

    def test_stream_delivers_raw_frames_without_intermediate_media(self):
        audio,sha=self.audio(5);sent=[]
        sink=SimpleNamespace(send=lambda session,task,index,image:sent.append((index,int(image[0,0,0]))),close=lambda:None)
        with self.assertRaisesRegex(ValueError,'Prepare'):self.provider.render('session','one',audio,None,sha,frame_channel=sink)
        self.provider.prepared=True
        progress = []
        load_stages = []
        original_load = self.provider.synth._load_single_frame
        def load_first(index):
            load_stages.append(progress[-1])
            return original_load(index)
        with patch.object(self.provider.synth, '_load_single_frame', side_effect=load_first):
            result=self.provider.render('session','one',audio,None,sha,frame_channel=sink,progress=progress.append)
        self.assertEqual(load_stages[0], {'event': 'speech_stage', 'stage': 'prepare', 'frame_index': 0})
        self.assertEqual(sent,[(0,0),(1,1),(2,2),(3,3),(4,4)])
        self.assertEqual(result['raw_frames_sent'],5);self.assertIsNone(result['output']);self.assertFalse(result['audio_data_sent'])
        self.verify.assert_not_called();self.assertEqual(self.written,[])

    def test_audio_only_span_preserves_samples_without_fabricated_frame(self):
        audio=self.root/'tiny.wav';pcm=bytes(200)
        with wave.open(str(audio),'wb') as output:output.setparams((1,2,24000,0,'NONE','not compressed'));output.writeframes(pcm)
        self.provider.prepared=True;span=SampleTimeline('session').reserve('session',100)
        sink=SimpleNamespace(send=lambda *_:self.fail('Unexpected video frame'),close=lambda:None)
        result=self.provider.render('session','tiny',audio,None,hashlib.sha256(pcm).hexdigest(),timing=asdict(span),frame_channel=sink)
        self.assertEqual(result['frames'],0);self.assertTrue(result['audio_only']);self.assertEqual(self.provider.sample_offset,100)
