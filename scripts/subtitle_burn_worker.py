"""Burn an SRT into a rendered video and verify the publishable result."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import traceback

from recovered.add_subtitles_to_video import add_subtitles_to_video, _get_video_resolution
from scripts.avatar_render import verify_media
from scripts.avatar_store import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--subtitle', required=True, type=Path)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        ffmpeg_dir = args.runtime_root.resolve() / '_internal/env/ffmpeg/bin'
        # The recovered resolver asks for extensionless tool names; PATH lets
        # Windows resolve both ffmpeg.exe and ffprobe.exe from the same bundle.
        os.environ.pop('FFMPEG_HOME', None)
        os.environ['PATH'] = str(ffmpeg_dir) + os.pathsep + os.environ.get('PATH', '')
        # The generic preset scales from video height and becomes oversized on
        # portrait video. Use portrait-safe bounds so a Chinese caption cannot
        # be clipped outside the publishable frame.
        width, height = _get_video_resolution(args.video)
        font_size = max(28, round(min(width * .061, height * .04)))
        max_chars = max(8, int(width / (font_size * 1.12)))
        output = Path(add_subtitles_to_video(
            args.video, args.subtitle, output_path=args.output,
            font_size=font_size, max_chars_per_line=max_chars, margin_v=round(height * .075),
            animation='fade',
        )).resolve()
        media = verify_media(args.audio, output, ffmpeg_dir / 'ffmpeg.exe')
        cover = output.with_name('cover.jpg')
        moment = min(1.0, max(0.0, media['video_duration'] / 2))
        subprocess.run([str(ffmpeg_dir / 'ffmpeg.exe'), '-nostdin', '-v', 'error', '-y', '-ss', str(moment),
                        '-i', str(output), '-frames:v', '1', '-update', '1', str(cover)],
                       capture_output=True, check=True, timeout=60)
        if not cover.is_file() or cover.stat().st_size < 1000 or cover.read_bytes()[:2] != b'\xff\xd8':
            raise RuntimeError('封面抽帧校验失败')
        response = {'ok': True, 'result': {'output': str(output), 'output_sha256': digest(output),
                    'cover': str(cover.resolve()), 'cover_sha256': digest(cover), **media}}
    except Exception as error:
        traceback.print_exc()
        response = {'ok': False, 'error': str(error), 'error_type': type(error).__name__}
    print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0 if response['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
