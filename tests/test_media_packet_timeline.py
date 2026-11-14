import unittest

from scripts.analyze_media_packet_timeline import summarize


class PacketTimelineTests(unittest.TestCase):
    def test_startup_gap_is_separate_from_settled_timeline(self):
        rows = [
            {'pts_time': '0.000', 'duration_time': '0.020'},
            {'pts_time': '0.035', 'duration_time': '0.020'},
            {'pts_time': '2.000', 'duration_time': '0.020'},
            {'pts_time': '2.021', 'duration_time': '0.020'},
        ]
        result = summarize(rows, settled_after=2.0)
        self.assertEqual(result['largest_delta']['delta_ms'], 1965.0)
        self.assertEqual(result['largest_settled_delta']['delta_ms'], 21.0)
        self.assertEqual(result['non_monotonic'], 0)

    def test_non_monotonic_packets_are_counted(self):
        result = summarize([
            {'pts_time': '1.0', 'duration_time': '.02'},
            {'pts_time': '1.0', 'duration_time': '.02'},
        ])
        self.assertEqual(result['non_monotonic'], 1)


if __name__ == '__main__': unittest.main()
