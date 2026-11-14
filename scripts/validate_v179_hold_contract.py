"""Compare the source-controlled held-product request with an authorized v179 package."""

import argparse
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from recovered import runninghub_hold, runninghub_ltx


V179_PROBE = r'''
import importlib, json, sys
sys.path.insert(0, ROOT)
module = importlib.import_module("tools.hold_product.qwen_hold")
ltx = importlib.import_module("tools.cloud_dh.runninghub_ltx")
calls = []
class Response:
    def raise_for_status(self): pass
    def json(self): return {"code": 0, "data": {"taskId": "task-1"}}
def post(*args, **kwargs):
    calls.append({"url": args[0], "kwargs": kwargs})
    return Response()
module.requests.post = post
ltx.requests.post = post
hold_task = module._create_task("redacted-key", "avatar.png", "product.png", "prompt")
ltx_task = ltx.create_ltx_task(api_key="redacted-key", image_remote="held.png",
    audio_remote="audio.wav", prompt="prompt", duration_s=6.5)
print(json.dumps({"hold": {"task": hold_task, "call": calls[0]},
                  "ltx": {"task": ltx_task, "call": calls[1]}}, ensure_ascii=False))
'''


class Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"code": 0, "data": {"taskId": "task-1"}}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--v179-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.v179_root.resolve()
    python = root / "_internal/env/python.exe"
    module = root / "_internal/tools/hold_product/qwen_hold.cp310-win_amd64.pyd"
    ltx_module = root / "_internal/tools/cloud_dh/runninghub_ltx.cp310-win_amd64.pyd"
    if not python.is_file() or not module.is_file() or not ltx_module.is_file():
        raise SystemExit("v179 Python or held-product module is missing")
    code = "ROOT=" + repr(str(root / "_internal")) + "\n" + V179_PROBE
    completed = subprocess.run([str(python), "-X", "utf8", "-I", "-c", code],
                               capture_output=True, text=True, encoding="utf-8", timeout=30)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "v179 probe failed")
    reference = json.loads([line for line in completed.stdout.splitlines() if line.strip()][-1])
    calls = []
    with patch.object(runninghub_hold.requests, "post",
                      side_effect=lambda *a, **kw: calls.append({"url": a[0], "kwargs": kw}) or Response()):
        hold_task = runninghub_hold.submit_hold_task(
            api_key="redacted-key", avatar_remote="avatar.png",
            product_remote="product.png", prompt="prompt")
        ltx_task = runninghub_ltx.create_ltx_task(
            api_key="redacted-key", image_remote="held.png", audio_remote="audio.wav",
            prompt="prompt", duration_s=6.5)
    current = json.loads(json.dumps({
        "hold": {"task": hold_task, "call": calls[0]},
        "ltx": {"task": ltx_task, "call": calls[1]},
    }, ensure_ascii=False))
    matched = reference == current
    report = {
        "passed": matched, "v179_module": str(module),
        "v179_module_sha256": __import__("hashlib").sha256(module.read_bytes()).hexdigest(),
        "v179_ltx_module": str(ltx_module),
        "v179_ltx_module_sha256": __import__("hashlib").sha256(ltx_module.read_bytes()).hexdigest(),
        "reference": reference, "current": current,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": matched, "report": str(args.report.resolve())}, ensure_ascii=False))
    if not matched:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
