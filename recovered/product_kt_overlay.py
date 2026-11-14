"""Asset resolution for the recovered product KT board module."""

from pathlib import Path
from threading import Lock
from dataclasses import dataclass
from itertools import combinations

KT_BOARD_CACHE_NAME = "kt_board_boxes.npz"


@dataclass(frozen=True)
class _Marker:
    cx: float
    cy: float
    ww: float
    hh: float
    area: float

    @property
    def point(self):
        import numpy as np
        return np.asarray((self.cx, self.cy), dtype=np.float32)


def _client_search_roots():
    module = Path(__file__).resolve()
    candidates = (Path.cwd(), module.parent.parent, module.parent.parent / "yunchuang_v122" / "_internal",
                  Path(getattr(__import__("sys"), "executable", module)).resolve().parent)
    result = []
    for root in candidates:
        value = str(root.resolve())
        if value not in result:
            result.append(value)
    return result


def _marker_point(marker):
    if hasattr(marker, "point"):
        return marker.point
    import numpy as np
    if hasattr(marker, "cx"):
        return np.asarray((marker.cx, marker.cy), dtype=np.float32)
    return np.asarray(marker, dtype=np.float32).reshape(-1)[:2]


def _nms_markers(markers, dist):
    kept = []
    for marker in sorted(markers or [], key=lambda item: float(getattr(item, "area", 0)), reverse=True):
        point = _marker_point(marker)
        if all(float(__import__("numpy").linalg.norm(point - _marker_point(other))) >= float(dist) for other in kept):
            kept.append(marker)
    return kept


def _quad_score(pts4):
    import cv2
    import numpy as np
    points = _order_box(np.asarray(pts4, dtype=np.float32))
    if not cv2.isContourConvex(points):
        return float("-inf")
    area = abs(float(cv2.contourArea(points)))
    width, height = _quad_edge_sizes(points)
    if area <= 0 or min(width, height) <= 0:
        return float("-inf")
    edge_lengths = [float(np.linalg.norm(points[(i + 1) % 4] - points[i])) for i in range(4)]
    regularity = min(edge_lengths) / max(edge_lengths)
    return area * (0.5 + 0.5 * regularity)


def _quad_board_overlap(quad, board_mask):
    import cv2
    import numpy as np
    if board_mask is None:
        return 0.0
    mask = np.zeros(board_mask.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(_order_box(quad)).astype(np.int32), 255)
    quad_area = cv2.countNonZero(mask)
    if not quad_area:
        return 0.0
    return cv2.countNonZero(cv2.bitwise_and(mask, board_mask)) / float(quad_area)


def _is_on_white_board(gray, hsv, board_mask, cx, cy, ww, hh):
    import cv2
    x0=max(0,int(cx-ww/2));x1=min(gray.shape[1],int(cx+ww/2)+1)
    y0=max(0,int(cy-hh/2));y1=min(gray.shape[0],int(cy+hh/2)+1)
    if x1<=x0 or y1<=y0:return False
    region=board_mask[y0:y1,x0:x1]
    return cv2.countNonZero(region) >= region.size * 0.6


def _find_white_board(bgr):
    import cv2
    import numpy as np
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,np.asarray((0,0,145),np.uint8),np.asarray((179,90,255),np.uint8))
    kernel=np.ones((7,7),np.uint8);mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel,iterations=2)
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    frame_area=bgr.shape[0]*bgr.shape[1];best=None
    for contour in contours:
        area=cv2.contourArea(contour)
        if area < frame_area*0.05:continue
        rect=cv2.minAreaRect(contour);box=cv2.boxPoints(rect).astype(np.float32)
        overlap=_quad_board_overlap(box,mask)
        score=area*overlap
        if best is None or score>best[0]:best=(score,box)
    if best is None:return None,None
    board=np.zeros(mask.shape,np.uint8);cv2.fillConvexPoly(board,np.rint(_order_box(best[1])).astype(np.int32),255)
    return board,_order_box(best[1])


def _detect_marker_blobs(bgr, board_mask):
    import cv2
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY);hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    dark=cv2.threshold(gray,90,255,cv2.THRESH_BINARY_INV)[1]
    dark=cv2.bitwise_and(dark,board_mask)
    contours,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    markers=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour);area=float(cv2.contourArea(contour))
        if min(w,h)<6 or max(w,h)>min(bgr.shape[:2])*0.35 or not 0.45<=w/max(h,1)<=2.2:continue
        cx=x+w/2;cy=y+h/2
        if _is_on_white_board(gray,hsv,board_mask,cx,cy,w,h):markers.append(_Marker(cx,cy,w,h,area))
    typical=max(8.0,min(bgr.shape[:2])*0.04)
    return _nms_markers(markers,typical)


