import tempfile
import unittest
import wave
from pathlib import Path
from threading import Lock
from unittest import mock

from recovered.voice_infer_v3 import VoiceSynthesizer, concatenate_pcm_wavs, split_synthesis_text


def write_wav(path, frames, rate=24000, channels=1):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(frames)


class VoiceV3LongTextTests(unittest.TestCase):
    def _synth(self, root, fail_at=None):
        class Model:
            def __init__(self): self.calls = []
            def infer_fast(inner, reference, text, output, verbose=False):
                inner.calls.append(text)
                if fail_at is not None and len(inner.calls) == fail_at:
                    raise RuntimeError("injected inference failure")
                write_wav(output, bytes([len(inner.calls), 0]) * 4)
        synth = VoiceSynthesizer.__new__(VoiceSynthesizer)
        synth._lock = Lock()
        synth.reference_audio = str(Path(root) / "reference.wav")
        Path(synth.reference_audio).write_bytes(b"reference")
        synth.reference_text = "reference"
        synth.voice_id = "voice"
        synth.voice_infer_version = "v3"
        synth.model = Model()
        synth._get_temp_path = lambda: str(root)
        synth._cached = lambda *args: None
        synth._record = mock.Mock()
        return synth

    def test_split_preserves_text_and_bounds_chunks(self):
        text = "第一句。" + "很长的商品介绍，" * 80 + "最后一句！"
        chunks = split_synthesis_text(text, max_chars=60)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(0 < len(chunk) <= 60 for chunk in chunks))
        self.assertEqual("".join(chunks), text)

    def test_hard_split_handles_text_without_punctuation(self):
        text = "测" * 301
        chunks = split_synthesis_text(text, max_chars=100)
        self.assertEqual([len(item) for item in chunks], [100, 100, 100, 1])
        self.assertEqual("".join(chunks), text)

    def test_pcm_concat_preserves_order_and_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            first, second, output = root / "a.wav", root / "b.wav", root / "out.wav"
            write_wav(first, b"\x01\x00" * 3)
            write_wav(second, b"\x02\x00" * 2)
            concatenate_pcm_wavs([first, second], output)
            with wave.open(str(output), "rb") as stream:
                self.assertEqual(stream.getnframes(), 5)
                self.assertEqual(stream.readframes(5), b"\x01\x00" * 3 + b"\x02\x00" * 2)
            mismatch = root / "bad.wav"
            write_wav(mismatch, b"\0\0", rate=16000)
            with self.assertRaisesRegex(ValueError, "参数不一致"):
                concatenate_pcm_wavs([first, mismatch], root / "failed.wav")

    def test_synthesize_merges_chunks_and_cleans_partial_failure(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            synth = self._synth(directory)
            result = synth.synthesize("甲" * 650, use_cache=True)
            self.assertTrue(Path(result).is_file())
            self.assertEqual([len(item) for item in synth.model.calls], [300, 300, 50])
            with wave.open(result, "rb") as stream:
                self.assertEqual(stream.getnframes(), 12)
            synth._record.assert_called_once()
            self.assertFalse(list(directory.glob("*.part-*.wav")))
            failing = self._synth(directory, fail_at=2)
            self.assertIsNone(failing.synthesize("乙" * 650, use_cache=True))
            failing._record.assert_not_called()
            self.assertFalse(list(directory.glob("*.part-*.wav")))
            self.assertFalse(list(directory.glob("*.partial.wav")))


if __name__ == "__main__":
    unittest.main()
