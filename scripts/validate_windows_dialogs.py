"""Interactive Windows validation harness for SYS-008 native dialogs."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import threading
import time


def close_owned_dialog(timeout):
    """Close only a native dialog owned by this validator process."""
    user32 = ctypes.windll.user32
    pid = os.getpid()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        handles = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def collect(hwnd, _):
            owner = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            class_name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if owner.value == pid and class_name.value == '#32770' and user32.IsWindowVisible(hwnd):
                handles.append(hwnd)
            return True

        user32.EnumWindows(collect, 0)
        if len(handles) == 1:
            user32.PostMessageW(handles[0], 0x0010, 0, 0)  # WM_CLOSE
            return {'dialog_handle': int(handles[0]), 'owner_pid': pid}
        if len(handles) > 1:
            raise RuntimeError('more than one owned native dialog is visible')
        time.sleep(.05)
    raise TimeoutError('owned native dialog did not appear')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('file', 'folder'), required=True)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--directory', type=Path, default=Path.cwd())
    parser.add_argument('--auto-cancel', action='store_true')
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args()

    import webview

    result_path = args.result.resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    initial = args.directory.resolve()
    window = webview.create_window('SYS-008 对话框验证', html='<h1>正在等待 Windows 选择结果</h1>')

    def run_dialog():
        closer = None
        close_result = []
        close_error = []
        if args.auto_cancel:
            def cancel_dialog():
                try:
                    close_result.append(close_owned_dialog(args.timeout))
                except BaseException as error:
                    close_error.append(str(error))
            closer = threading.Thread(target=cancel_dialog, daemon=True)
            closer.start()
        try:
            kind = webview.OPEN_DIALOG if args.mode == 'file' else webview.FOLDER_DIALOG
            selected = window.create_file_dialog(kind, directory=str(initial), allow_multiple=False)
            if closer:
                closer.join(args.timeout + 1)
            if close_error:
                raise RuntimeError(close_error[0])
            payload = {
                'mode': args.mode,
                'status': 'success' if selected else 'cancelled',
                'files': list(selected or ()),
                'auto_cancel': args.auto_cancel,
                'native_dialog': close_result[0] if close_result else None,
            }
        except Exception as error:
            payload = {'mode': args.mode, 'status': 'failed', 'error': str(error), 'files': []}
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        window.destroy()

    def ready():
        threading.Thread(target=run_dialog, daemon=True).start()

    webview.start(ready, debug=False)


if __name__ == '__main__':
    main()