def _complete_fourth_corner(markers):
    # Three corner markers plus the centre marker can recover the missing
    # parallelogram corner. Preserve marker scale for downstream filtering.
    if len(markers)!=4:return list(markers or [])
    import numpy as np
    points=np.asarray([_marker_point(marker) for marker in markers])
    center_index=int(np.argmin(np.linalg.norm(points-points.mean(axis=0),axis=1)))
    corners=np.delete(points,center_index,axis=0);center=points[center_index]
    inferred=4*center-corners.sum(axis=0)
    template=markers[center_index]
    return list(markers)+[_Marker(float(inferred[0]),float(inferred[1]),float(template.ww),float(template.hh),float(template.area))]


def _select_corners_and_center(markers, board_box):
    import cv2
    import numpy as np
    markers=_complete_fourth_corner(markers)
    best=None
    for chosen in combinations(markers,5):
        points=np.asarray([_marker_point(marker) for marker in chosen])
        for center_index in range(5):
            corners=np.delete(points,center_index,axis=0);quad=_order_box(corners)
            if cv2.pointPolygonTest(quad,tuple(map(float,points[center_index])),False)<=0:continue
            score=_quad_score(quad)
            if board_box is not None:score-=float(np.linalg.norm(points[center_index]-np.mean(board_box,axis=0)))
            if best is None or score>best[0]:
                ordered=[]
                for point in quad:ordered.append(chosen[int(np.argmin(np.linalg.norm(points-point,axis=1)))])
                best=(score,{"tl":ordered[0],"tr":ordered[1],"br":ordered[2],"bl":ordered[3],"center":chosen[center_index]})
    return None if best is None else best[1]


def _quad_from_selection(sel, expand=1.18):
    import numpy as np
    quad=np.asarray([_marker_point(sel[key]) for key in ("tl","tr","br","bl")],dtype=np.float32)
    center=quad.mean(axis=0)
    return _order_box(center+(quad-center)*float(expand))

def kt_board_cache_path(model_dir): return str(Path(model_dir)/KT_BOARD_CACHE_NAME)
def model_has_kt_board_cache(model_dir): return Path(kt_board_cache_path(model_dir)).is_file()

def compute_boxes_from_frames_dir(frames_dir):
    import cv2
    boxes=[]; frame_size=None; hit=0
    for path in _list_frame_paths(frames_dir):
        image=cv2.imread(path,cv2.IMREAD_COLOR)
        if image is None: boxes.append(None); continue
        size=(image.shape[1],image.shape[0])
        if frame_size is None: frame_size=size
        elif size!=frame_size: raise ValueError("KT board frames must have one consistent resolution")
        box=detect_kt_board_quad(image); boxes.append(box)
        if box is not None: hit+=1
    return boxes,frame_size,hit

def save_kt_board_cache(model_dir,boxes,frame_size,hit):
    import numpy as np
    path=Path(kt_board_cache_path(model_dir)); path.parent.mkdir(parents=True,exist_ok=True)
    valid=np.asarray([box is not None for box in boxes],dtype=np.bool_)
    values=np.zeros((len(boxes),4,2),dtype=np.float32)
    for index,box in enumerate(boxes):
        if box is not None: values[index]=np.asarray(box,dtype=np.float32).reshape(4,2)
    np.savez_compressed(path,boxes=values,valid=valid,frame_size=np.asarray(frame_size or (),dtype=np.int32),hit=np.asarray(int(hit)))
    return str(path)

def load_kt_board_cache(model_dir):
    import numpy as np
    with np.load(kt_board_cache_path(model_dir),allow_pickle=False) as data:
        values=data["boxes"]; valid=data["valid"].astype(bool)
        boxes=[values[i].copy() if valid[i] else None for i in range(len(valid))]
        raw=data["frame_size"].tolist(); frame_size=tuple(map(int,raw)) if len(raw)==2 else None
        hit=int(data["hit"])
    return boxes,frame_size,hit

def compute_and_save_kt_board_cache(model_dir):
    boxes,size,hit=compute_boxes_from_frames_dir(Path(model_dir)/"frames")
    save_kt_board_cache(model_dir,boxes,size,hit); return hit


