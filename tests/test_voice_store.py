import math
import os
import shutil
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import subprocess

from scripts.voice_store import VoiceStore,VoiceError,fingerprint

FFMPEG=Path(os.environ.get('SHUZIREN_TEST_FFMPEG') or shutil.which('ffmpeg') or '')


@unittest.skipUnless(FFMPEG.is_file(),'Real FFmpeg required for voice normalization tests')
class VoiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=VoiceStore(self.root/'data')

    def audio(self,duration=2,frequency=440):
        source=self.root/('input-%s-%s.wav'%(duration,frequency))
        with wave.open(str(source),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000)
            second=b''.join(struct.pack('<hh',*(2*[int(5000*math.sin(2*math.pi*frequency*i/48000))])) for i in range(48000))
            f.writeframes((second*math.ceil(duration))[:int(48000*duration)*4])
        return source

    def test_real_normalization_pair_selection_reopen_and_source_unchanged(self):
        source=self.audio();before=fingerprint(source)
        a=self.store.import_audio(source,'参考文本甲','音色甲',FFMPEG)
        b=self.store.import_audio(self.audio(frequency=660),'参考文本乙','音色乙',FFMPEG)
        self.assertNotEqual(a['audio_sha256'],b['audio_sha256'])
        self.store.select(b['id']);reopened=VoiceStore(self.root/'data')
        self.assertEqual(reopened.selected(),b['id'])
        self.assertEqual(reopened.get(a['id'])['transcript'],'参考文本甲')
        self.assertEqual(fingerprint(source),before)
        with wave.open(str(self.store.root/a['id']/'ref_audio.wav')) as f:
            self.assertEqual((f.getnchannels(),f.getframerate(),f.getsampwidth()),(1,24000,2))

    def test_invalid_long_short_silent_media_leave_no_registered_or_orphan_voice(self):
        bad=self.root/'bad.wav';bad.write_bytes(b'not audio')
        for source in [bad,self.audio(.2),self.audio(31),self.audio(2,0)]:
            with self.assertRaises(VoiceError): self.store.import_audio(source,'文字','名称',FFMPEG)
        self.assertEqual(self.store.list(),[])
        self.assertEqual([p for p in self.store.root.iterdir() if p.is_dir()],[])

    def test_tamper_and_missing_reference_invalidate_selection(self):
        a=self.store.import_audio(self.audio(),'参考文本','声音',FFMPEG)
        self.store.select(a['id'])
        (self.store.root/a['id']/'ref_text.txt').write_text('被替换的文字',encoding='utf-8')
        with self.assertRaises(VoiceError): self.store.selected()
        with self.assertRaises(VoiceError): self.store.get('../escape')

    def test_empty_fields_do_not_create_voice(self):
        for name,transcript in [('', '文字'),('名称','')]:
            with self.assertRaises(VoiceError): self.store.import_audio(self.audio(),transcript,name,FFMPEG)
        self.assertEqual(self.store.list(),[])

    def test_real_webm_recording_decodes_and_temporary_upload_is_removed(self):
        source=self.audio();webm=self.root/'recorded.webm'
        subprocess.run([str(FFMPEG),'-nostdin','-y','-loglevel','error','-i',str(source),'-c:a','libopus',str(webm)],check=True)
        result=self.store.import_recording(webm.read_bytes(),'测试音，非人声','录音媒体测试',FFMPEG)
        self.assertGreater(result['duration'],1)
        self.assertEqual(list(self.store.root.glob('recording-*.webm')),[])
        with self.assertRaises(VoiceError): self.store.import_recording(b'not media','文字','坏录音',FFMPEG)
        self.assertEqual(list(self.store.root.glob('recording-*.webm')),[])


if __name__=='__main__': unittest.main()
