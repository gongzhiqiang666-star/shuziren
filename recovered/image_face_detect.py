"""SCRFD + PFLD facade used by preprocessing and realtime readers."""

from __future__ import annotations

from pathlib import Path
import numpy as np

from .image_scrfd import SCRFD


def normalize_model_dir(model_path):
    path = Path(model_path).expanduser().resolve()
    return path.parent if path.is_file() else path


def resolve_model_file(model_path, mode):
    root = normalize_model_dir(model_path)
    names = {"scrfd_500m": "scrfd_500m_bnkps_shape640x640.onnx", "scrfd_10g": "scrfd_10g_bnkps.onnx"}
    expected = names.get(mode, mode if str(mode).endswith(".onnx") else names["scrfd_500m"])
    matches = list(root.rglob(expected)) if root.is_dir() else []
    if not matches: raise FileNotFoundError(f"找不到人脸检测模型 {expected}: {root}")
    return matches[0]


def resolve_landmark_model_file(model_path):
    root = normalize_model_dir(model_path); name = "pfld_robust_sim_bs1_8003.onnx"
    matches = list(root.rglob(name)) if root.is_dir() else []
    if not matches: raise FileNotFoundError(f"找不到关键点模型 {name}: {root}")
    return matches[0]


def _ort_session(path, cpu):
    try: import onnxruntime
    except ImportError as error: raise RuntimeError("人脸模型推理需要 onnxruntime") from error
    wanted = ["CPUExecutionProvider"] if cpu else ["CUDAExecutionProvider", "CPUExecutionProvider"]
    available = set(onnxruntime.get_available_providers())
    return onnxruntime.InferenceSession(str(path), providers=[name for name in wanted if name in available])


def convert98to68(list_info):
    source=np.asarray(list_info);points=source[0,0:196];info=[]
    def append_point(index):info.extend((points[index*2],points[index*2+1]))
    for index in range(17):append_point(index*2)
    for index in range(33,38):append_point(index)
    for index in range(42,47):append_point(index)
    for index in range(51,61):append_point(index)
    def midpoint(first,second):
        return ((float(points[first*2])+float(points[second*2]))/2.0,
                (float(points[first*2+1])+float(points[second*2+1]))/2.0)
    for value in (
        midpoint(60,62),midpoint(62,64),(points[64*2],points[64*2+1]),
        midpoint(64,66),midpoint(60,66),(points[68*2],points[68*2+1]),
        midpoint(68,70),midpoint(70,72),(points[72*2],points[72*2+1]),
        midpoint(72,74),midpoint(68,74),
    ):info.extend(value)
    for index in range(76,96):append_point(index)
    flat=source.reshape(-1)
    for index in range(len(flat[196:])):info.append(flat[196+index])
    return np.asarray(info)


class pfpld:
    def __init__(self, cpu=False, model_path="."):
        try:import onnxruntime
        except ImportError as error:raise RuntimeError("人脸模型推理需要 onnxruntime") from error
        self.onnx_path=str(model_path)+"/pfpld_robust_sim_bs1_8003.onnx"
        try:self.ort_session=onnxruntime.InferenceSession(self.onnx_path)
        except Exception:raise RuntimeError("load onnx failed")
        self.ort_session.set_providers(["CPUExecutionProvider" if cpu else "CUDAExecutionProvider"])
        self.input_name=self.ort_session.get_inputs()[0].name

    def forward(self, input):
        import cv2
        size=input.shape
        data=(cv2.resize(input,(112,112))/255).astype(np.float32).transpose(2,0,1)[None]
        prediction=self.ort_session.run(None,{self.input_name:data})
        landmarks=convert98to68(prediction[1])
        return landmarks.reshape(-1,68,2)*size[:2][::-1]


class FaceDetect:
    def __init__(self, mode="scrfd_500m", cpu=False, model_path="."):
        if mode=="scrfd_500m":scrfd_model_path=str(model_path)+"/scrfd_500m_bnkps_shape640x640.onnx"
        elif mode=="scrfd_10g":scrfd_model_path=str(model_path)+"/scrfd_10g_bnkps.onnx"
        else:raise ValueError(mode)
        self.det_model=SCRFD(scrfd_model_path,cpu=cpu)
        self.det_model.prepare(-1 if cpu else 0,input_size=(640,640))
        self.landmark=pfpld(cpu,model_path)

    def get_bboxes(self, image, thresh=.6, max_num=0):
        import cv2
        if not isinstance(image, np.ndarray):
            image = cv2.imread(str(image))
            if image is None: raise ValueError("无法读取图像")
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.det_model.detect(
            image, thresh=thresh, max_num=max_num, metric="default"
        )