def _resolve_std_kt_board_path(runtime_dir=None):
    module_root = Path(__file__).resolve().parent.parent
    roots = (Path(runtime_dir),) if runtime_dir is not None else (
        module_root,
        module_root / "yunchuang_v122" / "_internal",
    )
    for root in roots:
        board = root / "assets" / "kt_board" / "std_kt_board.png"
        if board.is_file():
            return str(board.resolve())
    return None


def resolve_std_kt_board_path():
    return _resolve_std_kt_board_path()


def render_std_kt_board_image(out_path, *, width=2480, height=3308):
    from PIL import Image, ImageDraw

    board = Image.new("RGB", (2480, 3308), "white")
    draw = ImageDraw.Draw(board)
    size = 272
    corner = [(237, 34), (34, 34), (34, 237), (87, 237), (87, 87), (237, 87)]
    for y, flip_y in ((198, False), (2838, True)):
        for x, flip_x in ((198, False), (2010, True)):
            draw.rectangle((x, y, x + size - 1, y + size - 1), fill="black")
            draw.polygon([
                (x + (size - 1 - dx if flip_x else dx),
                 y + (size - 1 - dy if flip_y else dy))
                for dx, dy in corner
            ], fill="white")

    x, y = 1104, 1518
    draw.rectangle((x, y, x + size - 1, y + size - 1), fill="black")
    for start, end in (((35, 35), (236, 236)), ((35, 236), (236, 35))):
        draw.line([(x + dx, y + dy) for dx, dy in (start, end)], fill="white", width=48)
        for dx, dy in (start, end):
            draw.ellipse((x + dx - 24, y + dy - 24, x + dx + 24, y + dy + 24), fill="white")

    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    board.resize((width, height), Image.Resampling.NEAREST).save(destination)
    return str(destination)


def _order_box(pts):
    import numpy as np

    points = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    sums = points.sum(axis=1)
    differences = points[:, 1] - points[:, 0]
    indices = [sums.argmin(), differences.argmin(), sums.argmax(), differences.argmax()]
    if len(set(indices)) == 4:
        return points[indices]

    center = points.mean(axis=0)
    offsets = points - center
    ordered = points[np.argsort(np.arctan2(offsets[:, 1], offsets[:, 0]))]
    first = np.lexsort((ordered[:, 0], ordered[:, 1], ordered.sum(axis=1)))[0]
    return np.roll(ordered, -first, axis=0)


def _quad_edge_sizes(dst):
    import numpy as np

    top_left, top_right, bottom_right, bottom_left = dst
    width = (np.linalg.norm(top_right - top_left) + np.linalg.norm(bottom_right - bottom_left)) / 2
    height = (np.linalg.norm(bottom_left - top_left) + np.linalg.norm(bottom_right - top_right)) / 2
    return float(width), float(height)


def _contain_inset_quad(dst, product_wh):
    import cv2
    import numpy as np

    width, height = _quad_edge_sizes(dst)
    product_width, product_height = product_wh
    scale = min(width / product_width, height / product_height)
    inset_x = (1 - product_width * scale / width) / 2
    inset_y = (1 - product_height * scale / height) / 2
    unit_square = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
    inset = np.float32([
        [inset_x, inset_y], [1 - inset_x, inset_y],
        [1 - inset_x, 1 - inset_y], [inset_x, 1 - inset_y],
    ])
    transform = cv2.getPerspectiveTransform(unit_square, dst)
    return cv2.perspectiveTransform(inset[None, :, :], transform)[0]


def _paste_on_board(frame, product, box):
    import cv2
    import numpy as np

    height, width = product.shape[:2]
    if height < 2 or width < 2:
        raise ValueError("Product image needs at least two pixels on each axis")
    if product.ndim != 3 or product.shape[2] not in (3, 4):
        raise ValueError("Product image must be BGR or BGRA")
    source = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    destination = _order_box(box)
    if not cv2.isContourConvex(destination):
        raise ValueError("KT board corners must form a convex quadrilateral")
    destination = _contain_inset_quad(destination, (width, height))
    transform = cv2.getPerspectiveTransform(source, destination)
    size = (frame.shape[1], frame.shape[0])
    warped = cv2.warpPerspective(product[..., :3], transform, size)
    source_alpha = product[..., 3] if product.shape[2] == 4 else np.full((height, width), 255, np.uint8)
    mask = cv2.warpPerspective(source_alpha, transform, size, flags=cv2.INTER_LINEAR)
    result = frame.copy()
    alpha = mask.astype(np.float32)[..., None] / 255.0
    result[:] = np.clip(
        warped.astype(np.float32) * alpha + result.astype(np.float32) * (1.0 - alpha), 0, 255
    ).astype(np.uint8)
    return result


