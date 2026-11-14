import unittest
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from recovered import runninghub_image


class Response:
    def json(self): return {'code': 0, 'data': {'status': 'RUNNING'}}


class RunningHubImageTests(unittest.TestCase):
    def test_cancel_before_submission_has_no_remote_side_effect(self):
        with patch.object(runninghub_image, 'submit_text_to_image') as submit:
            with self.assertRaises(InterruptedError):
                runninghub_image._generate_and_download_cancellable(
                    api_key='key', prompt='prompt', dest='unused.png', cancel_check=lambda: True)
        submit.assert_not_called()

    def test_cancel_during_poll_stops_before_another_request(self):
        checks = iter((False, True))
        with patch.object(runninghub_image, '_request', return_value=Response()) as request, \
                patch.object(runninghub_image.time, 'sleep') as sleep:
            with self.assertRaises(InterruptedError):
                runninghub_image._poll_task_url_cancellable(
                    api_key='key', task_id='task', poll_interval=5,
                    cancel_check=lambda: next(checks))
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_download_is_https_bounded_validated_and_atomic(self):
        class DownloadResponse:
            def __init__(self, payload, declared=None):
                self.payload = payload
                self.headers = {} if declared is None else {"Content-Length": str(declared)}
                self.closed = False
            def iter_content(self, chunk_size):
                yield self.payload
            def close(self):
                self.closed = True

        buffer = io.BytesIO()
        Image.new("RGB", (3, 2), "green").save(buffer, format="PNG")
        payload = buffer.getvalue()
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "result.png"
            target.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                runninghub_image.download_image("http://example.test/image.png", target)
            invalid = DownloadResponse(b"not-an-image")
            with patch.object(runninghub_image, "_request", return_value=invalid), \
                    self.assertRaises(Exception):
                runninghub_image.download_image("https://example.test/image.png", target)
            self.assertEqual(target.read_bytes(), b"previous")
            oversized = DownloadResponse(payload, declared=101)
            with patch.object(runninghub_image, "MAX_DOWNLOAD_BYTES", 100), \
                    patch.object(runninghub_image, "_request", return_value=oversized), \
                    self.assertRaisesRegex(ValueError, "100 MiB"):
                runninghub_image.download_image("https://example.test/image.png", target)
            self.assertEqual(target.read_bytes(), b"previous")
            valid = DownloadResponse(payload)
            with patch.object(runninghub_image, "_request", return_value=valid):
                self.assertEqual(runninghub_image.download_image(
                    "https://example.test/image.png", target), target)
            self.assertEqual(target.read_bytes(), payload)
            self.assertTrue(valid.closed)
            self.assertEqual(list(Path(root).glob("*.pending")), [])


if __name__ == '__main__': unittest.main()
