"""S3FD inference wrapper."""

from __future__ import annotations

import numpy as np

from .s3fd_nets import S3FDNet


class S3FD:
    def __init__(self,weight_path=".sfd_face.pth",device="cuda"):
        try:import torch
        except ImportError as error:raise RuntimeError("S3FD 需要 torch") from error
        self.torch=torch;self.device=torch.device(device if str(device).startswith("cuda") and torch.cuda.is_available() else "cpu")
        self.net=S3FDNet(str(self.device));state=torch.load(weight_path,map_location=self.device)
        if isinstance(state,dict) and "state_dict" in state:state=state["state_dict"]
        state={k.removeprefix("module."):v for k,v in state.items()};self.net.load_state_dict(state);self.net.to(self.device).eval()

    def detect_faces(self,image,conf_th=.8,scales=[1]):
        import cv2
        detections=[]
        for scale in scales:
            resized=cv2.resize(image,None,fx=scale,fy=scale);data=resized.astype(np.float32)-np.array([104,117,123],np.float32)
            tensor=self.torch.from_numpy(data.transpose(2,0,1)).unsqueeze(0).to(self.device)
            with self.torch.no_grad():output=self.net(tensor)[0,1]
            for row in output.detach().cpu().numpy():
                if row[0]<conf_th:continue
                detections.append([row[1]*resized.shape[1]/scale,row[2]*resized.shape[0]/scale,row[3]*resized.shape[1]/scale,row[4]*resized.shape[0]/scale,row[0]])
        detections.sort(key=lambda row:row[4],reverse=True);return detections
