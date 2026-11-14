"""Recovered local GroundingDINO + BiRefNet product cutout pipeline."""

from __future__ import annotations

import os
import inspect
from pathlib import Path
from threading import Lock, RLock
from typing import List, Optional, Sequence, Tuple

import numpy as np

_HF_BIREF = "ZhengPeng7/BiRefNet"
_HF_DINO = "IDEA-Research/grounding-dino-tiny"
AUTO_PROMPTS = ("product", "item", "object")
BOX_THRESHOLD = 0.25
TEXT_THRESHOLD = 0.20
PAD_RATIO = 0.04
CANVAS_SIZE = 768
SUBJECT_FILL = 0.82


def _client_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "assets" / "pretrained_models").is_dir():
            return parent
        candidate = parent / "yunchuang_v122" / "_internal"
        if (candidate / "assets" / "pretrained_models").is_dir():
            return candidate
    return here.parent.parent


def resolve_pretrained_root() -> Path:
    return _client_root() / "assets" / "pretrained_models"


def _prompt_text(prompts: Sequence[str]) -> str:
    parts = [str(prompt).strip().lower().rstrip(".") for prompt in prompts if str(prompt).strip()]
    return ". ".join(parts) + ("." if parts else "")


def _ensure_local_model(repo_id: str, local_dir: Path) -> Path:
    local_dir = Path(local_dir)
    if (local_dir / "model.safetensors").is_file():
        return local_dir
    local_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from huggingface_hub import snapshot_download

    print(f"[product.cutout] downloading {repo_id}")
    snapshot_download(repo_id=repo_id, local_dir=str(local_dir))
    if not (local_dir / "model.safetensors").is_file():
        raise FileNotFoundError(f"model.safetensors missing after download: {local_dir}")
    return local_dir


def _largest_components(mask: np.ndarray, max_keep: int = 1) -> np.ndarray:
    import cv2

    mask_u8 = (np.asarray(mask) > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    if count <= 1 or max_keep <= 0:
        return np.zeros_like(mask_u8)
    order = np.argsort(stats[1:, cv2.CC_STAT_AREA])[::-1][:max_keep] + 1
    return np.where(np.isin(labels, order), 255, 0).astype(np.uint8)


def _boxes_to_mask(
    shape: Tuple[int, int],
    boxes: Sequence[Sequence[float]],
    pad_ratio: float = PAD_RATIO,
) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    for box in boxes:
        x1, y1, x2, y2 = map(float, box)
        pad_x, pad_y = (x2 - x1) * pad_ratio, (y2 - y1) * pad_ratio
        left = max(0, int(round(x1 - pad_x)))
        top = max(0, int(round(y1 - pad_y)))
        right = min(width, int(round(x2 + pad_x)))
        bottom = min(height, int(round(y2 + pad_y)))
        if right > left and bottom > top:
            mask[top:bottom, left:right] = 255
    return mask


def _nms_boxes(
    boxes: List[List[float]], scores: List[float], iou_thr: float = 0.55
) -> List[List[float]]:
    if not boxes:
        return []
    order = sorted(range(len(boxes)), key=lambda index: scores[index], reverse=True)
    keep: list[list[float]] = []
    while order:
        best_i = order.pop(0)
        best_box = boxes[best_i]
        keep.append(best_box)
        x1, y1, x2, y2 = best_box
        area_i = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        rest = []
        for index in order:
            bx1, by1, bx2, by2 = boxes[index]
            inter = max(0.0, min(x2, bx2) - max(x1, bx1)) * max(
                0.0, min(y2, by2) - max(y1, by1)
            )
            area_r = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
            iou = inter / max(area_i + area_r - inter, 1e-9)
            if iou <= iou_thr:
                rest.append(index)
        order = rest
    return keep


def _select_subject_boxes(
    boxes: List[List[float]], scores: List[float], image_shape: Tuple[int, int]
) -> List[List[float]]:
    height, width = image_shape
    if not boxes:
        return []
    center = np.array([width / 2.0, height / 2.0])
    img_area = float(width * height)
    ranked = []
    for box, score in zip(boxes, scores):
        x1, y1, x2, y2 = box
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        box_center = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0])
        distance = np.linalg.norm((box_center - center) / np.array([width, height]))
        center_score = max(0.0, 1.0 - float(distance))
        ranked.append((float(score) * 0.6 + min(area / img_area, 1.0) * 0.25 + center_score * 0.15, box))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [box for _, box in ranked[:3]]
    selected_scores = [scores[boxes.index(box)] for box in selected]
    return _nms_boxes(selected, selected_scores)


