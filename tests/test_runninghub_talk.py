import tempfile
import unittest
import wave
import threading
import time
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from recovered import runninghub_talk
from recovered.main import Api


class DownloadResponse:
    def __init__(self, chunks, declared=0):
        self.chunks = chunks
        self.headers = {"Content-Length": str(declared)} if declared else {}

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def raise_for_status(self): return None
    def iter_content(self, _size): return iter(self.chunks)


class RunningHubTalkTests(unittest.TestCase):
    def test_cloud_project_restart_marks_running_task_interrupted_and_keeps_assets(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api.__new__(Api); api.runtime_dir = Path(root); api.config = {}
            project = api.create_cloud_dh_project('restart recovery')['project']
            outputs = api._get_cloud_dh_output_paths(project['id'])
            for kind, content in (('avatar', b'avatar'), ('audio', b'audio'), ('video', b'video')):
                Path(outputs[kind]).write_bytes(content)
            info = api._load_cloud_dh_project(project['id'])
            info['generation_task'] = {'status':'running', 'operation':'generate_video',
                                       'started_at':'2026-11-14T10:00:00', 'ended_at':None, 'error':''}
            api._save_cloud_dh_project(project['id'], info)
            directory = Path(api._get_cloud_dh_project_dir(project['id']))
            (directory/'.数字人口播.pending.mp4').write_bytes(b'partial')
            (directory/'.口播音频.wav.importing').write_bytes(b'partial')

            restarted = Api.__new__(Api); restarted.runtime_dir = Path(root); restarted.config = {}
            recovered = restarted.get_cloud_dh_project(project['id'])['project']
            self.assertEqual(recovered['generation_task']['status'], 'interrupted')
            self.assertIn('进程退出', recovered['generation_task']['error'])
            self.assertEqual({kind:Path(path).read_bytes() for kind, path in outputs.items()},
                             {'avatar':b'avatar', 'audio':b'audio', 'video':b'video'})
            self.assertFalse((directory/'.数字人口播.pending.mp4').exists())
            self.assertFalse((directory/'.口播音频.wav.importing').exists())
            summary = restarted.get_all_cloud_dh_projects()['projects'][0]
            self.assertEqual((summary['generation_status'], summary['generation_operation']),
                             ('interrupted', 'generate_video'))

    def test_talk_cancel_before_upload_has_no_remote_side_effect(self):
        with patch.object(runninghub_talk, 'upload_file') as upload:
            with self.assertRaises(InterruptedError):
                runninghub_talk._generate_talk_video_cancellable(
                    api_key='key', image_path='image', audio_path='audio', dest='video',
                    cancel_check=lambda: True)
        upload.assert_not_called()

    def test_cloud_video_can_be_cancelled_without_replacing_previous_result(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api.__new__(Api); api.runtime_dir = Path(root); api.config = {'runninghub_api_key':'key'}
            project = api.create_cloud_dh_project('cancel video')['project']
            outputs = api._get_cloud_dh_output_paths(project['id'])
            Image.new('RGB', (96, 160), 'blue').save(outputs['avatar'], 'PNG')
            Path(outputs['audio']).write_bytes(b'audio')
            Path(outputs['video']).write_bytes(b'old-video')
            replacement = Path(root)/'replacement.png'
            Image.new('RGB', (96, 160), 'green').save(replacement, 'PNG')
            entered = threading.Event(); result = []
            def provider(**kwargs):
                entered.set()
                while not kwargs['cancel_check'](): time.sleep(.01)
                raise InterruptedError('云数字人生成已取消')
            with patch.object(runninghub_talk, '_generate_talk_video_cancellable', side_effect=provider):
                worker = threading.Thread(target=lambda: result.append(
                    api.generate_cloud_dh_video({'project_id':project['id']})))
                worker.start(); self.assertTrue(entered.wait(2))
                duplicate = api.generate_cloud_dh_video({'project_id':project['id']})
                self.assertIn('正在生成', duplicate['message'])
                with self.assertRaisesRegex(RuntimeError, '正在生成或更新素材'):
                    api._import_cloud_dh_file(project['id'], 'avatar', replacement)
                avatar = api.generate_cloud_dh_avatar({'project_id':project['id']})
                self.assertEqual(avatar['status'], 'error')
                self.assertIn('正在生成或更新素材', avatar['message'])
                self.assertEqual(api.cancel_cloud_dh_generation(project['id'])['status'], 'cancel_requested')
                worker.join(2); self.assertFalse(worker.is_alive())
            self.assertEqual(result[0]['status'], 'cancelled')
            self.assertEqual(Path(outputs['video']).read_bytes(), b'old-video')
            self.assertFalse(list(Path(outputs['video']).parent.glob('*.pending.mp4')))
            self.assertEqual(api.cancel_cloud_dh_generation(project['id'])['status'], 'idle')
            task = api.get_cloud_dh_project(project['id'])['project']['generation_task']
            self.assertEqual((task['status'], task['operation']), ('cancelled', 'generate_video'))

    def test_cloud_media_import_validates_then_versions_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api.__new__(Api); api.runtime_dir = Path(root); api.config = {}
            project = api.create_cloud_dh_project('media import')['project']
            outputs = api._get_cloud_dh_output_paths(project['id'])
            Image.new('RGB', (80, 120), 'red').save(outputs['avatar'], 'PNG')
            Path(outputs['video']).write_bytes(b'old-video')
            invalid = Path(root)/'invalid.png'; invalid.write_bytes(b'not-an-image')
            with self.assertRaises(Exception): api._import_cloud_dh_file(project['id'], 'avatar', invalid)
            self.assertTrue(Path(outputs['video']).is_file())
            valid = Path(root)/'valid.png'; Image.new('RGB', (96, 160), 'blue').save(valid, 'PNG')
            imported = api._import_cloud_dh_file(project['id'], 'avatar', valid)
            self.assertEqual(imported['status'], 'success')
            self.assertFalse(Path(outputs['video']).exists())

            Path(outputs['video']).write_bytes(b'avatar-video')
            invalid_audio = Path(root)/'invalid.wav'; invalid_audio.write_bytes(b'not-audio')
            with self.assertRaises(Exception): api._import_cloud_dh_file(project['id'], 'audio', invalid_audio)
            self.assertTrue(Path(outputs['video']).is_file())
            audio = Path(root)/'valid.wav'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\x00\x00' * 24000)
            imported = api._import_cloud_dh_file(project['id'], 'audio', audio)
            self.assertEqual(imported['status'], 'success')
            self.assertFalse(Path(outputs['video']).exists())
            self.assertGreater(Path(outputs['audio']).stat().st_size, 44)
            history = Path(api._get_cloud_dh_history_dir(project['id']))
            self.assertGreaterEqual(len(list(history.rglob('数字人口播.mp4'))), 2)
            task = api.get_cloud_dh_project(project['id'])['project']['generation_task']
            self.assertEqual((task['status'], task['operation']), ('succeeded', 'import_audio'))

    def test_cloud_avatar_is_validated_before_replacing_versioned_project(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api.__new__(Api); api.runtime_dir = Path(root); api.config = {"runninghub_api_key": "key"}
            project = api.create_cloud_dh_project("avatar transaction")["project"]
            outputs = api._get_cloud_dh_output_paths(project["id"])
            Image.new('RGB', (80, 120), 'red').save(outputs['avatar'], 'PNG')
            Path(outputs['audio']).write_bytes(b'old-audio')
            Path(outputs['video']).write_bytes(b'old-video')
            old_avatar = Path(outputs['avatar']).read_bytes()

            def invalid(**kwargs): Path(kwargs['dest']).write_bytes(b'broken-image')
            with patch('recovered.runninghub_image._generate_and_download_cancellable', side_effect=invalid):
                failed = api.generate_cloud_dh_avatar({'project_id': project['id']})
            self.assertEqual(failed['status'], 'error')
            self.assertEqual(Path(outputs['avatar']).read_bytes(), old_avatar)
            self.assertEqual(Path(outputs['video']).read_bytes(), b'old-video')
            self.assertFalse(list(Path(outputs['avatar']).parent.glob('*.pending.png')))

            def valid(**kwargs): Image.new('RGB', (96, 160), 'blue').save(kwargs['dest'], 'PNG')
            with patch('recovered.runninghub_image._generate_and_download_cancellable', side_effect=valid):
                completed = api.generate_cloud_dh_avatar({'project_id': project['id']})
            self.assertEqual(completed['status'], 'success')
            self.assertFalse(Path(outputs['video']).exists())
            with Image.open(outputs['avatar']) as image: self.assertEqual(image.size, (96, 160))
            history = Path(api._get_cloud_dh_history_dir(project['id']))
            self.assertEqual(next(history.rglob('数字人形象.png')).read_bytes(), old_avatar)
            self.assertEqual(next(history.rglob('数字人口播.mp4')).read_bytes(), b'old-video')
            blue_avatar = Path(outputs['avatar']).read_bytes()
            Path(outputs['video']).write_bytes(b'newer-video')
            def second(**kwargs): Image.new('RGB', (96, 160), 'green').save(kwargs['dest'], 'PNG')
            with patch('recovered.runninghub_image._generate_and_download_cancellable', side_effect=second):
                self.assertEqual(api.generate_cloud_dh_avatar({'project_id': project['id']})['status'], 'success')
            archived_avatars = list(history.rglob('数字人形象.png'))
            self.assertEqual(len(archived_avatars), 2)
            self.assertEqual({item.read_bytes() for item in archived_avatars}, {old_avatar, blue_avatar})
            task = api.get_cloud_dh_project(project['id'])['project']['generation_task']
            self.assertEqual((task['status'], task['operation']), ('succeeded', 'generate_avatar'))

    def test_completed_without_url_is_not_success(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "data": {"status": "COMPLETED", "outputs": []}}
        with patch.object(runninghub_talk.requests, "post", return_value=response):
            self.assertEqual(runninghub_talk.query_talk_task(api_key="key", task_id="task")["status"], "queued")

    def test_download_is_https_bounded_validated_and_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "video.mp4"
            target.write_bytes(b"old")
            with self.assertRaises(ValueError):
                runninghub_talk.download_file("http://example.test/video.mp4", target)
            invalid = DownloadResponse([b"not a movie payload"])
            with patch.object(runninghub_talk.requests, "get", return_value=invalid):
                with self.assertRaises(RuntimeError):
                    runninghub_talk.download_file("https://example.test/video.mp4", target)
            self.assertEqual(target.read_bytes(), b"old")
            oversized = DownloadResponse([b"\0\0\0\x18ftypmp42"], declared=100)
            with patch.object(runninghub_talk.requests, "get", return_value=oversized), \
                    patch.object(runninghub_talk, "MAX_DOWNLOAD_BYTES", 20):
                with self.assertRaises(RuntimeError):
                    runninghub_talk.download_file("https://example.test/video.mp4", target)
            valid = DownloadResponse([b"\0\0\0\x18ftypmp42" + b"x" * 32])
            with patch.object(runninghub_talk.requests, "get", return_value=valid):
                runninghub_talk.download_file("https://example.test/video.mp4", target)
            self.assertIn(b"ftyp", target.read_bytes()[:32])
            self.assertFalse(list(Path(root).glob("*.partial")))

    def test_poll_bounds_are_rejected_before_upload(self):
        with patch.object(runninghub_talk, "upload_file") as upload:
            with self.assertRaises(ValueError):
                runninghub_talk.generate_talk_video(api_key="key", image_path="a", audio_path="b",
                                                    dest="c", poll_interval=-1)
            upload.assert_not_called()

    def test_cloud_project_archives_only_after_new_video_is_ready(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api.__new__(Api); api.runtime_dir = Path(root); api.config = {"runninghub_api_key": "key"}
            project = api.create_cloud_dh_project("test")["project"]
            outputs = api._get_cloud_dh_output_paths(project["id"])
            Path(outputs["avatar"]).write_bytes(b"png")
            Path(outputs["audio"]).write_bytes(b"wav")
            Path(outputs["video"]).write_bytes(b"old-video")

            def fail(**_kwargs):
                raise RuntimeError("network failed")
            with patch.object(runninghub_talk, "_generate_talk_video_cancellable", side_effect=fail):
                result = api.generate_cloud_dh_video({"project_id": project["id"]})
            self.assertEqual(result["status"], "error")
            self.assertEqual(Path(outputs["video"]).read_bytes(), b"old-video")
            self.assertFalse(list(Path(outputs["video"]).parent.glob("*.pending.mp4")))
            self.assertFalse(Path(api._get_cloud_dh_history_dir(project["id"])).exists())

            def succeed(**kwargs):
                Path(kwargs["dest"]).write_bytes(b"\0\0\0\x18ftypmp42-new")
                return {"task_id": "task-1", "status": "success", "video_path": str(kwargs["dest"])}
            with patch.object(runninghub_talk, "_generate_talk_video_cancellable", side_effect=succeed):
                result = api.generate_cloud_dh_video({"project_id": project["id"]})
            self.assertEqual(result["status"], "success")
            self.assertIn(b"ftyp", Path(outputs["video"]).read_bytes())
            archived = list(Path(api._get_cloud_dh_history_dir(project["id"])).glob("*/数字人口播.mp4"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_bytes(), b"old-video")


if __name__ == "__main__":
    unittest.main()
