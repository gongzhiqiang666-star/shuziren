import unittest
from scripts.audio_video_clock import AudioVideoClock


class AudioVideoClockTests(unittest.TestCase):
    def test_bursty_callbacks_do_not_burst_video_after_preroll(self):
        clock=AudioVideoClock(100000000);deadlines=[];origin=10**15
        for index in range(500):
            jitter=(0,18000000,1000000,-1000000)[index%4]
            deadlines.append(clock.deadline(index,origin+index*40000000+jitter))
        self.assertFalse(deadlines[7].tracked);self.assertTrue(deadlines[8].tracked)
        self.assertTrue(all(39900000<=b.due_ns-a.due_ns<=40100000 for a,b in zip(deadlines[8:],deadlines[9:])))
        self.assertLessEqual(len(clock.phases),64)

    def test_phase_follows_slow_device_drift_without_accumulating_delay(self):
        clock=AudioVideoClock(100000000);origin=10**15
        for index in range(20000):last=clock.deadline(index,origin+index*40050000)
        self.assertLess(abs(last.due_ns-(origin+19999*40050000+100000000)),2000000)
        self.assertLess(abs(last.phase_error_ns),100001)

    def test_reordered_frame_and_lost_tracking_fail(self):
        clock=AudioVideoClock(0)
        with self.assertRaises(ValueError):clock.deadline(1,0)
        for index in range(100):clock.deadline(index,10**15+index*40000000)
        with self.assertRaises(RuntimeError):
            for index in range(100,200):clock.deadline(index,10**15+index*40000000+200000000)
