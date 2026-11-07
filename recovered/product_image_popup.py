"""Recovered OpenCV product-image synchronization popup."""

from __future__ import annotations

import math
from threading import Event, RLock, Thread
from time import perf_counter
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np

_WINDOW_NAME = "Product Image Sync"
_WINDOW_SIZE = 640
_MAX_SRC_SIDE = 2048
_GREENSCREEN_BGR = (0, 255, 0)
_PLACEHOLDER_TEXT = "Ready - drag this window"
_MIN_JITTER_LEVEL = 1
_MAX_JITTER_LEVEL = 10
_DEFAULT_JITTER_LEVEL = 5
_JITTER_SPEED = 1.7
_JITTER_X = 0.012
_JITTER_Y = 0.010
_JITTER_ZOOM = 0.018
_SCALE_AMP = 0.025
_PAN_X = 0.014
_PAN_Y = 0.012


def clamp_product_image_jitter_level(value: Any) -> int:
    try:
        level = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        level = _DEFAULT_JITTER_LEVEL
    return max(_MIN_JITTER_LEVEL, min(_MAX_JITTER_LEVEL, level))


def product_image_jitter_strength(level: Any) -> float:
    return clamp_product_image_jitter_level(level) / _DEFAULT_JITTER_LEVEL


def _greenscreen_frame() -> np.ndarray:
    return np.full((_WINDOW_SIZE, _WINDOW_SIZE, 3), _GREENSCREEN_BGR, dtype=np.uint8)


