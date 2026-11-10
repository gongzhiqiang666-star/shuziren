"""Provider configuration fixtures, not actual GPU throughput evidence."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.v122_acceleration import accelerated_unet


class ControlTests(unittest.TestCase):
    def modules(self,version='1.15.1',fallback=False):
        class Session:
            def __init__(self,model,*args,**kwargs):
                self.requested=kwargs['providers'];self.options={}
                for provider in self.requested:
                    if isinstance(provider,tuple):self.options[provider[0]]=dict(provider[1])
                if fallback:self.options['CUDAExecutionProvider']['gpu_mem_limit']=str(2**64-1)
            def get_providers(self):return [value[0] if isinstance(value,tuple) else value for value in self.requested]
            def get_provider_options(self):return self.options
            def disable_fallback(self):self.fallback_disabled=True
        ort=SimpleNamespace(__version__=version,InferenceSession=Session)
        torch=SimpleNamespace(set_num_threads=lambda value:None,backends=SimpleNamespace(
            cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=True)),cudnn=SimpleNamespace(allow_tf32=True)))
        cv2=SimpleNamespace(setNumThreads=lambda value:None)
        return {'onnxruntime':ort,'torch':torch,'cv2':cv2}

    def test_legacy_ort_uses_process_override_without_unknown_option(self):
        modules=self.modules()
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,modules),patch.dict(os.environ,{'NVIDIA_TF32_OVERRIDE':'0'}):
            with accelerated_unet(directory,backend='cuda',strict_fp32=True) as sessions:
                instance=modules['onnxruntime'].InferenceSession(str(Path(directory)/'unet_v2.onnx'))
                self.assertNotIn('use_tf32',instance.options['CUDAExecutionProvider'])
                self.assertTrue(instance.fallback_disabled);self.assertEqual(len(sessions),1)
                self.assertFalse(modules['torch'].backends.cuda.matmul.allow_tf32)

    def test_supported_ort_sets_tf32_option_and_missing_override_rejected(self):
        modules=self.modules('1.18.0')
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,modules),patch.dict(os.environ,{'NVIDIA_TF32_OVERRIDE':'0'}):
            with accelerated_unet(directory,backend='cuda',strict_fp32=True):
                instance=modules['onnxruntime'].InferenceSession('unet_v2.onnx')
                self.assertEqual(instance.options['CUDAExecutionProvider']['use_tf32'],'0')
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'NVIDIA_TF32_OVERRIDE':'1'}):
            with self.assertRaises(RuntimeError):
                with accelerated_unet(directory,strict_fp32=True):pass

    def test_silent_fallback_losing_memory_limit_rejected(self):
        modules=self.modules(fallback=True)
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,modules):
            with accelerated_unet(directory,backend='cuda'):
                with self.assertRaisesRegex(RuntimeError,'gpu_mem_limit'):
                    modules['onnxruntime'].InferenceSession('unet_v2.onnx')


if __name__=='__main__':unittest.main()
