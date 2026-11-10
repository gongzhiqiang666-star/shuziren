import hashlib
import queue
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import numpy as np
from scripts.live_av_device_sink import AVDeviceSink
from scripts.audio_video_clock import AudioVideoClock


class StopCallback(Exception):pass
class AbortCallback(Exception):pass


class CombinedCallbackTests(unittest.TestCase):
    def test_four_frame_candidate_prefills_on_owner_thread(self):
        sink=self.sink()
        sink.closed=sink.started=False
        sink.buffer_frames=4
        sink.queue=queue.Queue(maxsize=4)
        sink.height,sink.width=32,24
        sink.owner_thread=threading.get_ident()
        sink.stream=Mock()
        sink.samples=sink.peak=0
        sink.pcm_hash=hashlib.sha256()
        image=np.zeros((32,24,3),np.uint8)
        for index in range(3):
            sink.submit(index,image,bytes(1920))
        sink.stream.start.assert_not_called()
        sink.submit(3,image,bytes(1920))
        sink.stream.start.assert_called_once()
        self.assertEqual(sink.peak,4)
        self.assertEqual([sink.queue.get_nowait()[0] for _ in range(4)],list(range(4)))

    def test_sealed_input_rejects_late_packet(self):
        sink=self.sink();sink.closed=False;sink.finish_input()
        with self.assertRaisesRegex(RuntimeError,'input sealed'):
            sink.submit(0,np.zeros((32,24,3),np.uint8),bytes(1920))

    def sink(self):
        sink=AVDeviceSink.__new__(AVDeviceSink)
        sink.sd=SimpleNamespace(CallbackStop=StopCallback,CallbackAbort=AbortCallback)
        sink.queue=queue.Queue(maxsize=2);sink.video_queue=queue.Queue(maxsize=4)
        sink.draining=False;sink.presented=0;sink.underflows=0;sink.error=None;sink.on_present=Mock()
        sink.frames=0;sink.underrun=None;sink.underrun_context=None
        sink.video_delay_ns=100000000;sink.camera=Mock()
        sink.video_clock=AudioVideoClock(sink.video_delay_ns)
        sink.smooth_clock=False
        return sink

    def test_callback_uses_same_frame_pcm_and_schedules_explicit_delay(self):
        sink=self.sink();image=np.zeros((32,24,3),np.uint8);pcm=b'\x01\x02'*960
        sink.video_clock.deadline=Mock(side_effect=AssertionError('Candidate clock must be opt-in'))
        sink.queue.put((0,image,pcm,123));output=bytearray(1920)
        timing=SimpleNamespace(outputBufferDacTime=1.04,currentTime=1.)
        sink._callback(output,960,timing,None)
        self.assertEqual(bytes(output),pcm);self.assertEqual(sink.presented,1)
        index,actual,due=sink.video_queue.get_nowait();event=sink.on_present.call_args.args[0]
        self.assertEqual(index,0);self.assertIs(actual,image)
        self.assertEqual(due-event['callback_ns'],100000000)
        sink.camera.send.assert_not_called()
        sink.video_clock.deadline.assert_not_called()

    def test_underrun_is_failure_not_successful_silence(self):
        sink=self.sink()
        sink.underrun_context=lambda: {'consumer':{'stage':'receive','position':0}}
        with self.assertRaises(AbortCallback):sink._callback(bytearray(1920),960,Mock(),None)
        self.assertEqual(sink.underflows,1);self.assertIn('underrun',sink.error)
        self.assertEqual(sink.presented,0)
        self.assertEqual(sink.underrun['next_frame'],0)
        self.assertEqual(sink.underrun['submitted_frames'],0)
        self.assertGreater(sink.underrun['callback_ns'],0)
        self.assertEqual(sink.underrun['pipeline']['consumer']['stage'],'receive')

    def test_drained_input_stops_cleanly_and_reorder_aborts(self):
        sink=self.sink();sink.draining=True
        with self.assertRaises(StopCallback):sink._callback(bytearray(1920),960,Mock(),None)
        self.assertIsNone(sink.error)
        sink.queue.put((1,np.zeros((32,24,3),np.uint8),bytes(1920),0))
        with self.assertRaises(AbortCallback):sink._callback(bytearray(1920),960,Mock(),None)
        self.assertIn('reordered',sink.error)
