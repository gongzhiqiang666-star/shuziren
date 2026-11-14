import os
import subprocess
import time
import unittest
import urllib.request
from pathlib import Path

from recovered.srs_runtime import start_bundled_srs, stop_srs_process


@unittest.skipUnless(os.environ.get("SHUZIREN_RUN_SRS_INTEGRATION") == "1", "requires bundled Windows SRS")
class SrsIntegrationTests(unittest.TestCase):
    def test_real_push_and_http_flv_pull(self):
        runtime = Path(os.environ["SHUZIREN_SRS_RUNTIME"])
        ffmpeg = Path(os.environ["SHUZIREN_FFMPEG"])
        process = start_bundled_srs(runtime)
        self.assertIsNotNone(process)
        publisher = None
        try:
            with urllib.request.urlopen("http://127.0.0.1:1985/api/v1/versions", timeout=3) as response:
                self.assertEqual(response.status, 200)
            publisher = subprocess.Popen([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-re",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
                "-t", "5", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-c:a", "aac", "-f", "flv", "rtmp://127.0.0.1/live/integration",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            time.sleep(1.5)
            pull = subprocess.run([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-rw_timeout", "5000000",
                "-i", "http://127.0.0.1:8080/live/integration.flv", "-t", "1", "-f", "null", "NUL",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(pull.returncode, 0, pull.stderr.decode("utf-8", "replace"))
            publisher_code = publisher.poll()
            if publisher_code is not None:
                self.assertEqual(publisher_code, 0, publisher.stderr.read().decode("utf-8", "replace"))
        finally:
            if publisher is not None and publisher.poll() is None:
                publisher.terminate()
                publisher.wait(timeout=5)
            if publisher is not None and publisher.stderr is not None:
                publisher.stderr.close()
            stop_srs_process(process)
        self.assertIsNotNone(process.poll())


if __name__ == "__main__":
    unittest.main()
