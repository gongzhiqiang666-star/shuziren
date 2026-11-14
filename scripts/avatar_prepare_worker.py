"""Prepare a new avatar in an owned job directory using restored preprocessing."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import subprocess
import sys
import traceback

from scripts.avatar_store import AvatarError, digest
from scripts.v122_acceleration import configure_runtime


def prepare(runtime_root, source, output, resolution):
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists():
        raise AvatarError('制作输出目录必须是新的任务目录')
    output.mkdir(parents=True)
    internal = configure_runtime(runtime_root)
    from recovered.image_clone_api import preprocess_video
    from recovered.output_resolution import normalize_target_height
    tools = internal/'env/ffmpeg/bin'
    data = json.loads(subprocess.check_output([str(tools/'ffprobe.exe'), '-v', 'error',
        '-show_streams', '-show_format', '-of', 'json', str(source)], timeout=30))
    video = next((item for item in data['streams'] if item['codec_type']=='video'), None)
    if video is None:
        raise AvatarError('文件没有视频轨道')
    duration = float(data['format'].get('duration', 0))
    if not 1 <= duration <= 240:
        raise AvatarError('当前视频制作支持1至240秒，不会静默截断')
    width, height = int(video['width']), int(video['height'])
    rotation = int((video.get('tags') or {}).get('rotate', 0))
    for item in video.get('side_data_list') or []:
        if 'rotation' in item:
            rotation = int(item['rotation'])
    if abs(rotation) % 180 == 90:
        width, height = height, width
    target_height = normalize_target_height(resolution, width > height)
    target_width = max(2, int(width*target_height/height)//2*2)
    progress = output.parent/'progress.json'
    def stage(value):
        temporary = progress.with_suffix('.tmp')
        temporary.write_text(json.dumps({'phase': value}), encoding='utf-8')
        temporary.replace(progress)
    stage('normalizing')
    normalized = output/'normalized_video.mp4'
    subprocess.run([str(tools/'ffmpeg.exe'), '-nostdin', '-y', '-v', 'error', '-i', str(source),
        '-map', '0:v:0', '-map', '0:a:0?', '-vf', f'scale={target_width}:{target_height},fps=25',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k',
        str(normalized)], check=True, capture_output=True, timeout=300)
    stage('detecting_faces')
    info = preprocess_video(normalized, output, face_model_path=internal/'assets/pretrained_models/face_detect')
    if not 1 <= info['total_frames'] <= 6000:
        raise AvatarError('视频制作帧数超出当前支持范围')
    validate_face_coverage(info)
    import yaml
    (output/'model_info.yaml').write_text(yaml.safe_dump({
        'resolution': resolution, 'fps': info['fps'], 'width': info['width'],
        'height': info['height'], 'total_frames': info['total_frames'],
    }), encoding='utf-8')
    stage('validating')
    return {'prepared_directory': str(output), 'frames': info['total_frames'],
            'width': info['width'], 'height': info['height'], 'source_sha256': digest(source)}


def validate_face_coverage(info):
    """Reject ambiguous or mostly unusable recordings before library import."""
    total = int(info.get('total_frames') or 0)
    face_frames = int(info.get('face_frames') or 0)
    no_face = sorted(set(int(value) for value in info.get('no_face_frames') or []))
    multi = int(info.get('multi_face_frames') or 0)
    if total <= 0 or face_frames + len(no_face) != total:
        raise AvatarError('人脸检测结果不完整，请重新制作')
    if multi:
        raise AvatarError(f'视频有{multi}帧检测到多张人脸，请只保留一个人物')
    if face_frames / total < .8:
        raise AvatarError('可驱动人脸帧不足80%，请减少遮挡、侧脸或离开画面')
    longest = current = previous = None
    for index in no_face:
        current = current + 1 if previous is not None and index == previous + 1 else 1
        longest = max(longest or 0, current)
        previous = index
    if (longest or 0) > 12:
        raise AvatarError('连续超过0.48秒未检测到人脸，请保持正脸清晰可见')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--resolution', choices=['480p', '720p', '1080p', '2k', '4k'], default='720p')
    args = parser.parse_args()
    try:
        with redirect_stdout(sys.stderr):
            result = prepare(args.runtime_root.resolve(), args.source.resolve(), args.output.resolve(), args.resolution)
        response = {'ok': True, 'result': result}
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        message = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            message = '视频无法解码或规范化失败，请检查文件格式与内容'
        elif isinstance(error, subprocess.TimeoutExpired):
            message = '视频处理超时，请检查视频或选择较低清晰度后重试'
        response = {'ok': False, 'error_type': type(error).__name__, 'error': message}
    print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0 if response['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
