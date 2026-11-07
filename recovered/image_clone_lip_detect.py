"""Batch face and landmark facade for offline lip-region preprocessing."""

from __future__ import annotations

from pathlib import Path
import math
import numpy as np

from .image_scrfd import SCRFD
from .image_face_detect import FaceDetect


class ScrfdFaceDetector:
    def __init__(self,model_dir,conf_threshold=.6):
        self.conf_threshold=conf_threshold
        self.last_detection=None
        self.detector=FaceDetect(cpu=False,model_path=model_dir)

    def detect(self,images):
        output=[]
        for image in images:
            detections,_ = self.detector.get_bboxes(image,thresh=self.conf_threshold)
            if detections is not None and len(detections):
                bboxes_xywh=[]
                for bbox in detections:
                    x1,y1,x2,y2,_score=bbox.astype(np.float32)
                    bboxes_xywh.append([x1,y1,x2-x1,y2-y1])
                current_detection=(
                    np.asarray(bboxes_xywh,dtype=np.float32),
                    list(range(len(bboxes_xywh))),
                )
                self.last_detection=current_detection
                output.append(current_detection)
            elif self.last_detection is None:
                output.append((np.array([]),[]))
            else:
                output.append(self.last_detection)
        return output

    def release(self):
        self.detector=None


