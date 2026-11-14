import unittest

from recovered.record_live_manager import RecordLiveManager


class _Resource:
    def __init__(self, error=None):
        self.error = error
        self.stops = 0

    def stop(self):
        self.stops += 1
        if self.error:
            raise self.error


class RecordLiveLifecycleTests(unittest.TestCase):
    def test_player_failure_does_not_skip_ingest_or_announcement_cleanup(self):
        manager = RecordLiveManager({})
        player = _Resource(OSError("player close failed"))
        ingest = _Resource()
        manager.video_player = player
        manager.stream_ingest = ingest
        manager.is_broadcasting = True
        manager.announcement_session = {
            "is_active": True,
            "temp_files": [],
            "worker_thread": object(),
        }

        self.assertFalse(manager.stop_live())

        self.assertEqual(player.stops, 1)
        self.assertEqual(ingest.stops, 1)
        self.assertFalse(manager.announcement_session["is_active"])
        self.assertIsNone(manager.video_player)
        self.assertIsNone(manager.stream_ingest)
        self.assertFalse(manager.is_broadcasting)
        self.assertEqual(
            manager.last_error,
            "停止录播直播时发生错误: player close failed",
        )

    def test_inactive_broadcast_still_cleans_active_announcement(self):
        manager = RecordLiveManager({})
        manager.is_broadcasting = False
        manager.announcement_session = {
            "is_active": True,
            "temp_files": [],
            "worker_thread": object(),
        }

        self.assertTrue(manager.stop_live())
        self.assertFalse(manager.announcement_session["is_active"])
        self.assertIsNone(manager.announcement_session["worker_thread"])


if __name__ == "__main__":
    unittest.main()
