"""HuBERT feature extractor used by the offline lip-sync preprocessing path.

Recovered from ``hubert_extractor.cp310-win_amd64.pyd``.  Keep the small API
surface and tensor pipeline aligned with the compiled Cython module.
"""

from __future__ import annotations

class HubertExtractor:
    def __init__(self, hubert_path, device="cuda:0"):
        try:
            from transformers import HubertModel, Wav2Vec2Processor
        except ImportError as error:
            raise RuntimeError("HuBERT 提取需要 transformers") from error

        self.device = device
        self.processor = Wav2Vec2Processor.from_pretrained(
            hubert_path, local_files_only=True
        )
        self.model = HubertModel.from_pretrained(
            hubert_path, local_files_only=True
        ).to(device)

    def extract(self, speech):
        input_values = self.processor(
            speech, sampling_rate=16000, return_tensors="pt"
        ).input_values.to(self.device)
        features = self.model(input_values).last_hidden_state[0]
        if features.shape[0] % 2 == 1:
            features = features[:-1]
        return features.detach().cpu().numpy()
