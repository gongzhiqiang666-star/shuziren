import unittest
from unittest.mock import patch

import numpy as np

from recovered.wenet_features import compute_bnf


class FakeTensor:
    def __init__(self, value): self.value = np.asarray(value)
    def float(self): return self
    def to(self, device): self.device = str(device); return self
    def unsqueeze(self, _): return self
    def squeeze(self, axis): self.value = np.squeeze(self.value, axis=axis); return self
    def cpu(self): return self
    def numpy(self): return self.value


class FakeTorch:
    long = 'long'
    class no_grad:
        def __enter__(self): return self
        def __exit__(self, *_): pass
    @staticmethod
    def from_numpy(value): return FakeTensor(value)
    @staticmethod
    def tensor(value, **options):
        result = FakeTensor(value)
        result.device = str(options.get('device'))
        return result


class WenetFeatureTests(unittest.TestCase):
    def test_inputs_follow_model_device_and_short_tail_is_trimmed(self):
        class Parameter: device = 'cpu'
        class Model:
            def parameters(self): return iter([Parameter()])
            def __call__(self, inputs, lengths):
                self.devices = (inputs.device, lengths.device)
                return FakeTensor(np.ones((1, 30, 256), dtype=np.float32))
        class Provider:
            hparams1 = {'sample_rate': 16000, 'n_mfcc': 80, 'n_fft': 400,
                        'hop_length': 160, 'win_length': 400, 'window': 'hann',
                        'num_mels': 80, 'center': True}
            @staticmethod
            def load_wav(*_, **__): return np.ones(1000)
            @staticmethod
            def wav2mfcc_v2(*_, **__): return np.ones((10, 80)), None
        model = Model()
        with patch.dict('sys.modules', {'torch': FakeTorch}):
            result = compute_bnf(Provider, 'fixture.wav', model)
        self.assertEqual(model.devices, ('cpu', 'cpu'))
        self.assertEqual(result.shape, (5, 256))

    def test_exact_section_multiple_preserves_provider_tail_block(self):
        class Parameter: device = 'cpu'
        class Model:
            def parameters(self): return iter([Parameter()])
            def __call__(self, inputs, lengths):
                return FakeTensor(np.ones((1, 30, 256), dtype=np.float32))
        class Provider:
            hparams1 = {'sample_rate': 100, 'n_mfcc': 80, 'n_fft': 40,
                        'hop_length': 16, 'win_length': 40, 'window': 'hann',
                        'num_mels': 80, 'center': True}
            @staticmethod
            def load_wav(*_, **__): return np.ones(200)
            @staticmethod
            def wav2mfcc_v2(*_, **__): return np.ones((10, 80)), None
        # Added provider silence is 12,800 samples, making 13 exact 1,000-sample
        # blocks. Historical behavior processes a fourteenth padded tail block.
        with patch.dict('sys.modules', {'torch': FakeTorch}):
            result = compute_bnf(Provider, 'fixture.wav', Model(), section=1000)
        self.assertEqual(result.shape, (13 * 30 + 5, 256))


if __name__ == '__main__': unittest.main()
