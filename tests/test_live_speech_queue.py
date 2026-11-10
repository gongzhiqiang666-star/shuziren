import io
import threading
import unittest
import wave

from scripts.live_speech_queue import LiveSpeechQueue,StaleSession


def wav(samples=2400):
    stream=io.BytesIO()
    with wave.open(stream,'wb') as writer:
        writer.setparams((1,2,24000,0,'NONE','not compressed'));writer.writeframes(bytes(samples*2))
    return stream.getvalue()


class SpeechQueueTests(unittest.TestCase):
    def setUp(self):
        self.queue=LiveSpeechQueue(max_items=2,max_seconds=.3,max_utterance_seconds=.2)
        self.binding={'product_id':'p1','product_version':1,'voice_id':'v1','avatar_id':'a1'}
        self.session=self.queue.start(self.binding)

    def test_fifo_bytes_snapshot_and_duration_backpressure(self):
        source=bytearray(wav());first=self.queue.put(self.session,source);source[-1]=1
        second=self.queue.put(self.session,wav(4800))
        with self.assertRaises(TimeoutError):self.queue.put(self.session,wav())
        self.assertEqual(first.pcm[-1],0)
        self.assertEqual(self.queue.take(self.session),first)
        self.assertEqual(self.queue.take(self.session),second)
        self.assertEqual([first.sequence,second.sequence],[0,1])
        self.assertEqual(self.queue.state()['queued_samples'],0)

    def test_restart_flushes_and_rejects_late_results(self):
        packet=self.queue.put(self.session,wav());new=self.queue.start({**self.binding,'product_version':2})
        self.assertFalse(self.queue.is_current(packet.session))
        with self.assertRaises(StaleSession):self.queue.put(self.session,wav())
        with self.assertRaises(StaleSession):self.queue.take(self.session)
        self.assertEqual(self.queue.put(new,wav()).sequence,0)
        self.queue.stop();self.assertFalse(self.queue.is_current(new))

    def test_waiting_producer_wakes_on_stop(self):
        self.queue.put(self.session,wav());self.queue.put(self.session,wav())
        entered=threading.Event();errors=[]
        def produce():
            entered.set()
            try:self.queue.put(self.session,wav(),timeout=5)
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=produce);worker.start();self.assertTrue(entered.wait(1))
        self.queue.stop();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertIsInstance(errors[0],StaleSession)

    def test_invalid_or_truncated_audio_rejected(self):
        with self.assertRaises(ValueError):self.queue.put(self.session,1000000000)
        with self.assertRaises(ValueError):self.queue.put(self.session,wav(4801))
        with self.assertRaisesRegex(ValueError,'Truncated'):self.queue.put(self.session,wav()[:-2])
        self.assertEqual(self.queue.state()['queued_items'],0)

    def test_waiting_producer_accepts_after_consumer_and_empty_consumer_stops(self):
        self.queue.put(self.session,wav());self.queue.put(self.session,wav());accepted=[];entered=threading.Event()
        def produce():
            entered.set();accepted.append(self.queue.put(self.session,wav(),timeout=2))
        worker=threading.Thread(target=produce);worker.start();self.assertTrue(entered.wait(1))
        self.queue.take(self.session);worker.join(1)
        self.assertFalse(worker.is_alive());self.assertEqual(accepted[0].sequence,2)
        self.queue.take(self.session);self.queue.take(self.session)
        errors=[];entered.clear()
        def consume():
            entered.set()
            try:self.queue.take(self.session,timeout=5)
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=consume);worker.start();self.assertTrue(entered.wait(1))
        self.queue.stop();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertIsInstance(errors[0],StaleSession)
