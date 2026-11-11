import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.tts_worker import TTSProvider


RUNTIME=os.environ.get('SHUZIREN_TEST_RUNTIME_ROOT','')


class TTSDeliveryTests(unittest.TestCase):
    def test_conversion_failure_removes_scratch_without_publishing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = Path(directory)
            scratch = outputs / 'cache' / 'generated.wav'
            scratch.parent.mkdir()
            scratch.write_bytes(b'bad audio')
            provider = TTSProvider.__new__(TTSProvider)
            provider.outputs = outputs
            provider.cache = Mock(root=outputs / 'content-cache')
            provider.voices = Mock()
            provider.voices.get.return_value = dict(id='voice', audio_sha256='a', text_sha256='b')
            provider.synth = Mock()
            provider.synth.synthesize.return_value = str(scratch)
            provider.identity = ('voice', 'a', 'b')
            provider.inference_calls = 0
            provider._engine_stamp = lambda: 'test-engine'

            with patch('scripts.tts_worker.normalize_task_wav', side_effect=OSError('conversion failed')):
                with self.assertRaisesRegex(OSError, 'conversion failed'):
                    provider.synthesize(dict(voice_id='voice', text='test', speed=1,
                                             language='en', use_cache=False))

            self.assertFalse(scratch.exists())
            self.assertEqual(list(outputs.glob('*.wav')), [])
            provider.cache.put.assert_not_called()


@unittest.skipUnless(RUNTIME and (Path(RUNTIME)/'_internal/env/python.exe').is_file(),'Explicit runtime required')
class TTSWorkerProtocolTests(unittest.TestCase):
    def test_alternate_engine_ready_and_close(self):
        for engine, provider in (('zipvoice', 'recovered-zipvoice'),
                                 ('omnivoice', 'recovered-omnivoice')):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [sys.executable, '-X', 'utf8', '-m', 'scripts.tts_worker',
                     '--runtime-root', RUNTIME, '--data-directory', directory,
                     '--engine', engine],
                    input='{"action":"close"}\n', capture_output=True,
                    text=True, encoding='utf-8', timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 {'event': 'ready', 'provider': provider})

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
