import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recovered import face_hand_vad_split as vad


class FaceHandVadContractTests(unittest.TestCase):
    def test_original_defaults_and_random_hand_planning(self):
        signature = inspect.signature(vad.clip_face_hand_video_group)
        self.assertEqual({name: signature.parameters[name].default for name in (
            'min_clip_ms', 'max_clip_ms', 'face_keep_min_ms',
            'rms_silence_thres', 'merge_gap_ms')}, {
                'min_clip_ms': 20000, 'max_clip_ms': 30000, 'face_keep_min_ms': 15000,
                'rms_silence_thres': 200.0, 'merge_gap_ms': 1200,
            })
        self.assertEqual((vad.FRAME_MS, vad.TARGET_SAMPLE_RATE, vad.VAD_SAMPLE_RATE, vad._CUT_WORKERS),
                         (40, 48000, 16000, 4))
        with patch.object(vad.random, 'randint', return_value=656) as randint:
            self.assertEqual(vad.plan_hand_random_segments(1200, min_ms=400, max_ms=800),
                             [(0, 656), (656, 1200)])
            self.assertEqual(vad._split_long_segment(0, 1200, min_ms=400, max_ms=800),
                             [(0, 656), (656, 1200)])
        self.assertEqual(randint.call_args_list[-1].args, (400, 800))

    def test_manifest_v2_and_return_shape_match_original_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.mp4'
            source.write_bytes(b'fixture')
            output = root / 'output'

            def cut(_source, _start, _end, target):
                path = Path(target)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'clip')

            with (patch.object(vad, '_probe_duration_ms', return_value=1200),
                  patch.object(vad, '_extract_wav_16k'),
                  patch.object(vad, 'plan_face_vad_segments', return_value=[(0, 480), (480, 1200)]),
                  patch.object(vad, 'plan_hand_random_segments', return_value=[(0, 656), (656, 1200)]),
                  patch.object(vad, '_cut_clip', side_effect=cut)):
                result = vad.clip_face_hand_video_group(
                    str(source), str(source), output_dir=output, min_clip_ms=400,
                    max_clip_ms=800, face_keep_min_ms=200, rms_silence_thres=.001)

            self.assertEqual(set(result), {'status', 'output_dir', 'face_count', 'hand_count',
                                           'face', 'hand', 'manifest'})
            self.assertEqual((result['status'], result['face_count'], result['hand_count']),
                             ('success', 2, 2))
            self.assertTrue(all(Path(path).is_absolute() for path in result['face'] + result['hand']))
            manifest = result['manifest']
            self.assertEqual(json.loads((output / 'manifest.json').read_text(encoding='utf-8')), manifest)
            self.assertEqual(manifest['version'], 2)
            self.assertRegex(manifest['created_at'], r'^\d{8}_\d{6}$')
            self.assertEqual(manifest['normalize'], {
                'fps': 25, 'sample_rate': 48000, 'width': 1080, 'height': 1920,
                'audio_channels': 1, 'pixel_format': 'yuv420p',
            })
            self.assertEqual(manifest['face'], ['face/face_001.mp4', 'face/face_002.mp4'])
            self.assertEqual(manifest['hand'], ['hand/hand_001.mp4', 'hand/hand_002.mp4'])
            self.assertEqual(manifest['details']['face']['segments'][0], {
                'start_ms': 0, 'end_ms': 480, 'duration_ms': 480, 'path': 'face/face_001.mp4',
            })
            self.assertEqual(manifest['details']['hand']['segments'][0], {
                'start_ms': 0, 'end_ms': 656, 'duration_ms': 656, 'path': 'hand/hand_001.mp4',
            })


if __name__ == '__main__':
    unittest.main()
