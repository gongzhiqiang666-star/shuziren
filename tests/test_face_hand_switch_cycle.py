import unittest

from recovered.face_hand_live_manager import FaceHandLiveManager


class _Player:
    def __init__(self):
        self.is_playing = True
        self.face_calls = 0
        self.hand_calls = 0
        self.clears = 0

    def play_face_clip(self):
        self.face_calls += 1
        return f"face-{self.face_calls}"

    def play_hand_clip(self):
        self.hand_calls += 1
        return f"hand-{self.hand_calls}"

    def clear_audio_queues(self):
        self.clears += 1


class FaceHandSwitchCycleTests(unittest.TestCase):
    def test_twenty_product_switches_keep_script_association(self):
        manager = FaceHandLiveManager({})
        manager._player = _Player()
        manager.host_streamer = manager._player
        manager.product_script_groups = [
            {
                "product_index": 10,
                "product_info": "十号商品",
                "items": [{"type": "host", "content": "十号话术", "product_index": 10}],
            },
            {
                "product_index": 20,
                "product_info": "二十号商品",
                "items": [{"type": "host", "content": "二十号话术", "product_index": 20}],
            },
        ]
        manager._product_script_groups = manager.product_script_groups
        manager.get_queue_lengths = lambda: {"normal": 0, "pending_normal": 0}
        emitted = []
        manager._emit_script_item = lambda item: emitted.append(dict(item))

        self.assertTrue(manager._enter_face_phase(0))
        for cycle in range(20):
            expected_group = cycle % 2
            expected_product = (10, 20)[expected_group]
            self.assertEqual(manager.phase, "face")
            self.assertEqual(manager._pending_group, expected_group)

            manager._on_face_done()
            self.assertEqual(manager.phase, "hand")
            self.assertEqual(manager.current_product_index, expected_group)
            manager._tick_broadcast()

            self.assertEqual(emitted[-1]["product_index"], expected_product)
            self.assertEqual(emitted[-1]["content"], ("十号话术", "二十号话术")[expected_group])

        self.assertEqual(len(emitted), 20)
        self.assertEqual(manager._player.face_calls, 21)
        self.assertEqual(manager._player.hand_calls, 20)
        self.assertEqual(manager._player.clears, 21)
        manager._interaction_llm_executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
