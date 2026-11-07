"""SCRFD ONNX face detector recovered from the bundled realtime pipelines."""

from __future__ import annotations

import os.path as osp
import numpy as np


def softmax(z):
    assert len(z.shape) == 2
    maximum = np.max(z, axis=1)[:, np.newaxis]
    e_x = np.exp(z - maximum)
    divisor = np.sum(e_x, axis=1)[:, np.newaxis]
    return e_x / divisor


def distance2bbox(points, distance, max_shape=None):
    points, distance = np.asarray(points), np.asarray(distance)
    boxes = np.stack((points[:, 0] - distance[:, 0], points[:, 1] - distance[:, 1],
                      points[:, 0] + distance[:, 2], points[:, 1] + distance[:, 3]), axis=-1)
    if max_shape is not None:
        boxes[:, 0::2] = np.clip(boxes[:, 0::2], 0, max_shape[1])
        boxes[:, 1::2] = np.clip(boxes[:, 1::2], 0, max_shape[0])
    return boxes


def distance2kps(points, distance, max_shape=None):
    points, distance = np.asarray(points), np.asarray(distance)
    outputs = []
    for index in range(0, distance.shape[1], 2):
        x = points[:, 0] + distance[:, index]; y = points[:, 1] + distance[:, index + 1]
        if max_shape is not None:
            x = np.clip(x, 0, max_shape[1]); y = np.clip(y, 0, max_shape[0])
        outputs.extend((x, y))
    return np.stack(outputs, axis=-1)


