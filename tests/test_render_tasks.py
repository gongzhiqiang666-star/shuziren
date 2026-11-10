"""Task/protocol fixtures only. Actual inference lives in validate_render_tasks."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import cv2
import numpy as np

from scripts.avatar_store import AvatarStore,digest
from scripts.product_store import ProductStore,Conflict,ProductError
from scripts.render_tasks import RenderTasks


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        source=self.root/'source';(source/'frames').mkdir(parents=True);(source/'positions').mkdir()
        cv2.imwrite(str(source/'frames/000000.jpg'),np.full((32,24,3),100,np.uint8))
        (source/'positions/000000.txt').write_text('fps: 25\nwidth: 24\nheight: 32\nis_no_face: False\nbounding_box: [2, 20, 3, 22]\n')
        avatars=AvatarStore(self.root);self.avatar=avatars.import_prepared(source,'一');self.second=avatars.import_prepared(source,'二')
        avatars.select(self.avatar['id']);products=ProductStore(self.root)
        self.product=products.save(title='绑定夹具',content='状态测试',product_index=1);products.select(self.product['id'])
        class AudioFixture:
            def state(inner):return copy.deepcopy(inner.value)
            def audio(inner,task_id):
                if task_id!=inner.value['id']:raise Conflict('错任务')
                return b'audio transport fixture'
        self.audio=AudioFixture();self.audio.products=products
        self.audio.value={'id':str(uuid.uuid4()),'status':'succeeded','product_id':self.product['id'],
                          'product_version':1,'script_id':str(uuid.uuid4()),'voice_id':str(uuid.uuid4()),
                          'product_title':'绑定夹具','speed':1.0}
        self.tasks=RenderTasks(self.root/'runtime',self.root,self.audio)

    def pending(self):
        binding,_,_,_=self.tasks._inputs(self.audio.value['id'],self.avatar['id'])
        task={'id':str(uuid.uuid4()),'status':'running',**binding};self.tasks.task=task
        work=self.tasks.jobs/task['id'];work.mkdir();(work/'audio.wav').write_bytes(b'input fixture')
        path=work/'output.mp4';path.write_bytes(b'video transport fixture')
        result={'output':str(path),'output_sha256':digest(path),'audio_sha256':binding['audio_sha256'],
                'full_decode_passed':True,'audio_complete':True}
        return task,work,result

    def finish(self,task,work,result):
        class ProcessFixture:
            returncode=0
            stdout=io.BytesIO()
            def poll(self):return 0
            def communicate(self,timeout):return json.dumps({'ok':True,'result':result}).encode(),None
        self.tasks._finish(ProcessFixture(),task['id'],work,io.BytesIO())

    def test_valid_completion_and_changed_file_rejected(self):
        task,work,result=self.pending();self.finish(task,work,result)
        self.assertEqual(self.tasks.state()['status'],'succeeded')
        path=self.tasks.video_path(task['id']);path.write_bytes(b'tampered')
        with self.assertRaises(Conflict):self.tasks.video_path(task['id'])
        self.assertEqual(self.tasks.state()['status'],'failed')
        self.assertNotIn('result',self.tasks.state())

    def test_avatar_change_invalidates_completed_result_without_resurrection(self):
        task,work,result=self.pending();self.finish(task,work,result)
        self.tasks.avatars.select(self.second['id'])
        self.assertEqual(self.tasks.state()['status'],'failed')
        self.tasks.avatars.select(self.avatar['id'])
        with self.assertRaises(Conflict):self.tasks.video_path(task['id'])

    def test_cancelled_late_result_is_not_accepted(self):
        task,work,result=self.pending();self.tasks.cancel(task['id']);self.finish(task,work,result)
        self.assertEqual(self.tasks.state()['status'],'cancelled')
        self.assertFalse((work/'output.mp4').exists());self.assertFalse((work/'audio.wav').exists())

    def test_new_audio_or_selected_product_rejects_late_result(self):
        task,work,result=self.pending();self.audio.value['id']=str(uuid.uuid4())
        self.finish(task,work,result);self.assertEqual(self.tasks.state()['status'],'failed')
        self.assertFalse((work/'output.mp4').exists())
        task,work,result=self.pending()
        other=self.audio.products.save(title='另一个商品',content='另一个',product_index=2)
        self.audio.products.select(other['id']);self.finish(task,work,result)
        self.assertEqual(self.tasks.state()['status'],'failed')

    def test_foreign_output_is_rejected_without_deleting_foreign_file(self):
        task,work,result=self.pending();foreign=self.root/'external.mp4';foreign.write_bytes(b'keep')
        result.update(output=str(foreign),output_sha256=digest(foreign))
        self.finish(task,work,result)
        self.assertEqual(self.tasks.state()['status'],'failed');self.assertEqual(foreign.read_bytes(),b'keep')

    def test_restart_running_record_is_interrupted(self):
        task,work,result=self.pending();self.tasks._save()
        reopened=RenderTasks(self.root/'runtime',self.root,self.audio)
        self.assertEqual(reopened.state()['status'],'interrupted')
        with self.assertRaises(Conflict):reopened.video_path(task['id'])

    def test_legacy_unverified_tail_result_invalidated_and_record_preserved(self):
        task,work,result=self.pending();self.finish(task,work,result)
        self.tasks.task['result'].pop('audio_complete')
        state=self.tasks.state()
        self.assertEqual(state['status'],'failed');self.assertIn('previous_result',state)
        self.assertTrue((work/'output.mp4').exists())
        saved=json.loads((work/'task.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['id'],task['id']);self.assertEqual(saved['status'],'failed')

    def test_explicit_profile_rejects_fallback_and_accepts_matching_result(self):
        task,work,result=self.pending();task['render_profile']='trt-nvenc'
        result.update(render_profile='standard',backend='cuda',video_encoder='legacy')
        self.finish(task,work,result)
        self.assertEqual(self.tasks.state()['status'],'failed');self.assertFalse((work/'output.mp4').exists())
        task,work,result=self.pending();task['render_profile']='trt-nvenc'
        result.update(render_profile='trt-nvenc',backend='tensorrt',video_encoder='h264_nvenc')
        self.finish(task,work,result);self.assertEqual(self.tasks.state()['status'],'succeeded')
        self.tasks.task['result']['video_encoder']='libx264'
        self.assertEqual(self.tasks.state()['status'],'failed')

    def test_unknown_profile_rejected_before_any_job(self):
        for profile in ['unknown',{},None]:
            with self.assertRaises(ProductError):self.tasks.start(self.audio.value['id'],self.avatar['id'],profile)
        self.assertEqual(list(self.tasks.jobs.iterdir()),[])

    def test_new_standard_job_requires_profile_evidence(self):
        task,work,result=self.pending();task['render_profile']='standard'
        self.finish(task,work,result)
        self.assertEqual(self.tasks.state()['status'],'failed')
        self.assertFalse((work/'output.mp4').exists())


if __name__=='__main__':unittest.main()
