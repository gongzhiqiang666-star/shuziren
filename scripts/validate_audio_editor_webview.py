"""Exercise the recovered audio editor through a real Windows pywebview window."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import wave


def write_wav(path: Path, *, frames: int = 8000, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(b"\0\0" * frames)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix="audio-editor-webview-", ignore_cleanup_errors=True) as raw:
        root = Path(raw)
        runtime = root / "runtime"
        clips = root / "clips"
        clips.mkdir(parents=True)
        write_wav(clips / "片段01.wav")
        (clips / "片段01.txt").write_text("这是一杯青瓷茶杯", encoding="utf-8")
        config = runtime / "tools/edit_audio/config/config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            "device: cpu\nitems_per_page: 50\nlast_folder: "
            + json.dumps(str(clips), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.environ["YUNCHUANG_RUNTIME_DIR"] = str(runtime)

        import webview
        from recovered.edit_audio import AudioEditorAPI, EDIT_AUDIO_HTML

        api = AudioEditorAPI()
        window = webview.create_window(
            "MED-002 音频编辑器交互验证",
            html=EDIT_AUDIO_HTML,
            js_api=api,
            width=1200,
            height=760,
        )
        result: dict[str, object] = {"passed": False}

        def inspect() -> None:
            try:
                deadline = time.monotonic() + 15
                rendered = False
                while time.monotonic() < deadline:
                    rendered = bool(window.evaluate_js(
                        "document.querySelectorAll('.audio-item').length === 1 && "
                        "document.body.innerText.includes('片段01.wav')"
                    ))
                    if rendered:
                        break
                    time.sleep(0.1)
                if not rendered:
                    raise RuntimeError("the WAV/TXT item was not rendered in the WebView")

                # Drive the same DOM handler a user reaches through the keyword-replace button.
                window.evaluate_js(
                    "document.getElementById('oldKeyword').value='茶杯';"
                    "document.getElementById('newKeyword').value='水杯';"
                    "runKeywordReplace();"
                )
                deadline = time.monotonic() + 15
                status = ""
                while time.monotonic() < deadline:
                    status = str(window.evaluate_js(
                        "document.getElementById('statusBar').textContent"
                    ) or "")
                    if "替换完成" in status:
                        break
                    time.sleep(0.1)
                if "替换完成" not in status:
                    raise RuntimeError(f"keyword replacement did not finish: {status}")

                text = (clips / "片段01.txt").read_text(encoding="utf-8")
                preview = api.get_audio_base64("片段01")
                if text != "这是一杯青瓷水杯":
                    raise RuntimeError(f"replacement was not persisted: {text}")
                if not preview.get("success") or not str(preview.get("audio_data", "")).startswith(
                    "data:audio/wav;base64,"
                ):
                    raise RuntimeError("WAV preview was not returned")
                result.update({
                    "passed": True,
                    "window_title": window.title,
                    "item_rendered": True,
                    "dom_action": "runKeywordReplace",
                    "status": status,
                    "persisted_text": text,
                    "preview_data_url": True,
                    "window_closed_after_validation": True,
                })
            except Exception as error:
                result.update({"error": f"{type(error).__name__}: {error}"})
            finally:
                api.shutdown()
                window.destroy()

        def loaded() -> None:
            threading.Thread(target=inspect, daemon=True).start()

        window.events.loaded += loaded
        webview.start(debug=False, private_mode=True)

    (report_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
