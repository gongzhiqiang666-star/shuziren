#!/usr/bin/env python3
"""Launch the reconstructed WebView against a local preview for Windows QA."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovered.main_webview import run_webview


class SmokeApi:
    def __init__(self, marker: Path):
        self.marker = marker
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.marker.with_suffix(self.marker.suffix + ".tmp")
        temporary.write_text(json.dumps({
            "shutdown_calls": self.shutdown_calls,
            "pid": os.getpid(),
        }), encoding="utf-8")
        os.replace(temporary, self.marker)
        return {"status": "success"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--marker", required=True, type=Path)
    options = parser.parse_args()
    config = {
        "environment": "development",
        "environments": {"development": {"webview_url": options.url}},
    }
    run_webview(SmokeApi(options.marker), config, ROOT, debug=False)


if __name__ == "__main__":
    main()
