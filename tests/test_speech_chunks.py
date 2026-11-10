import hashlib
import io
import unittest
import wave
from scripts.speech_chunks import iter_wav_chunks


def encode(pcm,rate=24000):
    stream=io.BytesIO()
    with wave.open(stream,'wb') as sound:
        sound.setparams((1,2,rate,0,'NONE','not compressed'));sound.writeframes(pcm)
    return stream.getvalue()


class ChunkTests(unittest.TestCase):
    def test_long_audio_exact_pcm_and_provenance(self):
        pcm=(bytes(range(256))*11260)[:(1440000+1201)*2]
        original=encode(pcm);chunks=list(iter_wav_chunks(original));decoded=[]
        for chunk in chunks:
            with wave.open(io.BytesIO(chunk.audio),'rb') as sound:decoded.append(sound.readframes(sound.getnframes()))
            self.assertEqual(chunk.source_sha256,hashlib.sha256(original).hexdigest())
            self.assertEqual(chunk.total_samples,len(pcm)//2)
        self.assertEqual(b''.join(decoded),pcm)
        self.assertEqual([x.start_sample for x in chunks],[0,720000,1440000])
        self.assertEqual(sum(x.samples for x in chunks),len(pcm)//2)

    def test_invalid_tail_rejected_before_first_chunk(self):
        source=encode(bytes(24000*4))[:-2]
        with self.assertRaisesRegex(ValueError,'Truncated'):next(iter_wav_chunks(source,2400))
        with self.assertRaises(ValueError):next(iter_wav_chunks(encode(bytes(240),16000)))
        with self.assertRaises(ValueError):next(iter_wav_chunks(encode(b'')))