def _green_mask(bgr):
    import cv2

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (35, 70, 40), (90, 255, 255))


def detect_kt_board_quad(bgr):
    import cv2

    board_mask,board_box=_find_white_board(bgr)
    if board_mask is not None:
        markers=_detect_marker_blobs(bgr,board_mask)
        selection=_select_corners_and_center(markers,board_box)
        if selection is not None:
            quad=_quad_from_selection(selection)
            if _quad_board_overlap(quad,board_mask)>=0.65:
                return quad
    quad = _quad_from_marker_mask(_green_mask(bgr))
    if quad is not None:
        return quad
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return _quad_from_marker_mask(mask)


def _filter_size_consistency(markers):
    from statistics import median

    if not markers:
        return []
    typical_area = median(area for area, _ in markers)
    return [marker for marker in markers if 0.5 * typical_area <= marker[0] <= 2 * typical_area]


def _quad_from_marker_mask(mask):
    import cv2
    import numpy as np

    _, _, stats, centers = cv2.connectedComponentsWithStats(mask)
    candidates = []
    for (_, _, width, height, area), center in zip(stats[1:], centers[1:]):
        if min(width, height) >= 8 and 0.6 <= width / height <= 1.67:
            if 0.45 <= area / (width * height) <= 0.85:
                candidates.append((width * height, center))
    candidates = _filter_size_consistency(candidates)
    if len(candidates) != 5:
        return None
    areas, points = zip(*candidates)
    if max(areas) > 2 * min(areas):
        return None
    points = np.asarray(points)
    center_index = np.argmin(np.linalg.norm(points - points.mean(axis=0), axis=1))
    quad = _order_box(np.delete(points, center_index, axis=0))
    if not cv2.isContourConvex(quad) or cv2.pointPolygonTest(quad, tuple(points[center_index]), False) <= 0:
        return None
    return quad


class _BoardTracker:
    def __init__(self, alpha=1.0, miss_hold=3):
        self.alpha = alpha
        self.miss_hold = miss_hold
        self.reset()

    def reset(self):
        self._quad = None
        self._misses = 0

    def update(self, quad):
        if quad is None:
            self._misses += 1
            if self._misses > self.miss_hold:
                self.reset()
        else:
            quad = _order_box(quad)
            if self._quad is not None and self.alpha != 1.0:
                quad = (1 - self.alpha) * self._quad + self.alpha * quad
            self._quad = quad
            self._misses = 0
        return None if self._quad is None else self._quad.copy()


def _download_image(url):
    from urllib.error import URLError
    from urllib.request import urlopen

    import cv2
    import numpy as np

    if url.startswith("//"):
        url = "https:" + url
    try:
        with urlopen(url, timeout=10) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        if not data or len(data) > 16 * 1024 * 1024:
            return None
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except (URLError, OSError, ValueError, cv2.error):
        return None


def _list_frame_paths(frames_dir):
    paths = [
        path for path in Path(frames_dir).glob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        and path.stem.isascii() and path.stem.isdecimal()
    ]
    return [str(path) for path in sorted(paths, key=lambda path: (int(path.stem), path.name))]


