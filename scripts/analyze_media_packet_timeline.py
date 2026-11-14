"""Analyze bounded audio/video packet timing without decoding user content."""

import argparse
import json
from pathlib import Path
import subprocess


def packets(ffprobe, media, selector):
    result = subprocess.run([
        str(ffprobe), '-v', 'error', '-select_streams', selector,
        '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', str(media),
    ], check=True, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)['packets']


def summarize(rows, *, settled_after=2.0):
    parsed = [(float(row['pts_time']), float(row.get('duration_time') or 0)) for row in rows]
    deltas = []
    for index, ((previous, duration), (current, _)) in enumerate(zip(parsed, parsed[1:]), 1):
        deltas.append({
            'index': index,
            'previous_pts': previous,
            'current_pts': current,
            'delta_ms': round((current - previous) * 1000, 3),
            'uncovered_ms': round(max(0, current - previous - duration) * 1000, 3),
        })
    largest = max(deltas, key=lambda row: row['delta_ms'])
    settled = [row for row in deltas if row['previous_pts'] >= settled_after]
    return {
        'packets': len(parsed), 'first_pts': parsed[0][0], 'last_pts': parsed[-1][0],
        'largest_delta': largest,
        'largest_settled_delta': max(settled, key=lambda row: row['delta_ms']) if settled else None,
        'non_monotonic': sum(row['delta_ms'] <= 0 for row in deltas),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffprobe', required=True, type=Path)
    parser.add_argument('--media', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    ffprobe = args.ffprobe.resolve(strict=True)
    media = args.media.resolve(strict=True)
    report = {
        'passed': True,
        'media': str(media),
        'audio': summarize(packets(ffprobe, media, 'a:0')),
        'video': summarize(packets(ffprobe, media, 'v:0')),
        'settled_after_seconds': 2.0,
    }
    if report['audio']['non_monotonic'] or report['video']['non_monotonic']:
        raise RuntimeError('packet timeline is not strictly increasing')
    destination = args.report.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
