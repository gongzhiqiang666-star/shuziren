#!/usr/bin/env python3
"""Validate FUNCTION_MATRIX.md IDs, statuses, and summary totals."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "FUNCTION_MATRIX.md"
ROW_RE = re.compile(r"^\| ((?:SYS|CNT|MED|LIV)-\d{3}) \|(?:[^|]*\|){3} ([^|]+) \|")
SUMMARY_RE = re.compile(r"^\| (静态验证通过|开发中|已分析|Windows 验证通过|端到端验证通过) \| (\d+) \|$")
ALLOWED_STATUSES = {
    "未分析",
    "已分析",
    "开发中",
    "静态验证通过",
    "Windows 验证通过",
    "端到端验证通过",
}


def main() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    rows: list[tuple[str, str]] = []
    summary: dict[str, int] = {}

    for line in text.splitlines():
        row = ROW_RE.match(line)
        if row:
            rows.append((row.group(1), row.group(2).strip()))
            continue
        total = SUMMARY_RE.match(line)
        if total:
            summary[total.group(1)] = int(total.group(2))

    if not rows:
        raise SystemExit("功能矩阵中没有找到功能条目")

    ids = [item_id for item_id, _ in rows]
    duplicates = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise SystemExit(f"功能 ID 重复: {', '.join(duplicates)}")

    invalid = sorted({status for _, status in rows} - ALLOWED_STATUSES)
    if invalid:
        raise SystemExit(f"存在非法状态: {', '.join(invalid)}")

    actual = Counter(status for _, status in rows)
    errors = []
    for status in ALLOWED_STATUSES:
        expected_count = summary.get(status, 0)
        actual_count = actual.get(status, 0)
        if expected_count != actual_count:
            errors.append(f"{status}: 统计={expected_count}, 实际={actual_count}")
    if errors:
        raise SystemExit("功能矩阵统计不一致: " + "; ".join(sorted(errors)))

    declared_total = re.search(r"^\| 合计 \| (\d+) \|$", text, re.MULTILINE)
    if not declared_total or int(declared_total.group(1)) != len(rows):
        value = declared_total.group(1) if declared_total else "缺失"
        raise SystemExit(f"合计不一致: 统计={value}, 实际={len(rows)}")

    print(f"PASS: {len(rows)} 项功能，ID/状态/统计一致")
    for status, count in sorted(actual.items()):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
