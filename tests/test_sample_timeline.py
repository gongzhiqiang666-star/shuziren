from dataclasses import asdict,replace
from fractions import Fraction
import random
import threading
import time
import unittest
from scripts.live_speech_queue import StaleSession
from scripts.sample_timeline import SampleTimeline,FramePacer,parse_span,feature_indices


class TimelineTests(unittest.TestCase):
    def test_submit_lead_preserves_pts_and_reports_early_completion(self):
        now=[35000000];clock=FramePacer('one',0,now=lambda:now[0],start_frame=1)
        stamp=clock.wait_for('one',1,submit_lead_ns=6000000)
        self.assertEqual((stamp.pts_ns,stamp.deadline_ns),(40000000,40000000))
        now[0]=39000000;result=clock.presented(stamp)
        self.assertEqual((result['late_ns'],result['early_ns'],result['offset_ns']),(0,1000000,-1000000))
        for lead in [-1,40000000,True]:
            with self.assertRaises(ValueError):clock.wait_for('one',2,submit_lead_ns=lead)

    def test_long_mixed_sequence_has_no_cumulative_rounding_drift(self):
        clock=SampleTimeline('one');random_source=random.Random(314159);samples=frames=0
        for _ in range(20000):
            count=random_source.randrange(100,240000);span=clock.reserve('one',count)
            self.assertEqual((span.sample_start,span.frame_start),(samples,frames))
            samples+=count;frames=span.frame_end
            error=abs(Fraction(frames,25)-Fraction(samples,24000))
            self.assertLessEqual(error,Fraction(1,50))
        self.assertGreater(samples/24000,8*3600)

    def test_fractional_carry_and_audio_only_span(self):
        clock=SampleTimeline('one');first=clock.reserve('one',480);second=clock.reserve('one',480)
        self.assertEqual((first.frames,second.frames),(1,0));self.assertEqual(second.sample_end,960)
        for bad in [0,-1,True,1.2]:
            with self.assertRaises(ValueError):clock.reserve('one',bad)
        clock.stop()
        with self.assertRaises(StaleSession):clock.reserve('one',960)

    def test_tampered_span_and_feature_endpoint_mapping(self):
        span=SampleTimeline('one').reserve('one',78848);self.assertEqual(parse_span(asdict(span)),span)
        with self.assertRaises(ValueError):parse_span(asdict(replace(span,frame_end=span.frame_end+1)))
        self.assertEqual(feature_indices(5,4),[0,1,3,4]);self.assertEqual(feature_indices(5,6),[0,1,2,2,3,4])
        with self.assertRaises(ValueError):feature_indices(5,7)

    def test_presentation_ack_and_deadlines(self):
        now=[0];clock=FramePacer('one',0,now=lambda:now[0])
        stamp=clock.wait_for('one',0)
        with self.assertRaises(ValueError):clock.wait_for('one',1)
        self.assertEqual(clock.presented(stamp)['late_ns'],0)
        now[0]=42000000;stamp=clock.wait_for('one',1)
        self.assertEqual(clock.presented(stamp)['late_ns'],2000000)
        with self.assertRaises(ValueError):clock.presented(stamp)
        clock.stop()
        with self.assertRaises(StaleSession):clock.wait_for('one',2)

    def test_stop_wakes_future_deadline_without_late_ack(self):
        clock=FramePacer('one',time.perf_counter_ns()+5000000000);started=threading.Event();errors=[]
        def wait():
            started.set()
            try:clock.wait_for('one',0)
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=wait);thread.start();self.assertTrue(started.wait(1));clock.stop();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertIsInstance(errors[0],StaleSession)
