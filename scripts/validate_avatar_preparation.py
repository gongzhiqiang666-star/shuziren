"""Real video/GPU preparation, cancellation, recovery and invalid media checks."""
import argparse
import json
from pathlib import Path
import time
import uuid

from scripts.avatar_tasks import AvatarTasks
from scripts.avatar_store import AvatarStore, digest
from scripts.product_store import Conflict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--report-directory', required=True, type=Path)
    args = parser.parse_args()
    root = (args.report_directory/('run-'+uuid.uuid4().hex)).resolve()
    root.mkdir(parents=True)
    manager = AvatarTasks(args.runtime_root, root)
    report = {'status':'failed', 'checks':{}, 'visual_quality_verified':False}
    def wait_finished(timeout=600):
        end = time.monotonic()+timeout
        while time.monotonic()<end:
            state = manager.state()
            if state['status']!='running':
                manager.monitor.join(timeout=20)
                return state
            time.sleep(.25)
        raise TimeoutError('制作未在限定时间内结束')
    try:
        import psutil
        source = args.source.resolve(strict=True)
        before = digest(source)
        task = manager.start(str(source), '取消验证')
        try:
            manager.start(str(source), '重复请求')
            raise AssertionError('重复制作未被拒绝')
        except Conflict:
            report['checks']['duplicate_rejected'] = True
        deadline = time.monotonic()+60
        children = []
        while time.monotonic()<deadline and manager.state()['status']=='running':
            children = psutil.Process(manager.process.pid).children(recursive=True)
            children = [child for child in children if child.name().lower()=='ffmpeg.exe']
            if children:
                break
            time.sleep(.05)
        assert children, '未观察到真实媒体子进程，不能宣称树回收通过'
        process = manager.process
        cancelled = manager.cancel(task['id'])
        assert cancelled['status']=='cancelled' and 'result' not in cancelled
        assert process.poll() is not None and not manager.monitor.is_alive()
        assert all(not child.is_running() for child in children)
        assert not (root/'avatar-jobs'/task['id']/'prepared').exists()
        report['checks']['real_media_child_tree_cancelled'] = True
        report['cancelled_child_names'] = ['ffmpeg.exe' for child in children]
        task = manager.start(str(source), '本机新视频制作')
        started = time.monotonic()
        success = wait_finished()
        assert success['status']=='succeeded', success
        store = AvatarStore(root)
        avatar = success['result']['avatar']
        assert avatar['name']=='本机新视频制作', avatar
        store.select(avatar['id'])
        directory = store.directory(avatar['id'])
        assert (directory/'normalized_video.mp4').is_file()
        assert (directory/'model_info.yaml').is_file()
        assert len(list((directory/'positions').glob('*.txt')))==avatar['frames']
        assert digest(source)==before
        report.update(avatar=avatar, preparation_seconds=time.monotonic()-started)
        report['checks']['new_video_prepared_imported_and_selected'] = True
        broken = root/'invalid.mp4'
        broken.write_bytes(b'not a video')
        manager.start(str(broken), '无效媒体')
        failed = wait_finished(60)
        assert failed['status']=='failed' and 'result' not in failed
        assert AvatarStore(root).selected()==avatar['id'] and len(store.list())==1
        assert not any((root/'avatar-jobs').glob('*/prepared'))
        report['checks']['invalid_media_preserves_existing_avatar'] = True
        manager.close()
        assert manager.process is None
        report.update(status='passed', source_unchanged=True, owned_worker_closed=True)
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
    finally:
        manager.close()
        (root/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status':report['status'], 'report':str(root/'result.json'), 'error':report.get('error')}, ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
