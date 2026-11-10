"""Real subprocess protocol fixtures; these do not load a GPU model."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from scripts.live_avatar_client import LiveAvatarClient


FIXTURE='''import json,os,sys,time
for line in sys.stdin:
 request=json.loads(line)
 if request['operation']=='timeout':time.sleep(30)
 if request['operation']=='big':print('x'*1048580,flush=True);time.sleep(30)
 print(json.dumps({'event':'first_frame_written'}),flush=True)
 if request['operation']=='cancel':time.sleep(30)
 print(json.dumps({'ok':True,'result':{'pid':os.getpid()}}),flush=True)
'''


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.client=self.make_client()

    def make_client(self,log=None):
        client=object.__new__(LiveAvatarClient)
        client.closed=False;client.busy=False;client.reader=None;client.calls=threading.Lock();client.guard=threading.RLock()
        # Force-killed processes can briefly retain Windows file-system locks.
        # OS-managed temporary logs avoid racing recursive directory deletion;
        # regular persistent-log deletion is checked separately below.
        client.log=log if log is not None else tempfile.TemporaryFile()
        client.process=subprocess.Popen([sys.executable,'-u','-c',FIXTURE],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=client.log,text=True,encoding='utf-8',bufsize=1)
        self.addCleanup(client.close)
        return client

    def test_resident_protocol_and_clean_eof(self):
        events=[];first=self.client.request('echo',progress=events.append);second=self.client.request('echo')
        self.assertEqual(first['pid'],second['pid']);self.assertEqual(len(events),1)
        self.client.close();self.assertEqual(self.client.process.poll(),0)

    def test_timeout_reaps_owned_worker(self):
        started=time.monotonic()
        with self.assertRaises(TimeoutError):self.client.request('timeout',timeout=.3)
        self.assertIsNotNone(self.client.process.poll());self.assertLess(time.monotonic()-started,5)

    def test_cancel_wakes_waiter_and_rejects_late_result(self):
        ready=threading.Event();errors=[]
        def request():
            try:self.client.request('cancel',progress=lambda _:ready.set())
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=request);worker.start();self.assertTrue(ready.wait(2))
        self.client.close();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertIsNotNone(self.client.process.poll())
        with self.assertRaises(RuntimeError):self.client.request('echo')

    def test_oversized_control_response_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Oversized'):self.client.request('big')
        self.assertIsNotNone(self.client.process.poll())

    def test_response_for_wrong_render_binding_is_rejected(self):
        self.client.close()
        self.client=self.make_client((Path(self.temp.name)/'fixture.log').open('ab'))
        with self.assertRaisesRegex(ValueError,'binding mismatch'):
            self.client.request('render',session_id='one',task_id='two',pcm_sha256='expected',audio='unused.wav',output='unused.mp4')
        self.assertIsNotNone(self.client.process.poll())
        self.assertTrue(self.client.log.closed)
        self.assertEqual(self.client.process.poll(),0)
        Path(self.client.log.name).unlink()

    def test_broken_pipe_during_cancel_still_closes_log(self):
        stream=self.client.process.stdin
        class BrokenClose:
            @property
            def closed(self):return stream.closed
            def close(self):
                try:stream.close()
                finally:raise BrokenPipeError('flush failed after handle close')
        self.client.process.stdin=BrokenClose();self.client.busy=True
        self.client.close()
        self.assertTrue(self.client.log.closed);self.assertIsNotNone(self.client.process.poll())