class ProductKtOverlay:
    def __init__(self):
        self._lock = Lock()
        self._enabled = False
        self._product = None
        self._product_key = None
        self._tracker = _BoardTracker()
        self._boxes = []
        self._frame_size = None
        self._frames_dir = None
        self._initializing = None
        self._precomputed = self._boxes

    def set_enabled(self, enabled):
        with self._lock:
            self._enabled = bool(enabled)
            if not self._enabled:
                self._tracker.reset()

    def enabled(self):
        with self._lock:
            return self._enabled

    def clear(self):
        with self._lock:
            self._product = None
            self._product_key = None
            self._tracker.reset()

    def set_product_image(self, *, goods_id, item_pic, item_name=""):
        import cv2

        product_key = (int(goods_id), str(item_pic or ""))
        with self._lock:
            self._product_key = product_key
            self._product = None
        path = str(item_pic) if item_pic else ""
        if path.startswith(("https://", "http://", "//")):
            product = _download_image(path)
        else:
            product = cv2.imread(path, cv2.IMREAD_UNCHANGED) if path else None
        if product is not None and (product.ndim != 3 or product.shape[2] not in (3, 4)):
            product = None
        with self._lock:
            if self._product_key == product_key:
                self._product = product

    def load_from_model_dir(self, model_dir):
        model_dir = str(Path(model_dir or "").expanduser().resolve())
        frames_dir = str(Path(model_dir) / "frames")
        request = object()
        with self._lock:
            self._initializing = request
        try:
            boxes, frame_size, hit = load_kt_board_cache(model_dir)
        except (OSError, KeyError, ValueError):
            boxes, frame_size, hit = compute_boxes_from_frames_dir(frames_dir)
            save_kt_board_cache(model_dir, boxes, frame_size, hit)
        with self._lock:
            if self._initializing is not request:
                return 0
            self._boxes = list(boxes)
            self._precomputed = self._boxes
            self._frame_size = frame_size
            self._frames_dir = frames_dir
            self._initializing = None
            self._tracker.reset()
        print(f"[product.kt] frames={len(boxes)} hit={hit} path={frames_dir}")
        return int(hit)

    def preload_from_frames_dir(self, frames_dir):
        import cv2

        request = object()
        with self._lock:
            self._initializing = request
            self._boxes = []
            self._precomputed = self._boxes
            self._frame_size = None
            self._frames_dir = str(Path(frames_dir).resolve())
            self._tracker.reset()
        boxes = []
        frame_size = None
        hit = 0
        for path in _list_frame_paths(frames_dir):
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                boxes.append(None)
                continue
            size = (image.shape[1], image.shape[0])
            if frame_size is None:
                frame_size = size
            elif size != frame_size:
                raise ValueError("KT board frames must have one consistent resolution")
            quad = detect_kt_board_quad(image)
            boxes.append(quad)
            if quad is not None:
                hit += 1
        with self._lock:
            if self._initializing is not request:
                return 0
            self._boxes = boxes
            self._precomputed = self._boxes
            self._frame_size = frame_size
            self._initializing = None
            self._tracker.reset()
        return hit

    def has_precomputed(self):
        with self._lock:
            return bool(self._boxes)

    @staticmethod
    def _scale_box(box, src_size, dst_hw):
        import numpy as np

        scaled = np.array(box, dtype=np.float32, copy=True)
        if src_size is not None:
            source_width, source_height = src_size
            height, width = dst_hw
            scaled[:, 0] *= width / source_width
            scaled[:, 1] *= height / source_height
        return scaled

    def apply(self, frame_bgr, physical_index=None):
        import numpy as np

        if frame_bgr is None or not isinstance(frame_bgr, np.ndarray):
            return frame_bgr
        with self._lock:
            if not self._enabled or self._product is None:
                return frame_bgr
            detected = None
            if physical_index is not None and self._boxes:
                cached = self._boxes[int(physical_index) % len(self._boxes)]
                if cached is not None:
                    detected = self._scale_box(cached, self._frame_size, frame_bgr.shape[:2])
            if detected is None:
                detected = detect_kt_board_quad(frame_bgr)
            box = self._tracker.update(detected)
            if box is None:
                return frame_bgr
            try:
                return _paste_on_board(frame_bgr, self._product, box)
            except Exception as error:
                print(f"[product.kt] apply failed: {error}")
                return frame_bgr


_overlay_lock = Lock()
_overlay = None


def get_product_kt_overlay():
    global _overlay
    with _overlay_lock:
        if _overlay is None:
            _overlay = ProductKtOverlay()
        return _overlay


def close_product_kt_overlay():
    global _overlay
    with _overlay_lock:
        if _overlay is not None:
            _overlay.set_enabled(False)
            _overlay.clear()
            _overlay = None


def apply_product_kt_overlay(frame_bgr, physical_index=None):
    return get_product_kt_overlay().apply(frame_bgr, physical_index)


def _ensure_std_kt_board_image(runtime_dir=None):
    existing = _resolve_std_kt_board_path(runtime_dir)
    if existing is not None:
        return existing
    root = Path(runtime_dir) if runtime_dir is not None else Path(__file__).resolve().parent.parent
    destination = root / "assets/kt_board/std_kt_board.png"
    return render_std_kt_board_image(destination)


def ensure_std_kt_board_image():
    return _ensure_std_kt_board_image()
