"""Non-acceptance diagnostic using immutable inputs from a completed quality run."""
import argparse
import json
import os
from pathlib import Path
import uuid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-directory',type=Path,required=True)
    parser.add_argument('--encoder',choices=['legacy','libx264','h264_nvenc'],default='legacy')
    args=parser.parse_args();root=args.run_directory.resolve()
    os.environ['NVIDIA_TF32_OVERRIDE']='0'
    from scripts.v122_acceleration import configure_runtime,accelerated_unet
    from scripts.avatar_store import AvatarStore,digest
    from scripts.avatar_render import verify_media
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    internal=configure_runtime(config['runtime_root'])
    from recovered.image_clone_video_synthesizer import VideoSynthesizer
    models=internal/'assets/pretrained_models'
    output=root.parent/('profile-'+uuid.uuid4().hex);output.mkdir()
    candidates=[json.loads(path.read_text(encoding='utf-8')) for path in (root/'tensorrt').glob('Q*.json')]
    candidates.sort(key=lambda item:item['process_seconds']/item['frames'],reverse=True)
    selected=[candidates[0]['item'],'Q023',candidates[1]['item']]
    results=[]
    with accelerated_unet(config['engine_cache'],backend='tensorrt',strict_fp32=True):
        with VideoSynthesizer(AvatarStore(root).directory(config['avatar_id']),models/'image_infer_v2/unet_v2.onnx',
            models/'wenet/conf/train_conformer_multi_cn.yaml',models/'wenet/exp/conformer/wenetmodel.pt',batch_size=4) as synth:
            if args.encoder!='legacy':
                from scripts.raw_video_writer import RawVideoWriter
                synth.frame_writer_factory=lambda target,audio,width,height:RawVideoWriter(internal/'env/ffmpeg/bin/ffmpeg.exe',target,audio,width,height,args.encoder)
            for index,item in enumerate([selected[0]]+selected):
                source=json.loads((root/'tts'/(item+'.json')).read_text(encoding='utf-8'))['result']
                audio=Path(source['output'])
                if digest(audio)!=source['sha256']:raise ValueError('Audio changed')
                synth.current_frame_position=0;synth.is_forward=True
                target=output/f'{index}-{item}.mp4'
                synth.process_single_file(audio,target)
                media=verify_media(audio,target,internal/'env/ffmpeg/bin/ffmpeg.exe')
                result={'id':item,'encoder':args.encoder,'cold':index==0,'timings':synth.last_process_timings,**media}
                results.append(result)
                (output/'result.json').write_text(json.dumps({'acceptance_run':False,'source_run':str(root),'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(result),flush=True)
    print(str(output),flush=True)


if __name__=='__main__':main()
