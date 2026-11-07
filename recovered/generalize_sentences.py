"""Recovered live-script sentence variation generator."""

from __future__ import annotations

import re
import threading
import time
from collections import deque

from .llm_base_chat import base_chat


LIVE_SCRIPT_OPTIMIZATION_PROMPT = "你是直播话术优化助手。保留原意和事实，改写成自然、简短、口语化的直播表达，只输出改写结果。"


class RateLimiter:
    def __init__(self, max_requests_per_minute=30):
        self.max_requests = max(1, int(max_requests_per_minute))
        self.window_size = 60.0
        self.requests = deque()
        self.lock = threading.Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.monotonic()
            while self.requests and now - self.requests[0] >= self.window_size:
                self.requests.popleft()
            if len(self.requests) >= self.max_requests:
                wait_time = max(0.0, self.window_size - (now - self.requests[0]))
                if wait_time:
                    time.sleep(wait_time)
                now = time.monotonic()
                while self.requests and now - self.requests[0] >= self.window_size:
                    self.requests.popleft()
            self.requests.append(now)


def optimize_script(sentence: str) -> str:
    return base_chat(sentence, LIVE_SCRIPT_OPTIMIZATION_PROMPT, model_type="script", raise_on_failure=True)


def slice_content(text: str):
    # Existing square-bracket alternatives are a single script unit even when
    # individual choices contain sentence punctuation.
    segments = re.split(r"(\[[^\[\]]*\])", str(text or ""))
    output = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        if segment.startswith("[") and segment.endswith("]"):
            output.append(segment)
            continue
        output.extend(item.strip() for item in
                      re.findall(r".*?[。！？!?；;\n]+|.+$", segment, re.S)
                      if item.strip())
    return output


def generalize_sentences(script: str, variations: int = 3) -> str:
    if variations < 1: raise ValueError("variations 必须大于零")
    sentences = slice_content(script); generalized = []
    limiter = RateLimiter()
    for sentence in sentences:
        existing = re.fullmatch(r"\[(.*?)\]", sentence, re.S)
        all_variants = ([item.strip() for item in existing.group(1).split("|") if item.strip()]
                        if existing else [sentence])
        original = all_variants[0]
        new_variants = []
        for _ in range(variations):
            limiter.wait_if_needed()
            variant = str(optimize_script(original) or "").strip()
            match = re.search(r"\[(.*?)\]", variant, re.S)
            if match:
                variant = match.group(1).split("|")[0].strip()
            if variant and variant not in all_variants and variant not in new_variants:
                new_variants.append(variant)
        generalized.append("[" + "|".join(all_variants + new_variants) + "]")
    return "\n".join(generalized)
