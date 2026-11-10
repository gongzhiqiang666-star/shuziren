"""Actual FFmpeg direct encoding, audio tails, invalid frames and cancellation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave
import numpy as np

from scripts.raw_video_writer import RawVideoWriter
from scripts.avatar_render import verify_media


@unittest.skipUnless(os.environ.get('SHUZIREN_TEST_FFMPEG'),'requires real FFmpeg')
class DirectEncoderTests(unittest.TestCase):
    def test_complete_audio_and_frames(self):
        ffmpeg=Path(os.environ['SHUZIREN_TEST_FFMPEG'])
        encoders=['libx264']+(['h264_nvenc'] if os.environ.get('SHUZIREN_TEST_NVENC')=='1' else [])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for codec in encoders:
                for samples in [9840,16320,97280]:
                    audio=root/'audio.wav'
                    with wave.open(str(audio),'wb') as writer:
                        writer.setparams((1,2,24000,0,'NONE','not compressed'))
                        writer.writeframes((np.sin(np.arange(samples)*.08)*7000).astype('<i2').tobytes())
                    output=root/f'{codec}-{samples}.mp4';frames=round(samples/24000*25)
                    writer=RawVideoWriter(ffmpeg,output,audio,256,256,codec)
                    for index in range(frames):writer.write(np.full((256,256,3),index%256,dtype=np.uint8))
                    writer.release();writer.release()
                    self.assertIsNotNone(writer.process.poll())
                    result=verify_media(audio,output,ffmpeg)
                    self.assertEqual(result['frames'],frames);self.assertTrue(result['audio_complete'])
                    probe=json.loads(subprocess.check_output([str(ffmpeg.with_name('ffprobe.exe')),'-v','error','-show_streams','-of','json',str(output)]))
                    self.assertEqual(probe['streams'][0]['codec_name'],'h264')

    def test_bad_frame_and_abort_reap_process(self):
        ffmpeg=Path(os.environ['SHUZIREN_TEST_FFMPEG'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);audio=root/'audio.wav'
            with wave.open(str(audio),'wb') as sound:
                sound.setparams((1,2,24000,0,'NONE','not compressed'));sound.writeframes(bytes(48000))
            output=root/'cancelled.mp4';writer=RawVideoWriter(ffmpeg,output,audio,64,64,'libx264')
            with self.assertRaisesRegex(ValueError,'BGR frame'):writer.write(np.zeros((8,8,3),dtype=np.uint8))
            writer.abort();writer.abort();self.assertIsNotNone(writer.process.poll());self.assertFalse(output.exists())

    def test_failed_encoder_does_not_leave_result(self):
        ffmpeg=Path(os.environ['SHUZIREN_TEST_FFMPEG'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'failed.mp4'
            writer=RawVideoWriter(ffmpeg,output,root/'missing.wav',64,64,'libx264')
            try:
                with self.assertRaisesRegex(RuntimeError,'encoder failed'):
                    for _ in range(5):writer.write(np.zeros((64,64,3),dtype=np.uint8))
                    writer.release()
            finally:writer.abort()
            self.assertFalse(output.exists());self.assertIsNotNone(writer.process.poll())
