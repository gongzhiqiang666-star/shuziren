"""Run v179 and source-controlled held-product video tools on identical media."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from recovered.hold_product_video import make_pingpong_video, portrait_filter, probe_video, write_drive_video


def frame_count(path, ffprobe):
    completed = subprocess.run([
        str(ffprobe), "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(path),
    ], check=True, capture_output=True, text=True, encoding="utf-8")
    return int(completed.stdout.strip())


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--v179-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    v179 = args.v179_root.resolve()
    runtime = args.runtime_root.resolve()
    vpython = v179 / "_internal/env/python.exe"
    vffmpeg = v179 / "_internal/env/ffmpeg/bin/ffmpeg.exe"
    vffprobe = v179 / "_internal/env/ffmpeg/bin/ffprobe.exe"
    ffmpeg = runtime / "_internal/env/ffmpeg/bin/ffmpeg.exe"
    ffprobe = runtime / "_internal/env/ffmpeg/bin/ffprobe.exe"
    required = (vpython, vffmpeg, vffprobe, ffmpeg, ffprobe)
    if not all(path.is_file() for path in required):
        raise SystemExit("v179/current media runtime is incomplete")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hold-video-") as temporary:
        source = Path(temporary) / "source.mp4"
        subprocess.run([
            str(ffmpeg), "-y", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=10:d=0.8",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.8", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        outputs = {
            "v179_drive": report_dir / "v179-drive.mp4", "current_drive": report_dir / "current-drive.mp4",
            "v179_loop": report_dir / "v179-loop.mp4", "current_loop": report_dir / "current-loop.mp4",
        }
        code = (
            "import sys;sys.path.insert(0," + repr(str(v179 / "_internal")) + ");"
            "from tools.hold_product.video import write_drive_video,make_pingpong_video,portrait_filter;"
            "write_drive_video(" + repr(str(source)) + "," + repr(str(outputs["v179_drive"]))
            + ",ffmpeg=" + repr(str(vffmpeg)) + ",ffprobe=" + repr(str(vffprobe)) + ");"
            "make_pingpong_video(" + repr(str(source)) + "," + repr(str(outputs["v179_loop"]))
            + ",ffmpeg=" + repr(str(vffmpeg)) + ");print(portrait_filter())")
        completed = subprocess.run([str(vpython), "-X", "utf8", "-I", "-c", code],
                                   capture_output=True, text=True, encoding="utf-8", timeout=120)
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "v179 held-product video failed")
        write_drive_video(source, outputs["current_drive"], ffmpeg=ffmpeg, ffprobe=ffprobe)
        make_pingpong_video(source, outputs["current_loop"], ffmpeg=ffmpeg)
    media = {}
    for name, path in outputs.items():
        media[name] = {**probe_video(path, ffprobe=ffprobe), "frames": frame_count(path, ffprobe)}
    def comparable(value):
        return {key: value[key] for key in ("width", "height", "fps", "codec", "has_audio", "frames")}
    output_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    reference_filter = output_lines[-1] if output_lines else ""
    passed = (reference_filter == portrait_filter()
              and comparable(media["v179_drive"]) == comparable(media["current_drive"])
              and comparable(media["v179_loop"]) == comparable(media["current_loop"])
              and abs(media["v179_drive"]["duration"] - media["current_drive"]["duration"]) <= .04
              and abs(media["v179_loop"]["duration"] - media["current_loop"]["duration"]) <= .04)
    report = {"passed": passed, "portrait_filter_equal": reference_filter == portrait_filter(),
              "media": media}
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
