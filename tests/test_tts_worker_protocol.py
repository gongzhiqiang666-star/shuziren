import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RUNTIME=os.environ.get('SHUZIREN_TEST_RUNTIME_ROOT','')


@unittest.skipUnless(RUNTIME and (Path(RUNTIME)/'_internal/env/python.exe').is_file(),'Explicit runtime required')
class TTSWorkerProtocolTests(unittest.TestCase):
    def test_invalid_requests_report_failure_and_worker_closes_without_model(self):
        with tempfile.TemporaryDirectory() as directory:
            requests=[{}, {'voice_id':'missing','text':'测试','speed':True,'language':'zh-CN','use_cache':False},
                      {'voice_id':'missing','text':'','speed':1.0,'language':'zh-CN','use_cache':False},
                      {'action':'close'}]
            result=subprocess.run([sys.executable,'-X','utf8','-m','scripts.tts_worker','--runtime-root',RUNTIME,
                '--data-directory',directory],input='\n'.join(json.dumps(r) for r in requests)+'\n',
                capture_output=True,text=True,encoding='utf-8',timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            events=[json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(events[0]['event'],'ready')
            self.assertEqual([e['ok'] for e in events[1:]],[False,False,False])
            self.assertEqual(list((Path(directory)/'tts').glob('*.wav')),[])


if __name__=='__main__': unittest.main()
