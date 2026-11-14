"""Real RTX validation for retained-live-audio to digital-human video."""
import argparse
import hashlib
import json
import shutil
import time
import zipfile
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
    products.save_live_content_draft('validation-scene', 'validation-speech',
                                       '标题：直播内容成片验证\n封面文字：直播内容成片验证')
    products.save_live_content_schedule('validation-scene', 'validation-speech', '本机验证账号',
                                        '人工审核后公开', '2027-01-01T09:00:00+08:00')
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
    package = tasks.publication_package('validation-scene', 'validation-speech', task['id'])
    package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    if hashlib.sha256(tasks.publication_package(
            'validation-scene', 'validation-speech', task['id']).read_bytes()).hexdigest() != package_hash:
        raise SystemExit('publication package retry is not deterministic')
    shutil.copy2(package, root / 'publication-package.zip')
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        if names != {'video.mp4', 'cover.jpg', 'captions.srt', 'metadata.json', 'SHA256SUMS.txt'}:
            raise SystemExit('publication package inventory mismatch')
        checksums = {name: digest_value for digest_value, name in
                     (line.split('  ', 1) for line in archive.read('SHA256SUMS.txt').decode().splitlines())}
        for name, expected in checksums.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise SystemExit('publication package checksum mismatch: ' + name)
    products.record_live_content_receipt('validation-scene', 'validation-speech', 'validation-work-1')
    publication, = products.live_session_report('validation-scene')['content_publications']
    if (publication.get('package_sha256') != package_hash
            or publication.get('render_task_id') != task['id']):
        raise SystemExit('publication receipt is not bound to exported package')
    report = {'ok': True, 'task': task, 'video': str(root / 'live-content-avatar.mp4'),
              'subtitle': str(root / 'avatar-subtitles.srt'), 'cover': str(root / 'live-content-cover.jpg'),
              'package': str(root / 'publication-package.zip')}
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
