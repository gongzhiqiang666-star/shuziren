from pathlib import Path
import tempfile
import unittest

from recovered.voice_infer_v3 import VoiceSynthesizer


class CaptureSynthesizer(VoiceSynthesizer):
    def __init__(self, models_base_path, reference_audio, reference_text, device='cuda',voice_id=None,voice_infer_version=None):
        self.audio=Path(reference_audio)
        self.text=reference_text
        self.voice_id=voice_id


class VoiceReferenceTests(unittest.TestCase):
    def test_selected_voice_does_not_use_root_or_other_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,text in [('', 'root-decoy'),('speaker-a','first voice'),('speaker-b','second voice')]:
                target=root/name;target.mkdir(exist_ok=True)
                (target/'ref_audio.wav').write_bytes(text.encode())
                (target/'ref_text.txt').write_text(text,encoding='utf-8')
            for name in ['speaker-a','speaker-b']:
                synth=CaptureSynthesizer.from_voice_dir(str(root/'models'),str(root),name)
                self.assertEqual(synth.audio,root/name/'ref_audio.wav')
                self.assertEqual(synth.text,{'speaker-a':'first voice','speaker-b':'second voice'}[name])
                self.assertEqual(synth.voice_id,name)

    def test_missing_selected_voice_does_not_fall_back_to_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'ref_audio.wav').write_bytes(b'decoy')
            with self.assertRaises(FileNotFoundError):
                CaptureSynthesizer.from_voice_dir(str(root),str(root),'missing')


if __name__=='__main__': unittest.main()
