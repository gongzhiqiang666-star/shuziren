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


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        provider=object.__new__(ResidentAvatar);self.provider=provider
        provider.internal=self.root;provider.sessions=[object()];provider.frame_offset=0;provider.wenet_loads=0;provider.session='session'
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