class LipDetector:
    def __init__(self,weight_base_dir):
        try:import torch
        except ImportError as error:raise RuntimeError("唇部关键点检测需要 torch") from error
        from .pfld_mobileone import PFLD_GhostOne
        self.torch=torch;self.weight_base_dir=Path(weight_base_dir)
        face_model_dir=self.weight_base_dir/"scrfd_2.5g_kps.onnx"
        self.face_detector=ScrfdFaceDetector(face_model_dir)
        checkpoint_path=self.weight_base_dir/"checkpoint_epoch_335.pth.tar"
        checkpoint=torch.load(checkpoint_path)
        self.det_net=PFLD_GhostOne().cuda()
        self.det_net.load_state_dict(checkpoint["pfld_backbone"]);self.det_net.eval()
        mean_face_path=self.weight_base_dir/"mean_face.txt"
        with open(mean_face_path,"r") as mean_file:
            self.mean_face=np.asarray(mean_file.read().split(" "),dtype=np.float32)

    def _face_det(self,images):
        import cv2
        crops_list=[];offsets_list=[]
        detections=self.face_detector.detect(images)
        for image,(boxes,indices) in zip(images,detections):
            boxes=np.asarray(boxes)
            image_crops=[];image_offsets=[]
            for raw_index in indices:
                index=int(np.asarray(raw_index).reshape(-1)[0]);box=boxes[index]
                x1,y1=int(box[0]),int(box[1]);x2,y2=int(box[0]+box[2]),int(box[1]+box[3])
                width,height=x2-x1,y2-y1;cx,cy=(x2+x1)//2,(y2+y1)//2
                boxsize=int(np.max(np.asarray([width,height]))*1.05)
                xy=np.asarray((cx-boxsize//2,cy-boxsize//2),dtype=np.int32)
                x1,y1=xy;x2,y2=xy+boxsize
                image_height,image_width,_=image.shape
                dx,dy=max(0,-x1),max(0,-y1);x1,y1=max(0,x1),max(0,y1)
                edx,edy=max(0,x2-image_width),max(0,y2-image_height)
                x2,y2=min(image_width,x2),min(image_height,y2)
                cropped=image[y1:y2,x1:x2]
                if dx>0 or dy>0 or edx>0 or edy>0:
                    cropped=cv2.copyMakeBorder(cropped,dy,edy,dx,edx,cv2.BORDER_CONSTANT,0)
                    y1-=dy;x1-=dx
                image_crops.append(cropped);image_offsets.append((x1,y1))
                break
            crops_list.append(image_crops);offsets_list.append(image_offsets)
        return crops_list,offsets_list

    def detect_landmarks(self,images):
        import cv2
        images=list(images);crops_list,offsets_list=self._face_det(images)
        all_crops=[];all_info=[]
        for image_index,crops in enumerate(crops_list):
            for crop_index,crop in enumerate(crops):
                height,width=crop.shape[:2]
                resized=cv2.resize(crop,(192,192))
                all_crops.append(resized)
                offset_x,offset_y=offsets_list[image_index][crop_index]
                all_info.append((image_index,width,height,offset_x,offset_y))
        results=[[] for _ in images]
        if not all_crops:return results
        batch_input=np.stack(all_crops).astype(np.float32)/255.0
        batch_input=batch_input.transpose(0,3,1,2)
        batch_input=self.torch.from_numpy(batch_input).cuda()
        with self.torch.no_grad():landmarks=self.det_net(batch_input)
        batch_landmarks=landmarks.cpu().detach().numpy()+self.mean_face
        for landmark_idx,(image_index,width,height,offset_x,offset_y) in enumerate(all_info):
            points=batch_landmarks[landmark_idx].reshape(-1,2)
            points[:,0]*=width;points[:,1]*=height
            points[:,0]+=offset_x;points[:,1]+=offset_y
            results[image_index].append(points.astype(np.int32))
        return results


def face_det(img, model):
    """Crop the first SCRFD face using the geometry in the native module."""
    import cv2

    cropped_imgs=[];boxes_list=[];center_list=[];alpha_list=[]
    detected=model.detect(img)
    if len(detected)==3:
        bboxes,indices,kps=detected
    else:
        # The shared recovered SCRFD returns xyxy+score and keypoints directly.
        detections,kps=detected
        bboxes=np.asarray(detections,dtype=np.float32).copy()
        if bboxes.size:
            bboxes[:,2]=bboxes[:,2]-bboxes[:,0]
            bboxes[:,3]=bboxes[:,3]-bboxes[:,1]
        indices=range(len(bboxes))
    for raw_index in indices:
        index=int(np.asarray(raw_index).reshape(-1)[0])
        x1,y1=int(bboxes[index,0]),int(bboxes[index,1])
        x2,y2=int(bboxes[index,0]+bboxes[index,2]),int(bboxes[index,1]+bboxes[index,3])
        p1,p2=kps[index,0],kps[index,1]
        width,height=x2-x1,y2-y1
        cx,cy=(x2+x1)//2,(y2+y1)//2
        boxsize=int(np.max(np.asarray([width,height]))*1.05)
        xy=np.asarray((cx-boxsize//2,cy-boxsize//2),dtype=np.int32)
        x1,y1=xy
        x2,y2=xy+boxsize
        image_height,image_width,_=img.shape
        dx,dy=max(0,-x1),max(0,-y1)
        x1,y1=max(0,x1),max(0,y1)
        edx,edy=max(0,x2-image_width),max(0,y2-image_height)
        x2,y2=min(image_width,x2),min(image_height,y2)
        cropped=img[y1:y2,x1:x2]
        if dx>0 or dy>0 or edx>0 or edy>0:
            cropped=cv2.copyMakeBorder(
                cropped,dy,edy,dx,edx,cv2.BORDER_CONSTANT,0
            )
            y1-=dy;x1-=dx
        center=(int((x2-x1)//2),int((y2-y1)//2))
        boxes_list.append([x1,y1,x2,y2]);center_list.append(center)
        alpha=math.atan2(p2[1]-p1[1],p2[0]-p1[0])*180/math.pi
        # The compiled code computes this matrix even though it does not warp.
        cv2.getRotationMatrix2D(center,alpha,1)
        cropped_imgs.append(cropped);alpha_list.append(alpha)
        break
    return cropped_imgs,boxes_list,center_list,alpha_list


def _lip_weight_dir():
    candidates=[
        Path(__file__).resolve().parents[1]/"yunchuang_v122"/"_internal"/"assets"/"pretrained_models"/"lip_detect_weights",
        Path.cwd()/"_internal"/"assets"/"pretrained_models"/"lip_detect_weights",
        Path.cwd()/"assets"/"pretrained_models"/"lip_detect_weights",
    ]
    for candidate in candidates:
        if (candidate/"mean_face.txt").is_file():return candidate
    return candidates[0]


class _LandmarkSCRFD:
    """Match the older detector's `detect(img)` threshold contract."""
    def __init__(self,model_path):
        self.backend=SCRFD(str(model_path))
        self.backend.prepare(0,input_size=(640,640),nms_thresh=.5)
    def detect(self,img):
        return self.backend.detect(img,thresh=.1)


class Landmark:
    def __init__(self):
        try:
            import torch
            from .pfld_mobileone import PFLD_GhostOne as PFLDInference
        except ImportError as error:
            raise RuntimeError("关键点检测需要 torch") from error
        model_dir=_lip_weight_dir()
        with open(model_dir/"mean_face.txt","r") as f_mean_face:
            mean_face=f_mean_face.read()
        self.mean_face=np.asarray(mean_face.split(" "),dtype=np.float32)
        self.det_net=_LandmarkSCRFD(model_dir/"scrfd_2.5g_kps.onnx")
        checkpoint=torch.load(model_dir/"checkpoint_epoch_335.pth.tar")
        self.pfld_backbone=PFLDInference().cuda()
        self.pfld_backbone.load_state_dict(checkpoint["pfld_backbone"])
        self.pfld_backbone.eval()

    def detect(self,img_path):
        import cv2
        import torch
        img=cv2.imread(str(img_path));img_ori=img.copy()
        cropped_imgs,boxes_list,_center_list,_alpha_list=face_det(img,self.det_net)
        cropped=cropped_imgs[0]
        height,width=cropped.shape[:2]
        x1,y1,_x2,_y2=boxes_list[0]
        input_image=cv2.resize(cropped,(192,192))
        input_image=np.asarray(input_image,dtype=np.float32)/255.0
        input_image=input_image.transpose(2,0,1)
        input_tensor=torch.from_numpy(input_image)[None].cuda()
        landmarks=self.pfld_backbone(input_tensor)
        pre_landmark=landmarks[0].cpu().detach().numpy()
        pre_landmark=pre_landmark+self.mean_face
        pre_landmark=pre_landmark.reshape(-1,2)
        pre_landmark[:,0]*=width;pre_landmark[:,1]*=height
        return pre_landmark.astype(np.int32),x1,y1