def _limit_src(frame: np.ndarray) -> np.ndarray:
    import cv2

    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= _MAX_SRC_SIDE:
        return frame
    scale = _MAX_SRC_SIDE / longest
    return cv2.resize(
        frame,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _fit_frame(frame: np.ndarray) -> np.ndarray:
    import cv2

    source = _limit_src(frame)
    src_h, src_w = source.shape[:2]
    if src_h <= 0 or src_w <= 0:
        return _greenscreen_frame()
    scale = min(_WINDOW_SIZE / src_w, _WINDOW_SIZE / src_h)
    out_w, out_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    scaled = cv2.resize(source, (out_w, out_h), interpolation=interpolation)
    target = _greenscreen_frame()
    x = (_WINDOW_SIZE - out_w) // 2
    y = (_WINDOW_SIZE - out_h) // 2
    target[y : y + out_h, x : x + out_w] = scaled
    return target


def _placeholder(text: str) -> np.ndarray:
    import cv2

    frame = _greenscreen_frame()
    label = (text or _PLACEHOLDER_TEXT).encode("ascii", "replace").decode("ascii")
    cv2.putText(
        frame,
        label,
        (24, _WINDOW_SIZE // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return frame


def _normalize_pic(url: str) -> str:
    url = (url or "").strip()
    return "https:" + url if url.startswith("//") else url


def _download_image(url: str) -> Optional[np.ndarray]:
    import cv2
    from urllib.request import Request, urlopen

    url = _normalize_pic(url)
    if not url:
        return None
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=10) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        if not data or len(data) > 16 * 1024 * 1024:
            return None
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def apply_product_image_jitter(
    src: np.ndarray,
    t: float,
    out_w: int,
    out_h: int,
    level: Any = _DEFAULT_JITTER_LEVEL,
) -> np.ndarray:
    import cv2

    strength = product_image_jitter_strength(level)
    phase = float(t) * _JITTER_SPEED
    zoom = 1.0 + strength * (
        _SCALE_AMP * math.sin(phase * 0.73) + _JITTER_ZOOM * math.sin(phase * 1.31)
    )
    pan_x = strength * (_PAN_X * math.sin(phase) + _JITTER_X * math.sin(phase * 2.17))
    pan_y = strength * (_PAN_Y * math.cos(phase * 0.91) + _JITTER_Y * math.sin(phase * 1.79))
    src_h, src_w = src.shape[:2]
    needed_zoom = max(out_w / src_w, out_h / src_h) * zoom
    scaled_w = max(out_w, math.ceil(src_w * needed_zoom))
    scaled_h = max(out_h, math.ceil(src_h * needed_zoom))
    interp = cv2.INTER_AREA if needed_zoom < 1.0 else cv2.INTER_LINEAR
    scaled = cv2.resize(src, (scaled_w, scaled_h), interpolation=interp)
    max_dx, max_dy = scaled_w - out_w, scaled_h - out_h
    x = int(round(max_dx * (0.5 + pan_x)))
    y = int(round(max_dy * (0.5 + pan_y)))
    x, y = max(0, min(max_dx, x)), max(0, min(max_dy, y))
    return scaled[y : y + out_h, x : x + out_w].copy()


class ProductImagePopup:
    def __init__(self) -> None:
        self._lock = RLock()
        self._stop = Event()
        self._thread: Optional[Thread] = None
        self._frames: dict[int, np.ndarray] = {}
        self._frame = _placeholder(_PLACEHOLDER_TEXT)
        self._geom: Optional[Tuple[int, int, int, int]] = None
        self._shown_goods_id: Optional[int] = None
        self._jitter_enabled = False
        self._jitter_level = _DEFAULT_JITTER_LEVEL

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def showing_product(self) -> bool:
        with self._lock:
            return self._shown_goods_id is not None

    def preload_products(
        self,
        items: Sequence[Mapping[str, str]],
        *,
        enable_cutout: bool,
        enable_jitter: bool = False,
        jitter_level: Any = _DEFAULT_JITTER_LEVEL,
    ) -> None:
        engine = None
        if enable_cutout:
            try:
                from .product_cutout import get_product_cutout_engine

                engine = get_product_cutout_engine()
                if not engine.ready():
                    engine.load()
            except Exception:
                engine = None
        frames: dict[int, np.ndarray] = {}
        for index, item in enumerate(items):
            goods_id = int(item.get("goods_id") or item.get("goodsId") or index)
            image = _download_image(str(item.get("item_pic") or item.get("itemPic") or ""))
            if image is None:
                continue
            if engine is not None and engine.ready():
                cutout = engine.cutout_bgr(image)
                if cutout is not None:
                    image = cutout
            frames[goods_id] = _fit_frame(image)
        with self._lock:
            self._frames = frames
            self._jitter_enabled = bool(enable_jitter)
            self._jitter_level = clamp_product_image_jitter_level(jitter_level)

    def show_product(self, *, goods_id: int, item_pic: str = "", item_name: str = "") -> None:
        goods_id = int(goods_id)
        with self._lock:
            frame = self._frames.get(goods_id)
        if frame is None and item_pic:
            image = _download_image(item_pic)
            frame = _fit_frame(image) if image is not None else None
        with self._lock:
            self._shown_goods_id = goods_id
            self._frame = frame if frame is not None else _placeholder(f"{item_name or goods_id} not preloaded")
        self._ensure_window()

    def show_greenscreen(self) -> None:
        with self._lock:
            self._shown_goods_id = None
            self._frame = _greenscreen_frame()
        self._ensure_window()

    def stop(self) -> None:
        import cv2

        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None
        try:
            cv2.destroyWindow(_WINDOW_NAME)
        except Exception:
            pass

    def _ensure_window(self) -> None:
        if self.running():
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="product-image-popup", daemon=True)
        self._thread.start()

    def _read_geom(self) -> Optional[Tuple[int, int, int, int]]:
        import cv2

        try:
            geom = tuple(map(int, cv2.getWindowImageRect(_WINDOW_NAME)))
            return geom if geom[2] > 0 and geom[3] > 0 else None
        except Exception:
            return None

    def _loop(self) -> None:
        import cv2

        try:
            cv2.namedWindow(_WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
            cv2.resizeWindow(_WINDOW_NAME, _WINDOW_SIZE, _WINDOW_SIZE)
            start = perf_counter()
            while not self._stop.is_set():
                with self._lock:
                    frame = self._frame.copy()
                    jitter = self._jitter_enabled and self._shown_goods_id is not None
                    level = self._jitter_level
                if jitter:
                    frame = apply_product_image_jitter(
                        frame, perf_counter() - start, _WINDOW_SIZE, _WINDOW_SIZE, level
                    )
                cv2.imshow(_WINDOW_NAME, frame)
                if cv2.waitKey(16) & 0xFF == 27:
                    self._stop.set()
                geom = self._read_geom()
                if geom is not None:
                    self._geom = geom
        finally:
            try:
                cv2.destroyWindow(_WINDOW_NAME)
            except Exception:
                pass


_popup_lock = RLock()
_popup: Optional[ProductImagePopup] = None


def get_product_image_popup() -> ProductImagePopup:
    global _popup
    with _popup_lock:
        if _popup is None:
            _popup = ProductImagePopup()
        return _popup


def close_product_image_popup() -> None:
    global _popup
    with _popup_lock:
        popup, _popup = _popup, None
    if popup is not None:
        popup.stop()

