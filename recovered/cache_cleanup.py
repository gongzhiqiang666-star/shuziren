"""Bounded cleanup for application-owned caches under the OS temporary directory."""
from pathlib import Path
import tempfile
import threading


CACHE_DIRECTORIES = (
    'short_video', 'converted_audio_for_player', 'voice_infer', 'ip_agent',
    'yunchuang_voice', 'yunchuang-cosyvoice', 'yunchuang-minimax', 'yunchuang_image_clone',
)
_LOCK = threading.Lock()


def _remove(path, result):
    try:
        if path.is_symlink() or path.is_file():
            size = path.lstat().st_size
            path.unlink()
            result['removed'] += 1
            result['removed_bytes'] += size
            return
        if not path.is_dir():
            return
        for child in path.iterdir():
            _remove(child, result)
        path.rmdir()
    except OSError as error:
        result['failures'].append({'path': str(path), 'error': str(error)})


def clear_known_caches(temporary_root=None):
    root = Path(temporary_root or tempfile.gettempdir()).resolve()
    result = {'status': 'success', 'removed': 0, 'removed_bytes': 0, 'failures': []}
    with _LOCK:
        for name in CACHE_DIRECTORIES:
            target = root / name
            if target.parent != root:
                raise ValueError('缓存目录配置无效')
            if target.exists() or target.is_symlink():
                _remove(target, result)
    if result['failures']:
        result['status'] = 'partial'
        result['message'] = '部分缓存无法清理，请关闭占用文件后重试'
    else:
        result['message'] = '缓存清理完成'
    return result
