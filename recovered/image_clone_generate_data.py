"""Extract numbered frames and face metadata for offline image cloning."""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np

from .image_face_detect import FaceDetect,pfpld


def read_video_frames(video_path, output_dir):
    frames_dir=Path(output_dir)/"frames";frames_dir.mkdir(parents=True,exist_ok=True)
    capture=cv2.VideoCapture(str(video_path))
    if not capture.isOpened():raise ValueError(f"无法打开视频文件: {video_path}")
    fps=round(capture.get(cv2.CAP_PROP_FPS),2)
    frame_count=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"视频信息: {fps}fps, 总帧数: {frame_count}, 分辨率: {width}x{height}")
    count=0
    while True:
        ok,frame=capture.read()
        if not ok:break
        frame_path=frames_dir/f"{count:06d}.jpg"
        cv2.imwrite(str(frame_path),frame)
        count+=1
    capture.release()
    print(f"视频处理完成，共保存 {count} 帧")
    return {"fps":fps,"width":width,"height":height,"total_frames":count}


def save_frame_data(idx,positions_dir,video_info,frame_data,is_no_face):
    position_data={
        "fps":video_info["fps"],"width":video_info["width"],
        "height":video_info["height"],"is_no_face":is_no_face,
    }
    if "bounding_box" in frame_data:
        value=frame_data["bounding_box"]
        position_data["bounding_box"]=value.tolist() if isinstance(value,np.ndarray) else value
    if "landmarks" in frame_data:
        value=frame_data["landmarks"]
        position_data["landmarks"]=value.tolist() if isinstance(value,np.ndarray) else value
    position_path=Path(positions_dir)/f"{idx:06d}.txt"
    with open(position_path,"w",encoding="utf-8") as stream:
        for key,value in position_data.items():stream.write(f"{key}: {value}\n")


def _face_landmarks(frame,detector,landmark_detector,include_right=True):
    boxes,_=detector.get_bboxes(frame)
    if not len(boxes):return None
    box=boxes[int(np.nanargmax(np.asarray(boxes)[:,4]))]
    x1,y1,x2,y2=np.asarray(box[:4],dtype=np.int32)
    # Native preprocessing includes context beside/below the detector box.
    # Its ratio pass excludes the final right column; its persistence pass includes it.
    pad_x=int((x2-x1)*.1);pad_y=int((y2-y1)*.1)
    x1=max(0,x1-pad_x);x2=min(frame.shape[1],x2+pad_x+int(include_right))
    y2=min(frame.shape[0],y2+pad_y);y1=max(0,y1)
    face_img=frame[y1:y2,x1:x2]
    if face_img.size==0:raise ValueError("Face crop for landmarks is empty.")
    landmarks=np.asarray(landmark_detector.forward(face_img)[0],dtype=np.float32)
    landmarks+=np.asarray([x1,y1],dtype=np.float32)
    return landmarks.astype(np.int32)


def _position_box(landmarks,shape,wh_ratio):
    x,y,width,_=cv2.boundingRect(landmarks.astype(np.int32))
    face_height=width/wh_ratio
    center_x=x+width/2
    xmin=max(0,int(center_x-face_height*.75))
    xmax=min(shape[1],int(center_x+face_height*.75))
    ymin=max(0,int(y-face_height*.15))
    ymax=min(shape[0],int(y+face_height*1.35))
    return np.asarray([ymin,ymax,xmin,xmax])


def process_face_frames(frames_dir,total_frames,output_dir,video_info,img_size=256,cpu=False,model_path="face_detect_utils/resources/"):
    print("初始化人脸检测模型...")
    try:
        detector=FaceDetect(cpu=cpu,model_path=model_path)
        landmark_detector=pfpld(cpu=cpu,model_path=model_path)
    except Exception as error:
        if cpu:raise
        print(f"警告: GPU人脸检测初始化失败，切换CPU重试: {error}")
        cpu=True
        detector=FaceDetect(cpu=True,model_path=model_path)
        landmark_detector=pfpld(cpu=True,model_path=model_path)
    positions=Path(output_dir)/"positions";positions.mkdir(parents=True,exist_ok=True)
    print("计算人脸宽高比...")
    wh_list=[]
    for index in range(int(total_frames)):
        try:
            frame=cv2.imread(str(Path(frames_dir)/f"{index:06d}.jpg"))
            landmarks=_face_landmarks(frame,detector,landmark_detector,include_right=False)
            if landmarks is not None:
                _,_,width,height=cv2.boundingRect(landmarks.astype(np.int32))
                wh_list.append(width/height)
        except Exception as error:print(f"处理面部失败 (帧 {index}): {error}")
    wh_ratio=np.mean(wh_list) if wh_list else 1.0
    print(f"人脸宽高比: {wh_ratio}")
    print("开始逐帧处理并即时保存数据...")
    for index in range(int(total_frames)):
        print(f"处理帧: {index}")
        frame_data={};is_no_face=True
        try:
            frame=cv2.imread(str(Path(frames_dir)/f"{index:06d}.jpg"))
            landmarks=_face_landmarks(frame,detector,landmark_detector)
            if landmarks is not None:
                frame_data={"bounding_box":_position_box(landmarks,frame.shape,wh_ratio),"landmarks":landmarks}
                is_no_face=False
        except Exception as error:print(f"处理面部失败 (帧 {index}): {error}")
        save_frame_data(index,positions,video_info,frame_data,is_no_face)
        if (index+1)%100==0:print(f"已处理 {index+1} 帧")
    print("人脸处理与数据保存完成.")