class SCRFD:
    def __init__(self, model_file=None, session=None, cpu=False):
        self.model_file = model_file
        self.session = session
        self.taskname = "detection"
        self.batched = False
        if session is None:
            assert self.model_file is not None
            assert osp.exists(self.model_file)
            import onnxruntime
            provider = "CPUExecutionProvider" if cpu else "CUDAExecutionProvider"
            self.session = onnxruntime.InferenceSession(
                self.model_file, None, providers=[provider]
            )
        self.center_cache = {}
        self.nms_thresh = .4
        self._init_vars()

    def _init_vars(self):
        input_cfg = self.session.get_inputs()[0]
        input_shape = input_cfg.shape
        if isinstance(input_shape[2], str):
            self.input_size = None
        else:
            self.input_size = tuple(input_shape[2:4][::-1])
        self.input_name = input_cfg.name
        self.input_shape = input_shape
        outputs = self.session.get_outputs()
        if len(outputs[0].shape) == 3:
            self.batched = True
        self.output_names = [output.name for output in outputs]
        self.use_kps = False
        self._num_anchors = 1
        count = len(outputs)
        if count == 6:
            self.fmc = 3
            self._feat_stride_fpn = [8, 16, 32]
            self._num_anchors = 2
        elif count == 9:
            self.fmc = 3
            self._feat_stride_fpn = [8, 16, 32]
            self._num_anchors = 2
            self.use_kps = True
        elif count == 10:
            self.fmc = 5
            self._feat_stride_fpn = [8, 16, 32, 64, 128]
        elif count == 15:
            self.fmc = 5
            self._feat_stride_fpn = [8, 16, 32, 64, 128]
            self.use_kps = True

    def prepare(self, ctx_id, **kwargs):
        if ctx_id < 0:
            self.session.set_providers(["CPUExecutionProvider"])
        nms_thresh = kwargs.get("nms_thresh", None)
        if nms_thresh is not None:
            self.nms_thresh = nms_thresh
        input_size = kwargs.get("input_size", None)
        if input_size is not None:
            if self.input_size is not None:
                print("warning: det_size is already set in scrfd model, ignore")
            else:
                self.input_size = input_size

    def forward(self, img, thresh):
        import cv2
        scores_list, bboxes_list, kpss_list = [], [], []
        input_size = tuple(img.shape[0:2][::-1])
        blob = cv2.dnn.blobFromImage(
            img, 1.0 / 128.0, input_size, (127.5, 127.5, 127.5), swapRB=True
        )
        outputs = self.session.run(self.output_names, {self.input_name: blob})
        levels = len(self._feat_stride_fpn)
        for index, stride in enumerate(self._feat_stride_fpn):
            if self.batched:
                scores = outputs[index][0]
                bbox_preds = outputs[index + levels][0] * stride
                if self.use_kps:
                    kps_preds = outputs[index + levels * 2][0] * stride
            else:
                scores = outputs[index]
                bbox_preds = outputs[index + levels] * stride
                if self.use_kps:
                    kps_preds = outputs[index + levels * 2] * stride
            height, width = blob.shape[2] // stride, blob.shape[3] // stride
            key = (height, width, stride)
            if key not in self.center_cache:
                grid = np.stack(np.mgrid[:height, :width][::-1], axis=-1).astype(np.float32).reshape(-1, 2) * stride
                if self._num_anchors > 1: grid = np.stack([grid] * self._num_anchors, axis=1).reshape(-1, 2)
                if len(self.center_cache) < 100:
                    self.center_cache[key] = grid
                anchors = grid
            else:
                anchors = self.center_cache[key]
            positive = np.where(scores >= thresh)[0]
            scores_list.append(scores[positive]); bboxes_list.append(distance2bbox(anchors, bbox_preds)[positive])
            if self.use_kps:
                kpss_list.append(distance2kps(anchors, kps_preds).reshape(-1, 5, 2)[positive])
        return scores_list, bboxes_list, kpss_list

    def nms(self, dets):
        x1, y1, x2, y2, scores = (dets[:, i] for i in range(5))
        areas = (x2 - x1 + 1) * (y2 - y1 + 1); order = scores.argsort()[::-1]; keep = []
        while order.size:
            index = order[0]; keep.append(int(index))
            xx1, yy1 = np.maximum(x1[index], x1[order[1:]]), np.maximum(y1[index], y1[order[1:]])
            xx2, yy2 = np.minimum(x2[index], x2[order[1:]]), np.minimum(y2[index], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1 + 1) * np.maximum(0, yy2 - yy1 + 1)
            overlap = inter / (areas[index] + areas[order[1:]] - inter)
            order = order[np.where(overlap <= self.nms_thresh)[0] + 1]
        return keep

    def detect(self, img, thresh=.6, input_size=None, max_num=0, metric="default"):
        import cv2
        size = self.input_size if input_size is None else input_size
        assert size is not None
        ratio = float(img.shape[0]) / img.shape[1]
        if ratio > size[1] / size[0]: new_h, new_w = size[1], int(size[1] / ratio)
        else: new_w, new_h = size[0], int(size[0] * ratio)
        scale = float(new_h) / img.shape[0]
        resized = cv2.resize(img, (new_w, new_h)); canvas = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized
        scores, boxes, keypoints = self.forward(canvas, thresh)
        scores = np.vstack(scores); boxes = np.vstack(boxes) / scale
        order = scores.ravel().argsort()[::-1]
        detections = np.hstack((boxes, scores)).astype(np.float32, copy=False)[order, :]
        keypoints = np.vstack(keypoints) / scale if self.use_kps else None
        if keypoints is not None: keypoints = keypoints[order]
        keep = self.nms(detections); detections = detections[keep]
        if keypoints is not None: keypoints = keypoints[keep]
        if max_num and len(detections) > max_num:
            areas = (detections[:, 2] - detections[:, 0]) * (detections[:, 3] - detections[:, 1])
            image_center = img.shape[0] // 2, img.shape[1] // 2
            offsets = np.vstack((
                (detections[:, 0] + detections[:, 2]) / 2 - image_center[1],
                (detections[:, 1] + detections[:, 3]) / 2 - image_center[0],
            ))
            offset = np.sum(np.power(offsets, 2.0), 0)
            values = areas if metric == "max" else areas - offset * 2.0
            selected = values.argsort()[::-1][:max_num]; detections = detections[selected]
            if keypoints is not None: keypoints = keypoints[selected]
        return detections, keypoints


def get_scrfd(name, download=False, root="~/.insightface/models", **kwargs):
    if download:
        from .model_store import get_model_file
        model_file = get_model_file("scrfd_%s" % name, root=root)
    else:
        assert osp.exists(name)
        return SCRFD(name)
    return SCRFD(model_file)


def scrfd_2p5gkps(**kwargs):
    return get_scrfd("2p5gkps", download=True, **kwargs)
