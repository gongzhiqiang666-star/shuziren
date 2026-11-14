#!/usr/bin/env python3
"""Ensure every authoritative function is routed to an A07 acceptance queue."""

from collections import Counter
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'docs' / 'FUNCTION_MATRIX.md'
ROW = re.compile(r'^\| ((?:SYS|CNT|MED|LIV)-\d{3}) \|(?:[^|]*\|){3} ([^|]+) \|', re.M)

QUEUES = {
    'development': {'CNT-014'},
    'external': {
        'SYS-006', 'SYS-008', 'SYS-010', 'SYS-011',
        'CNT-001', 'CNT-002', 'CNT-003', 'CNT-004', 'CNT-007', 'CNT-009',
        'CNT-011', 'CNT-013',
        'MED-009',
        'LIV-005', 'LIV-006', 'LIV-007', 'LIV-008', 'LIV-009', 'LIV-010',
        'LIV-011', 'LIV-012', 'LIV-014', 'LIV-015',
    },
    'local': {
        'SYS-001', 'SYS-002', 'SYS-003', 'SYS-004', 'SYS-005', 'SYS-007',
        'SYS-009', 'SYS-012',
        'CNT-005', 'CNT-006', 'CNT-008', 'CNT-010', 'CNT-012', 'CNT-015', 'CNT-016',
        'MED-001', 'MED-002', 'MED-003', 'MED-004', 'MED-005', 'MED-006',
        'MED-007', 'MED-008', 'MED-010', 'MED-011', 'MED-012',
        'LIV-001', 'LIV-002', 'LIV-003', 'LIV-004', 'LIV-013', 'LIV-016', 'LIV-017', 'LIV-018',
    },
}


def main():
    rows = dict(ROW.findall(MATRIX.read_text(encoding='utf-8')))
    routed = [item for values in QUEUES.values() for item in values]
    duplicates = sorted(item for item, count in Counter(routed).items() if count != 1)
    missing = sorted(set(rows) - set(routed))
    unknown = sorted(set(routed) - set(rows))
    if duplicates or missing or unknown:
        raise SystemExit(f'audit routing invalid: duplicates={duplicates}, missing={missing}, unknown={unknown}')
    statuses = Counter(value.strip() for value in rows.values())
    print(f'PASS: {len(rows)} functions routed exactly once')
    print('statuses: ' + ', '.join(f'{key}={value}' for key, value in sorted(statuses.items())))
    for name, values in QUEUES.items():
        print(f'{name}={len(values)}: ' + ', '.join(sorted(values)))


if __name__ == '__main__':
    main()
