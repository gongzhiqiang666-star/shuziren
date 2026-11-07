from recovered.image_clone_video_synthesizer import VideoSynthesizer as _VideoSynthesizer
import cv2
import numpy as np


class VideoSynthesizer(_VideoSynthesizer):
    """Frame-saving binary variant, whose constructor predates silence features."""
    def __init__(self,data_dir,model_path,wenet_conf_path,wenet_model_path,device="cuda:0",batch_size=8):
        super().__init__(data_dir,model_path,wenet_conf_path,wenet_model_path,device,batch_size,None)

    def _process_batch(self,batch_images,batch_frame_data,audio_features,batch_start=0):
        frames=self.engine.process_batch(batch_images,batch_frame_data,audio_features)
        for offset,item in enumerate(getattr(self.engine,"last_diagnostics",())):
            frame_number=int(batch_start)+offset
            generated=np.asarray(item["generated_face"]).copy()
            face_with_landmarks=generated.copy()
            landmarks=np.asarray(item.get("landmarks") if item.get("landmarks") is not None else ()).reshape(-1,2)
            # The Cython binary uses ``range(2, 16)`` here.  Keep the bounds
            # check so diagnostics remain usable with a shorter custom model.
            for landmark_index in range(2,min(16,len(landmarks))):
                point=tuple(np.rint(landmarks[landmark_index]).astype(int))
                cv2.circle(face_with_landmarks,point,2,(0,255,0),-1)
                cv2.putText(face_with_landmarks,str(landmark_index),
                            (point[0]+3,point[1]+3),cv2.FONT_HERSHEY_SIMPLEX,
                            0.4,(255,0,0),1)
            cv2.imwrite(f"generated_face_with_landmarks_{frame_number}.jpg",face_with_landmarks)
            cv2.imwrite(f"generated_face_cropped_{frame_number}.jpg",
                        np.asarray(item["cropped_for_pasting"]))
        return frames


def main():
    import argparse
    parser=argparse.ArgumentParser(description="离线数字人视频合成并保存中间帧")
    parser.add_argument("data_dir");parser.add_argument("model_path")
    parser.add_argument("wenet_conf_path");parser.add_argument("wenet_model_path")
    parser.add_argument("audio_path");parser.add_argument("output_path")
    parser.add_argument("--frames-dir");parser.add_argument("--device",default="cuda:0")
    parser.add_argument("--batch-size",type=int,default=8)
    args=parser.parse_args()
    synthesizer=VideoSynthesizer(args.data_dir,args.model_path,args.wenet_conf_path,args.wenet_model_path,
                                 args.device,args.batch_size)
    return synthesizer.process_single_file(args.audio_path,args.output_path,args.frames_dir)


if __name__ == "__main__":
    main()
