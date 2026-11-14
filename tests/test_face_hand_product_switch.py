import unittest
from unittest.mock import Mock

import numpy as np

from recovered.face_hand_live_manager import FaceHandLiveManager
from recovered.face_hand_player import FaceHandVideoStreamManager


class FaceHandProductSwitchTests(unittest.TestCase):
    def test_clearing_queues_discards_active_previous_product_audio(self):
        player = FaceHandVideoStreamManager(face_videos=[], hand_videos=[])
        player._load_tts = lambda _path: np.arange(8, dtype=np.float32)
        player.add_audio_to_queue("product-1.wav", queue_name="normal")

        first, path = player._take_tts(2)
        self.assertEqual(path, "product-1.wav")
        self.assertTrue(np.array_equal(first, np.array([0, 1], dtype=np.float32)))
        self.assertEqual(player._tts_samples.size, 6)

        player.clear_audio_queues()
        silence, path = player._take_tts(2)

        self.assertIsNone(path)
        self.assertTrue(np.array_equal(silence, np.zeros(2, dtype=np.float32)))
        self.assertEqual(player._tts_samples.size, 0)

    def test_product_phase_clear_removes_stale_audio_mapping(self):
        manager = FaceHandLiveManager({})
        manager._player = Mock()
        manager._audio_product_map = {"old.wav": 7}
        manager._enqueue_tts("old queued", product_index=7)

        manager._clear_normal_queues()

        self.assertEqual(manager._audio_product_map, {})
        self.assertEqual(manager._pending_audio["normal"], 0)
        manager._player.clear_audio_queues.assert_called_once_with()
        manager._interaction_llm_executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
