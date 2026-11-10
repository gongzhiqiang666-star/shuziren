import threading
import unittest
import numpy as np
from scripts.live_frame_channel import FrameReceiver,FrameSender


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.receiver=FrameReceiver('session',16,16,capacity=1);self.addCleanup(self.receiver.close)

    def test_raw_pixels_order_and_credit_backpressure(self):
        sender=FrameSender(self.receiver.descriptor());self.addCleanup(sender.close)
        first=threading.Event();second=threading.Event();errors=[]
        def produce():
            try:
                sender.send('session','task',0,np.full((16,16,3),37,np.uint8));first.set()
                sender.send('session','task',1,np.full((16,16,3),91,np.uint8));second.set()
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=produce);worker.start();self.assertTrue(first.wait(1));self.assertFalse(second.wait(.05))
        frame=self.receiver.take();self.assertEqual(frame.frame_index,0);self.assertTrue(np.all(frame.image==37));self.assertFalse(frame.image.flags.writeable)
        self.assertTrue(second.wait(1));next_frame=self.receiver.take();worker.join(1)
        self.assertEqual(next_frame.frame_index,1);self.assertTrue(np.all(next_frame.image==91));self.assertFalse(errors)
        self.assertLessEqual(self.receiver.peak,1)

    def test_stop_releases_blocked_producer(self):
        sender=FrameSender(self.receiver.descriptor());self.addCleanup(sender.close);ready=threading.Event();errors=[]
        def produce():
            try:
                sender.send('session','task',0,np.zeros((16,16,3),np.uint8));ready.set()
                sender.send('session','task',1,np.zeros((16,16,3),np.uint8))
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=produce);worker.start();self.assertTrue(ready.wait(1));self.receiver.close();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors)
        with self.assertRaises(RuntimeError):self.receiver.take()

    def test_wrong_session_and_token_are_rejected(self):
        sender=FrameSender(self.receiver.descriptor());self.addCleanup(sender.close)
        sender.send('old-session','task',0,np.zeros((16,16,3),np.uint8))
        with self.assertRaises(ValueError):self.receiver.take()
        another=FrameReceiver('session',16,16);self.addCleanup(another.close)
        descriptor=another.descriptor();descriptor['token']='00'*32
        unauthorized=FrameSender(descriptor);self.addCleanup(unauthorized.close)
        with self.assertRaises(PermissionError):another.take()
