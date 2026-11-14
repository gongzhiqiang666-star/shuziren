import unittest

from recovered.deduplication_processor import (
    CompositeFrameProcessor,
    DeduplicationFrameProcessor,
)


class _Processor:
    def __init__(self, name, events, error=None):
        self.name = name
        self.events = events
        self.error = error

    def stop(self):
        self.events.append(self.name)
        if self.error:
            raise self.error


class DeduplicationLifecycleTests(unittest.TestCase):
    def test_enabled_overlay_without_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlay video_path"):
            DeduplicationFrameProcessor({"overlay": {"enabled": True}})

    def test_stop_failure_does_not_skip_other_processors(self):
        events = []
        processor = CompositeFrameProcessor([
            _Processor("first", events),
            _Processor("second", events, OSError("close failed")),
            _Processor("third", events),
        ])

        with self.assertRaisesRegex(RuntimeError, "画面去重资源停止失败"):
            processor.stop()

        self.assertEqual(events, ["third", "second", "first"])


if __name__ == "__main__":
    unittest.main()
