"""Real FFmpeg mux regression; generated media, no speech/model quality claim."""
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave
import numpy as np

from recovered.image_clone_video_synthesizer import _mux_video_audio
from scripts.avatar_render import verify_media


@unittest.skipUnless(os.environ.get('SHUZIREN_TEST_FFMPEG'),'requires actual FFmpeg')
class TailTests(unittest.TestCase):
    def test_non_frame_aligned_audio_not_shortened(self):
        ffmpeg=Path(os.environ['SHUZIREN_TEST_FFMPEG'])
        previous=os.environ.get('PATH','');os.environ['PATH']=str(ffmpeg.parent)+os.pathsep+previous
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                for samples in [9840,16320,97280]:
                    audio=root/f'{samples}.wav';duration=samples/24000
                    with wave.open(str(audio),'wb') as writer:
                        writer.setparams((1,2,24000,0,'NONE','not compressed'))
                        writer.writeframes((np.sin(np.arange(samples)*2*math.pi*440/24000)*8000).astype('<i2').tobytes())
                    video=root/f'{samples}-silent.mp4'
                    subprocess.run([str(ffmpeg),'-nostdin','-y','-v','error','-f','lavfi','-i',
                        'color=c=black:s=64x64:r=25','-frames:v',str(round(duration*25)),str(video)],check=True,timeout=30)
                    output=root/f'{samples}.mp4';_mux_video_audio(video,audio,output)
                    decoded=root/'decoded.wav'
                    subprocess.run([str(ffmpeg),'-nostdin','-y','-v','error','-i',str(output),
                        '-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(decoded)],check=True,timeout=30)
                    with wave.open(str(decoded)) as reader:self.assertGreaterEqual(reader.getnframes(),samples)
                    self.assertTrue(verify_media(audio,output,ffmpeg)['audio_complete'])
        finally:os.environ['PATH']=previous


if __name__=='__main__':unittest.main()
