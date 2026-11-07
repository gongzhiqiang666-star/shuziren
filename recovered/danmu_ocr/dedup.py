"""Normalize OCR text for duplicate detection."""

import re


def normalize_dedup_key(text, vietnam_pack=False):
    chinese = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    if chinese:
        return chinese

    pattern = r"[^a-zA-Z0-9À-ỹà-ỹ]" if vietnam_pack else r"[^a-zA-Z0-9]"
    return re.sub(pattern, "", text).lower()


def indel_ratio(left, right):
    """Compute the normalized insertion/deletion similarity."""
    if left == right:
        return 1.0
    if len(left) < len(right):
        left, right = right, left
    lengths = [0] * (len(right) + 1)
    for char in left:
        diagonal = 0
        for index, other in enumerate(right, 1):
            previous = lengths[index]
            if char == other:
                lengths[index] = diagonal + 1
            else:
                lengths[index] = max(previous, lengths[index - 1])
            diagonal = previous
    return 2 * lengths[-1] / (len(left) + len(right))
