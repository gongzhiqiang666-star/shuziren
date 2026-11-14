import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from recovered import runninghub_ltx as ltx


class Response:
    def __init__(self, body): self.body = body
    def raise_for_status(self): return None
    def json(self): return self.body


class RunningHubLTXTests(unittest.TestCase):
    def test_resolution_instance_and_v179_request_contract(self):
        self.assertEqual([ltx.normalize_ltx_res(value) for value in
                          (480, '480p', 720, '720p', 1080, '1080p', 'bad', None)],
                         ['480p', '480p', '720p', '720p', '1080p', '1080p', '480p', '480p'])
        self.assertEqual([ltx.resolve_ltx_long_edge(value) for value in (480, 720, 1080, 864, 1280, 1536)],
                         [864, 1280, 1536, 864, 1280, 1536])
        self.assertEqual([ltx.default_ltx_instance(value, True) for value in (864, 1280, 1536)],
                         ['default', 'default', 'plus'])
        with patch.object(ltx.requests, 'post', return_value=Response(
                {'code': 0, 'data': {'taskId': 'task-1'}})) as post:
            task = ltx.create_ltx_task(api_key='request-only-key', image_remote='image.png',
                audio_remote='audio.wav', prompt='prompt', duration_s=6.5)
        self.assertEqual(task, 'task-1')
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://www.runninghub.cn/task/openapi/ai-app/run')
        payload = kwargs['json']
        self.assertEqual((payload['webappId'], payload['instanceType']),
                         ('2031016553440878594', 'plus'))
        self.assertNotIn('retainSeconds', payload)
        self.assertEqual([(item['nodeId'], item['fieldName'], item['fieldValue'])
                          for item in payload['nodeInfoList']], [
            ('444', 'image', 'image.png'), ('1755', 'audio', 'audio.wav'),
            ('1583', 'value', '0'), ('1776', 'value', '0'),
            ('1624', 'value', '保持镜头稳定，双手手持商品讲解'),
            ('1606', 'value', '864'), ('1586', 'value', '25.0')])

    def test_generation_uploads_once_supports_low_cost_and_cancel(self):
        with tempfile.TemporaryDirectory() as directory:
            image, audio, output = (Path(directory) / name for name in ('image.png', 'audio.wav', 'video.mp4'))
            image.write_bytes(b'image'); audio.write_bytes(b'audio')
            def download(_url, dest): Path(dest).write_bytes(b'video'); return Path(dest)
            with (patch.object(ltx, 'upload_file', side_effect=['image.remote', 'audio.remote']) as upload,
                  patch.object(ltx, 'create_ltx_task', return_value='task') as create,
                  patch.object(ltx, 'query_talk_task', return_value={
                      'status':'success','video_url':'https://example.test/video.mp4','fail_reason':''}),
                  patch.object(ltx, 'download_file', side_effect=download)):
                result = ltx.generate_ltx_video(api_key='key', image_path=image, audio_path=audio,
                    dest=output, audio_duration=3, video_res='720p', low_cost=True, poll_interval=0)
            self.assertEqual((result['max_res'], result['instance_type']), (1280, 'default'))
            self.assertEqual(upload.call_args_list, [call(api_key='key', file_path=image),
                                                     call(api_key='key', file_path=audio)])
            self.assertEqual(create.call_args.kwargs['retain_seconds'], 20)
            with patch.object(ltx, 'upload_file') as upload:
                with self.assertRaisesRegex(InterruptedError, '已取消'):
                    ltx.generate_ltx_video(api_key='key', image_path=image, audio_path=audio,
                                           dest=output, cancel_check=lambda: True)
                upload.assert_not_called()

    def test_cancel_during_completed_download_removes_late_output(self):
        with tempfile.TemporaryDirectory() as directory:
            image, audio, output = (Path(directory) / name for name in ('image.png', 'audio.wav', 'video.mp4'))
            image.write_bytes(b'image'); audio.write_bytes(b'audio')
            cancelled = [False]

            def download(_url, dest):
                Path(dest).write_bytes(b'late-video')
                cancelled[0] = True
                return Path(dest)

            with (patch.object(ltx, 'upload_file', side_effect=['image.remote', 'audio.remote']),
                  patch.object(ltx, 'create_ltx_task', return_value='task'),
                  patch.object(ltx, 'query_talk_task', return_value={
                      'status':'success','video_url':'https://example.test/video.mp4','fail_reason':''}),
                  patch.object(ltx, 'download_file', side_effect=download)):
                with self.assertRaisesRegex(InterruptedError, '已取消'):
                    ltx.generate_ltx_video(api_key='key', image_path=image, audio_path=audio,
                        dest=output, audio_duration=3, poll_interval=0,
                        cancel_check=lambda: cancelled[0])
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
