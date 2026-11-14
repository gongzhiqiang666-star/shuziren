"""Real RTX validation for retained-live-audio to digital-human video."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from scripts.avatar_store import AvatarStore
from scripts.product_store import ProductStore
from scripts.render_tasks import RenderTasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True)
    parser.add_argument('--avatar-directory', required=True)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--output-root', required=True)
    args = parser.parse_args()
    root = Path(args.output_root).resolve()
    if root.exists():
        raise SystemExit('output root already exists')
    root.mkdir(parents=True)
    products = ProductStore(root)
    product = products.save(title='直播内容成片验证', content='真实留存音频驱动数字人', product_index=1)
    products.select(product['id'])
    script_id = products.add_script(product, '这是直播中已经说出的内容，现在直接生成数字人短视频。')
    products.record_live_session('validation-scene', time.time(), status='stopped')
    audio = Path(args.audio).resolve(strict=True)
    audio_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
    products.archive_live_content_audio('validation-scene', 'validation-speech', audio, audio_hash)
    products.record_rotation_completion('validation-scene', 'validation-speech', {
        'product_id': product['id'], 'product_version': product['version'], 'script_id': script_id,
    }, 0)
    avatars = AvatarStore(root)
    avatar = avatars.import_prepared(args.avatar_directory, '真实数字人验证形象')
    avatars.select(avatar['id'])

    class AudioContext:
        def __init__(self): self.products = products

    tasks = RenderTasks(args.runtime_root, root, AudioContext())
    task = tasks.start_content('validation-scene', 'validation-speech', avatar['id'], 'standard')
    deadline = time.time() + 600
    while task['status'] == 'running' and time.time() < deadline:
        time.sleep(1)
        task = tasks.state()
    if task['status'] != 'succeeded':
        raise SystemExit(json.dumps(task, ensure_ascii=False))
    video = tasks.video_path(task['id'])
    subtitle = tasks.subtitle(task['id'])
    (root / 'avatar-subtitles.srt').write_text(subtitle, encoding='utf-8')
    shutil.copy2(video, root / 'live-content-avatar.mp4')
    shutil.copy2(tasks.cover_path(task['id']), root / 'live-content-cover.jpg')
    report = {'ok': True, 'task': task, 'video': str(root / 'live-content-avatar.mp4'),
              'subtitle': str(root / 'avatar-subtitles.srt'), 'cover': str(root / 'live-content-cover.jpg')}
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
