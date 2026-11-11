"""ONNX mouth/face frame synthesizer used by v2 and origin-frame modes."""

from __future__ import annotations

import time
from pathlib import Path
import cv2
import numpy as np

from .frame_synthesizer import resize_face_crop, get_batch_audio_features, paste_synthesis_interior
from .heygem_face_fuse import (fuse_crop_heygem_lmk, landmarks_to_crop_coords,
                               paste_fused_crop_rectangle)
from .occluder_mask import paste_occluder_mask
from .image_position_compat import resolve_frame_landmarks


class FrameSynthesizer:
    def __init__(self, data_dir, model_path, device="cuda:0", enable_occluder=False):
        self.data_dir = Path(data_dir); configured_path = Path(model_path)
        self.model_dir = configured_path if configured_path.is_dir() else configured_path.parent
        path = self._resolve_model_path(configured_path)
        self.model_path = path; self.device = device; self.enable_occluder = bool(enable_occluder); self.img_size = 256
        self.batch_size = 8
        self.session = None; self.input_names = ["source_img", "ref_img", "audio_feature"]; self.output_names = ["output"]
        self.input_mask = self._load_mask("input_mask.npy"); self.input_mask_re = self._load_mask("input_mask_re.npy")
        self.last_diagnostics = []
        self.perf_stats = self._new_perf_stats()
        if path.is_file(): self._load_session()

    @staticmethod
    def _resolve_model_path(path):
        path = Path(path)
        if not path.is_dir():
            return path
        for name in ("unet_v2.onnx", "unet_v2_fix.onnx"):
            candidate = path / name
            if candidate.is_file():
                return candidate
        return path / "unet_v2.onnx"

    def _load_mask(self, name):
        matches = []
        for root in (self.model_dir, self.data_dir):
            if not root.is_dir():
                continue
            direct = root / name
            if direct.is_file():
                matches.append(direct)
            else:
                matches.extend(root.rglob(name))
            if matches:
                break
        if matches:
            mask = np.asarray(np.load(matches[0]), np.float32).squeeze()
            return cv2.resize(mask, (self.img_size, self.img_size))
        mask = np.ones((self.img_size, self.img_size), np.float32); mask[:self.img_size // 2] = 0
        return cv2.GaussianBlur(mask, (21, 21), 0)

    def _load_session(self):
        try: import onnxruntime
        except ImportError as error: raise RuntimeError("帧合成模型需要 onnxruntime") from error
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if str(self.device).startswith("cuda") else ["CPUExecutionProvider"]
        available = set(onnxruntime.get_available_providers())
        self.session = onnxruntime.InferenceSession(str(self.model_path), providers=[x for x in providers if x in available])
        self.input_names = [x.name for x in self.session.get_inputs()]; self.output_names = [x.name for x in self.session.get_outputs()]

    @staticmethod
    def _new_perf_stats():
        return {"batches": 0, "frames": 0, "inference_ms": [], "prepare_ms": [], "paste_ms": []}

    def tensor_norm_no_training(self, img_tensor, mask=None):
        value = np.asarray(img_tensor, np.float32) / 255.0
        if mask is not None: value = value * np.asarray(mask, np.float32)
        return value

    def _get_batch_audio_features(self, features):
        return get_batch_audio_features([np.asarray(x, np.float32) for x in features])

    @staticmethod
    def _should_synthesize_frame(frame_data):
        return bool(frame_data and not frame_data.get("is_no_face", False) and
                    (frame_data.get("bounding_box") is not None or frame_data.get("bbox") is not None))

    def _prepare_face_crop(self, img, frame_data, index):
        frame_data = dict(frame_data)
        landmarks = resolve_frame_landmarks(frame_data, self.img_size)
        if landmarks is not None:
            frame_data["landmarks"] = landmarks
        top, bottom, left, right = frame_data.get("bounding_box", frame_data.get("bbox"))
        bbox = (left, right, top, bottom)
        crop = resize_face_crop(img, bbox, self.img_size)
        margin = (crop.shape[0] - self.img_size) // 2
        interior = crop[margin:margin + self.img_size, margin:margin + self.img_size]
        rgb = interior[..., ::-1]
        source = self.tensor_norm_no_training(rgb, self.input_mask[..., None]).transpose(2, 0, 1)
        reference = self.tensor_norm_no_training(rgb).transpose(2, 0, 1)
        return {"index": index, "bbox": bbox, "original_crop": interior, "padded_crop": crop, "source": source.astype(np.float32),
                "reference": reference.astype(np.float32), "frame_data": frame_data}

    def _run_model(self, source, reference, audio):
        if self.session is None: raise RuntimeError(f"帧合成 ONNX session 尚未加载: {self.model_path}")
        values = [source, reference, audio]
        inputs = {name: values[index] for index, name in enumerate(self.input_names[:3])}
        return np.asarray(self.session.run(self.output_names, inputs)[0])

    def synthesize_batch(self, batch_audio_features, batch_images, batch_frame_data):
        begin = time.perf_counter(); prepared = []; self.last_diagnostics = []
        for index, (image, data) in enumerate(zip(batch_images, batch_frame_data)):
            if self._should_synthesize_frame(data): prepared.append(self._prepare_face_crop(image, data, index))
        self.perf_stats["prepare_ms"].append((time.perf_counter() - begin) * 1000)
        if not prepared: return list(batch_images)
        sources = np.stack([item["source"] for item in prepared]); references = np.stack([item["reference"] for item in prepared])
        selected_audio = [batch_audio_features[item["index"]] for item in prepared]
        audio = np.stack(self._get_batch_audio_features(selected_audio)).astype(np.float32)
        begin = time.perf_counter(); generated = self._run_model(sources, references, audio)
        self.perf_stats["inference_ms"].append((time.perf_counter() - begin) * 1000)
        if generated.ndim == 4 and generated.shape[1] in (1, 3, 4): generated = generated.transpose(0, 2, 3, 1)
        if generated.min(initial=0) >= 0 and generated.max(initial=0) <= 1.5: generated = generated * 255
        generated = np.clip(generated, 0, 255).astype(np.uint8)[..., ::-1]
        output = [image.copy() for image in batch_images]; begin = time.perf_counter()
        for item, face in zip(prepared, generated):
            data, index, bbox = item["frame_data"], item["index"], item["bbox"]
            cropped_for_pasting = face
            if self.enable_occluder and data.get("full_mask") is not None:
                output[index] = paste_occluder_mask(output[index], face, bbox, data["full_mask"])
            elif getattr(self, "preserve_offline_crop_border", False):
                cropped_for_pasting = paste_synthesis_interior(item["padded_crop"], face, self.img_size)
                output[index] = paste_fused_crop_rectangle(output[index], cropped_for_pasting, bbox)
            elif data.get("landmarks") is not None and len(data["landmarks"]) >= 3:
                fused, _, _ = fuse_crop_heygem_lmk(item["original_crop"], face, data["landmarks"], bbox, self.img_size)
                cropped_for_pasting = fused
                output[index] = paste_fused_crop_rectangle(output[index], fused, bbox)
            else: output[index] = paste_fused_crop_rectangle(output[index], face, bbox)
            local_landmarks = None
            if data.get("landmarks") is not None:
                local_landmarks = landmarks_to_crop_coords(
                    data["landmarks"], bbox, face.shape, self.img_size)
            self.last_diagnostics.append({"index": index, "generated_face": face.copy(),
                                          "cropped_for_pasting": np.asarray(cropped_for_pasting).copy(),
                                          "landmarks": local_landmarks})
        self.perf_stats["paste_ms"].append((time.perf_counter() - begin) * 1000)
        self.perf_stats["batches"] += 1; self.perf_stats["frames"] += len(prepared); return output

    def process_batch(self, batch_images, batch_frame_data, audio_features):
        return self.synthesize_batch(audio_features, batch_images, batch_frame_data)

    def inference(self, audio_info, face_data_dict, this_batch, start_idx):
        images, metadata, features = [], [], []
        for offset in range(this_batch):
            index = start_idx + offset; item = face_data_dict[index] if isinstance(face_data_dict, dict) else face_data_dict[index]
            images.append(item.get("image", item.get("frame"))); metadata.append(item); features.append(audio_info[index])
        return self.process_batch(images, metadata, features)

    def close(self):
        """Release the native ONNX session owned by this synthesizer."""
        session, self.session = self.session, None
        if session is not None:
            close = getattr(session, "close", None)
            if callable(close):
                close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
