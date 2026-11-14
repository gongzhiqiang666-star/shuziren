import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from scripts.avatar_tasks import AvatarTasks
from scripts.avatar_store import AvatarError
from scripts.avatar_prepare_worker import validate_face_coverage


class AvatarTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.runtime=self.root/'runtime'
        python=self.runtime/'_internal/env/python.exe';python.parent.mkdir(parents=True);python.touch()
        self.source=self.root/'input.mp4';self.source.write_bytes(b'media request fixture, not real video')

    def test_restart_marks_interrupted_without_using_persisted_pid(self):
        data=self.root/'data';data.mkdir()
        (data/'avatar-task.json').write_text(json.dumps({'id':str(uuid.uuid4()),'status':'running','pid':123}),encoding='utf-8')
        with patch('scripts.avatar_tasks.subprocess.Popen') as spawn, patch.object(AvatarTasks,'_terminate') as kill:
            tasks=AvatarTasks(self.runtime,data)
            self.assertEqual(tasks.state()['status'],'interrupted')
            tasks.close();spawn.assert_not_called();kill.assert_not_called()

    def test_bad_inputs_and_closed_manager_never_launch(self):
        tasks=AvatarTasks(self.runtime,self.root/'data')
        with patch('scripts.avatar_tasks.subprocess.Popen') as spawn:
            for kwargs in ({'source':'relative.mp4','name':'名称'},
                           {'source':str(self.source),'name':''},
                           {'source':str(self.source),'name':'名称','resolution':{}},
                           {'source':str(self.source),'name':'名称','resolution':'invalid'}):
                with self.assertRaises(AvatarError):tasks.start(**kwargs)
            tasks.close()
            with self.assertRaises(AvatarError):tasks.start(str(self.source),'名称')
            spawn.assert_not_called()

    def test_state_write_failure_prevents_process_launch(self):
        tasks=AvatarTasks(self.runtime,self.root/'data')
        with patch.object(tasks,'_save',side_effect=OSError('disk failure')), \
             patch('scripts.avatar_tasks.subprocess.Popen') as spawn, self.assertLogs(level='ERROR'):
            with self.assertRaises(OSError):tasks.start(str(self.source),'名称')
            spawn.assert_not_called()
        self.assertIsNone(tasks.process)
        self.assertEqual(tasks.state()['status'],'failed')

    def test_face_coverage_rejects_ambiguous_and_occluded_video(self):
        validate_face_coverage({'total_frames':100,'face_frames':90,
                                'no_face_frames':list(range(0,10)),'multi_face_frames':0})
        for info, message in ((
            {'total_frames':100,'face_frames':99,'no_face_frames':[0],'multi_face_frames':1},'多张人脸'),(
            {'total_frames':100,'face_frames':79,'no_face_frames':list(range(21,42)),'multi_face_frames':0},'不足80%'),(
            {'total_frames':100,'face_frames':87,'no_face_frames':list(range(13)),'multi_face_frames':0},'0.48秒'),(
            {'total_frames':100,'face_frames':90,'no_face_frames':[0],'multi_face_frames':0},'不完整')):
            with self.assertRaisesRegex(AvatarError,message):validate_face_coverage(info)


if __name__=='__main__':
    unittest.main()
