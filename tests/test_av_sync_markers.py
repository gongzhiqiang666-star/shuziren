import unittest
from scripts.av_sync_markers import analyze_markers,is_flash


class SyncMarkerTests(unittest.TestCase):
    def video(self,missing=()):
        return [(index,index*.04,is_flash(index)) for index in range(15,140) if index not in missing]

    def test_good_sync_and_continuity(self):
        result=analyze_markers(self.video(),[1.01,2.61,4.21])
        self.assertTrue(result['receiver_sync_passed']);self.assertTrue(result['frame_continuity_passed'])

    def test_one_missing_onset_has_explicit_uncertainty_and_no_continuity_pass(self):
        result=analyze_markers(self.video((25,)),[1.01,2.61,4.21])
        self.assertTrue(result['receiver_sync_passed']);self.assertFalse(result['frame_continuity_passed'])
        self.assertEqual(result['missing_frames'],1);self.assertEqual(result['onset_uncertainty_ms'],[40,0,0])

    def test_missing_marker_or_excess_offset_fails(self):
        self.assertFalse(analyze_markers(self.video((25,26,27)),[1.,2.6,4.2])['receiver_sync_passed'])
        self.assertFalse(analyze_markers(self.video(),[1.081,2.6,4.2])['receiver_sync_passed'])
        self.assertFalse(analyze_markers(self.video((25,26)),[.99,2.6,4.2])['receiver_sync_passed'])

    def test_repetition_and_order_preserved_as_failures(self):
        video=self.video();video.insert(3,video[2])
        result=analyze_markers(video,[1.,2.6,4.2])
        self.assertEqual(result['repeated_frames'],1);self.assertFalse(result['frame_continuity_passed'])
