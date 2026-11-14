import unittest
from unittest import mock

from recovered import local_voice


class FakeSynthesizer:
    calls = []
    cleared = 0

    @classmethod
    def from_voice_dir(cls, **kwargs):
        cls.calls.append(("create", kwargs))
        return cls()

    def synthesize(self, **kwargs):
        self.calls.append(("synthesize", kwargs))
        return "audio.wav"

    def clear(self):
        type(self).cleared += 1


class MultilingualVoiceRoutingTests(unittest.TestCase):
    def setUp(self):
        FakeSynthesizer.calls = []
        FakeSynthesizer.cleared = 0

    def test_malay_and_vietnamese_use_resident_omnivoice_with_language(self):
        module = mock.Mock(VoiceSynthesizer=FakeSynthesizer)
        config = {"models_base_path": "models", "voice_base_dir": "voices", "device": "cuda"}
        with mock.patch.object(local_voice, "import_module", return_value=module) as importer:
            for version, language in (("malai_local", "ms-MY"), ("vietnam_local", "vi-VN")):
                self.assertEqual(local_voice.synthesize_local_audio(config, "voice", "text", 1.1, version), "audio.wav")
                self.assertEqual(FakeSynthesizer.calls[-1][1]["language"], language)
                self.assertEqual(importer.call_args.args[0], "bin.voice_infer_v2.infer_api")
        self.assertEqual(FakeSynthesizer.cleared, 2)

    def test_existing_versions_keep_their_provider_and_no_forced_language(self):
        module = mock.Mock(VoiceSynthesizer=FakeSynthesizer)
        config = {"voice_base_dir": "voices"}
        with mock.patch.object(local_voice, "import_module", return_value=module) as importer:
            local_voice.synthesize_local_audio(config, "voice", "text", 1.0, "v1")
        self.assertEqual(importer.call_args.args[0], "bin.voice_infer.infer_api")
        self.assertIsNone(FakeSynthesizer.calls[-1][1]["language"])


if __name__ == "__main__":
    unittest.main()
