import unittest
from unittest.mock import patch

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


if __name__ == '__main__': unittest.main()
