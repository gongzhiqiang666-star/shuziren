from recovered.image_clone_video_synthesizer import *


def main():
    import argparse
    parser=argparse.ArgumentParser(description="离线数字人视频合成")
    parser.add_argument("data_dir");parser.add_argument("model_path")
    parser.add_argument("wenet_conf_path");parser.add_argument("wenet_model_path")
    parser.add_argument("audio_path");parser.add_argument("output_path")
    parser.add_argument("--device",default="cuda:0");parser.add_argument("--batch-size",type=int,default=8)
    parser.add_argument("--silence-feature-path")
    args=parser.parse_args()
    synthesizer=VideoSynthesizer(args.data_dir,args.model_path,args.wenet_conf_path,args.wenet_model_path,
                                 args.device,args.batch_size,args.silence_feature_path)
    return synthesizer.process_single_file(args.audio_path,args.output_path)


if __name__ == "__main__":
    main()