def _extract_subject(
    biref: np.ndarray, boxes: List[List[float]], scores: List[float]
) -> np.ndarray:
    import cv2

    mask = np.clip(np.asarray(biref, dtype=np.float32), 0.0, 1.0)
    bin_mask = (mask >= 0.5).astype(np.uint8) * 255
    if boxes:
        box_mask = _boxes_to_mask(mask.shape[:2], boxes)
        bin_mask = cv2.bitwise_and(bin_mask, box_mask)
    bin_mask = _largest_components(bin_mask, max_keep=max(1, min(3, len(boxes) or 1)))
    support = cv2.dilate(bin_mask, np.ones((3, 3), np.uint8), iterations=1)
    # Keep BiRefNet probabilities at the subject boundary instead of flattening
    # every selected pixel to opaque. This is what lets PNG and KT consumers
    # retain hair, glass and packaging edges.
    return np.where(support > 0, np.rint(mask * 255), 0).astype(np.uint8)


def _compose_centered_bgr(
    rgb: np.ndarray,
    mask: np.ndarray,
    canvas: int = CANVAS_SIZE,
    fill: float = SUBJECT_FILL,
) -> np.ndarray:
    import cv2

    mask_u8 = np.asarray(mask, dtype=np.uint8)
    ys, xs = np.where(mask_u8 > 0)
    if not len(xs):
        return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop_rgb, crop_a = rgb[y1:y2, x1:x2], mask_u8[y1:y2, x1:x2]
    scale = min(canvas * fill / crop_rgb.shape[1], canvas * fill / crop_rgb.shape[0])
    out_w, out_h = max(1, round(crop_rgb.shape[1] * scale)), max(1, round(crop_rgb.shape[0] * scale))
    crop_rgb = cv2.resize(crop_rgb, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
    crop_a = cv2.resize(crop_a, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
    canvas_img = np.full((canvas, canvas, 3), 255, dtype=np.uint8)
    gap_x, gap_y = (canvas - out_w) // 2, (canvas - out_h) // 2
    alpha = crop_a.astype(np.float32)[..., None] / 255.0
    region = canvas_img[gap_y : gap_y + out_h, gap_x : gap_x + out_w]
    region[:] = (crop_rgb * alpha + region * (1.0 - alpha)).astype(np.uint8)
    return cv2.cvtColor(canvas_img, cv2.COLOR_RGB2BGR)


def _compose_centered_bgra(
    rgb: np.ndarray,
    mask: np.ndarray,
    canvas: int = CANVAS_SIZE,
    fill: float = SUBJECT_FILL,
) -> Optional[np.ndarray]:
    """Place a subject on a transparent canvas while preserving soft edges."""
    import cv2

    alpha = np.clip(np.asarray(mask), 0, 255).astype(np.uint8)
    ys, xs = np.where(alpha > 0)
    if not len(xs):
        return None
    x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop_rgb, crop_a = np.asarray(rgb)[y1:y2, x1:x2], alpha[y1:y2, x1:x2]
    scale = min(canvas * fill / crop_rgb.shape[1], canvas * fill / crop_rgb.shape[0])
    out_w = max(1, round(crop_rgb.shape[1] * scale))
    out_h = max(1, round(crop_rgb.shape[0] * scale))
    crop_rgb = cv2.resize(crop_rgb, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
    crop_a = cv2.resize(crop_a, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
    result = np.zeros((canvas, canvas, 4), dtype=np.uint8)
    gap_x, gap_y = (canvas - out_w) // 2, (canvas - out_h) // 2
    result[gap_y:gap_y + out_h, gap_x:gap_x + out_w, :3] = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
    result[gap_y:gap_y + out_h, gap_x:gap_x + out_w, 3] = crop_a
    return result


class ProductCutoutEngine:
    def __init__(self) -> None:
        self._lock = RLock()
        self._ready = False
        self._model_root: Optional[Path] = None
        self._device = "cpu"
        self._biref = None
        self._biref_transform = None
        self._dino = None
        self._dino_processor = None

    def ready(self) -> bool:
        with self._lock:
            return self._ready

    def load(self, model_root: Optional[str] = None) -> bool:
        with self._lock:
            if self._ready:
                return True
            try:
                import torch
                from torchvision import transforms
                from transformers import AutoModelForImageSegmentation, AutoModelForZeroShotObjectDetection, AutoProcessor

                root = Path(model_root).resolve() if model_root else resolve_pretrained_root()
                biref_dir = _ensure_local_model(_HF_BIREF, root / "BiRefNet")
                dino_dir = _ensure_local_model(_HF_DINO, root / "GroundingDINO")
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                print(f"[product.cutout] loading BiRefNet device={self._device}")
                self._biref = AutoModelForImageSegmentation.from_pretrained(
                    str(biref_dir), trust_remote_code=True, local_files_only=True
                ).to(self._device).eval()
                self._biref_transform = transforms.Compose(
                    [
                        transforms.Resize((1024, 1024)),
                        transforms.ToTensor(),
                        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                    ]
                )
                print(f"[product.cutout] loading GroundingDINO path={dino_dir}")
                self._dino_processor = AutoProcessor.from_pretrained(str(dino_dir), local_files_only=True)
                self._dino = AutoModelForZeroShotObjectDetection.from_pretrained(
                    str(dino_dir), local_files_only=True
                ).to(self._device).eval()
                self._model_root, self._ready = root, True
                print("[product.cutout] models ready")
                return True
            except Exception as error:
                self._release_unlocked()
                print(f"[product.cutout] load failed: {error}")
                return False

    def unload(self) -> None:
        with self._lock:
            self._release_unlocked()
        print("[product.cutout] models unloaded")

    def _release_unlocked(self) -> None:
        self._ready = False
        self._biref = self._biref_transform = self._dino = self._dino_processor = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _infer_subject(self, bgr: np.ndarray):
        if not self.ready() or not isinstance(bgr, np.ndarray) or bgr.ndim != 3:
            return None
        try:
            import cv2
            import torch
            from PIL import Image

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            with self._lock, torch.no_grad():
                biref_dtype = next(self._biref.parameters()).dtype
                biref_input = self._biref_transform(image).unsqueeze(0).to(
                    device=self._device, dtype=biref_dtype
                )
                outputs = self._biref(biref_input)
                preds = outputs[-1] if isinstance(outputs, (tuple, list)) else outputs
                if isinstance(preds, (tuple, list)):
                    preds = preds[-1]
                biref = torch.sigmoid(preds).squeeze().detach().float().cpu().numpy()
                biref = cv2.resize(biref, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
                inputs = self._dino_processor(images=image, text=_prompt_text(AUTO_PROMPTS), return_tensors="pt")
                dino_dtype = next(self._dino.parameters()).dtype
                inputs = {
                    key: value.to(device=self._device, dtype=dino_dtype)
                    if torch.is_floating_point(value) else value.to(self._device)
                    for key, value in inputs.items()
                }
                dino_outputs = self._dino(**inputs)
                postprocess = self._dino_processor.post_process_grounded_object_detection
                threshold_name = (
                    "box_threshold" if "box_threshold" in inspect.signature(postprocess).parameters else "threshold"
                )
                result = postprocess(
                    dino_outputs,
                    inputs["input_ids"],
                    text_threshold=TEXT_THRESHOLD,
                    target_sizes=[image.size[::-1]],
                    **{threshold_name: BOX_THRESHOLD},
                )[0]
            boxes = result["boxes"].detach().cpu().tolist()
            scores = result["scores"].detach().cpu().tolist()
            boxes = _select_subject_boxes(boxes, scores, bgr.shape[:2])
            mask = _extract_subject(biref, boxes, scores)
            return rgb, mask
        except Exception as error:
            print(f"[product.cutout] infer failed: {error}")
            return None

    def cutout_bgr(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        result = self._infer_subject(bgr)
        return None if result is None else _compose_centered_bgr(*result)

    def cutout_bgra(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        result = self._infer_subject(bgr)
        return None if result is None else _compose_centered_bgra(*result)


_engine_lock = Lock()
_engine: Optional[ProductCutoutEngine] = None


def get_product_cutout_engine() -> ProductCutoutEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ProductCutoutEngine()
        return _engine


def load_product_cutout() -> bool:
    return get_product_cutout_engine().load()


def unload_product_cutout() -> None:
    global _engine
    with _engine_lock:
        engine, _engine = _engine, None
    if engine is not None:
        engine.unload()

