import hashlib
import threading
import time
import unittest

from scripts.streaming_speech import PCMStream, StreamStopped, iter_pcm_provider


class StreamingSpeechTests(unittest.TestCase):
    def test_contiguous_identity_and_final_digest(self):
        stream = PCMStream(max_chunks=4, max_chunk_samples=4, stream_id="fixed")
        source = [b"\x01\x00\x02\x00", b"\x03\x00", b"\x04\x00\x05\x00"]
        state = iter_pcm_provider(source, stream)
        chunks = [stream.take() for _ in source]
        self.assertEqual([item.sequence for item in chunks], [0, 1, 2])
        self.assertEqual([item.start_sample for item in chunks], [0, 2, 3])
        self.assertEqual([item.final for item in chunks], [False, False, True])
        pcm = b"".join(source)
        self.assertEqual(chunks[-1].cumulative_sha256, hashlib.sha256(pcm).hexdigest())
        self.assertEqual(state["pcm_sha256"], hashlib.sha256(pcm).hexdigest())
        self.assertEqual(state["samples"], 5)

    def test_backpressure_does_not_advance_identity(self):
        stream = PCMStream(max_chunks=1, max_chunk_samples=4)
        stream.put(b"\x00\x00", timeout=0)
        with self.assertRaises(TimeoutError):
            stream.put(b"\x01\x00", timeout=0)
        self.assertEqual(stream.state()["next_sequence"], 1)
        stream.take()
        chunk = stream.put(b"\x01\x00", final=True, timeout=0)
        self.assertEqual((chunk.sequence, chunk.start_sample), (1, 1))

    def test_cancel_discards_buffer_and_rejects_late_chunks(self):
        stream = PCMStream(max_chunks=2)
        stream.put(b"\x00\x00")
        stream.stop("cancelled")
        self.assertEqual(stream.state()["queued_chunks"], 0)
        with self.assertRaisesRegex(StreamStopped, "cancelled"):
            stream.take(timeout=0)
        with self.assertRaises(StreamStopped):
            stream.put(b"\x01\x00")

    def test_provider_failure_stops_partial_delivery(self):
        def broken():
            yield b"\x00\x00"
            raise OSError("provider failed")
        stream = PCMStream(max_chunks=2)
        with self.assertRaisesRegex(OSError, "provider failed"):
            iter_pcm_provider(broken(), stream)
        self.assertTrue(stream.state()["stopped"])
        self.assertEqual(stream.state()["queued_chunks"], 0)

    def test_empty_odd_oversized_and_after_final_rejected(self):
        stream = PCMStream(max_chunk_samples=2)
        for value in (b"", b"\x00", bytes(6)):
            with self.assertRaises(ValueError):
                stream.put(value)
        stream.put(bytes(4), final=True)
        with self.assertRaises(StreamStopped):
            stream.put(bytes(2))

    def test_pre_cancelled_provider_emits_nothing(self):
        stopped = threading.Event(); stopped.set()
        stream = PCMStream()
        with self.assertRaisesRegex(StreamStopped, "cancelled"):
            iter_pcm_provider([bytes(2)], stream, stop_event=stopped)
        self.assertEqual(stream.state()["queued_chunks"], 0)

    def test_consumer_releases_blocked_producer_without_timeout(self):
        stream = PCMStream(max_chunks=1)
        first = stream.put(bytes(2))
        completed = []
        producer = threading.Thread(
            target=lambda: completed.append(stream.put(b"\x01\x00", final=True, timeout=1)))
        producer.start()
        time.sleep(0.05)
        self.assertTrue(producer.is_alive())
        self.assertEqual(stream.take(timeout=0.1), first)
        producer.join(1)
        self.assertFalse(producer.is_alive())
        self.assertEqual((completed[0].sequence, completed[0].start_sample), (1, 1))

    def test_stop_wakes_blocked_producer_and_discards_late_chunk(self):
        stream = PCMStream(max_chunks=1)
        stream.put(bytes(2))
        failures = []

        def produce():
            try:
                stream.put(b"\x01\x00", timeout=5)
            except BaseException as error:
                failures.append(error)

        producer = threading.Thread(target=produce)
        producer.start()
        time.sleep(0.05)
        self.assertTrue(producer.is_alive())
        stream.stop("cancelled")
        producer.join(1)
        self.assertFalse(producer.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], StreamStopped)
        self.assertEqual(stream.state()["queued_chunks"], 0)


if __name__ == "__main__":
    unittest.main()
