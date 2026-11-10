from dataclasses import asdict
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
import wave

from scripts.pcm_timeline import PCMTimeline
from scripts.sample_timeline import SampleTimeline


class PCMTests(unittest.TestCase):
    def test_read_crosses_speech_silence_boundary_without_rounding(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'speech.wav';pcm=b'\x01\x02'*1001
            with wave.open(str(path),'wb') as sound:
                sound.setparams((1,2,24000,0,'NONE','not compressed'));sound.writeframes(pcm)
            events=[];ledger=PCMTimeline('s',events.append);self.addCleanup(ledger.close)
            clock=SampleTimeline('s')
            ledger.append(asdict(clock.reserve('s',1001)),'speech',path,hashlib.sha256(pcm).hexdigest())
            ledger.append(asdict(clock.reserve('s',919)),'idle')
            self.assertEqual(ledger.read(960)+ledger.read(960),pcm+bytes(919*2))
            self.assertEqual([event['samples'] for event in events],[1001,919])
            self.assertEqual(events[0]['pcm_sha256'],hashlib.sha256(pcm).hexdigest())

    def test_close_wakes_blocked_reader(self):
        ledger=PCMTimeline('s');errors=[];started=threading.Event()
        def read():
            started.set()
            try:ledger.read(960,timeout=30)
            except RuntimeError as error:errors.append(str(error))
        thread=threading.Thread(target=read);thread.start();started.wait(1)
        ledger.close();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,['PCM output stopped'])

    def test_bad_hash_and_reordered_span_rejected(self):
        ledger=PCMTimeline('s');self.addCleanup(ledger.close);clock=SampleTimeline('s')
        clock.reserve('s',960)
        with self.assertRaises(ValueError):ledger.append(asdict(clock.reserve('s',960)),'gap')
