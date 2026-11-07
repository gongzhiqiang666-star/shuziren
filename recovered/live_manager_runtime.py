"""Recovered public runtime contract of ``live.live_manager``.

The lower-level playback/danmu implementation lives in ``digital_live_manager``;
this module restores the original class names and task-oriented local session API.
"""
from __future__ import annotations

import itertools
import os
import random
import re
import tempfile
import threading
import time
import traceback
import wave
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from .digital_live_manager import DigitalLiveManager
from .slice_content import slice_content


_INTERRUPTION_SAMPLE_RATE = 16000

# Recovered from the Cython module initialiser (FUN_1800f6230).  Both TTS
# limits point at the cached Python integer 4; the broadcast high-water mark
# points at the cached integer 1000.
BROADCAST_QUEUE_TARGET = 1000
PRODUCT_SWITCH_QUEUE_THRESHOLD = 0
TTS_BACKLOG_LOW_WATERMARK = 250
TTS_EMIT_BURST_MAX = 4
TTS_PIPELINE_DEPTH = 4
TTS_CLOUD_TIMEOUT_SECONDS = 90.0
TTS_LOCAL_TIMEOUT_SECONDS = 120.0
INTERACTION_MESSAGE_CAP = 500


@dataclass
class InteractionMessage:
    msg_type: str
    nickname: str
    content: str
    timestamp: float
    processed: bool = False


def _pcm_to_wav_bytes(pcm_bytes, rate=_INTERRUPTION_SAMPLE_RATE):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(int(rate))
        stream.writeframes(bytes(pcm_bytes))
    return output.getvalue()


def _is_vietnamese_language(language):
    return str(language or "").strip().lower().replace("_", "-") in {"vi", "vi-vn", "vietnamese"}


def _to_chinese_num(n):
    number = int(n)
    if number < 0:
        return "负" + _to_chinese_num(-number)
    digits = "零一二三四五六七八九"
    if number < 10:
        return digits[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        return ("" if tens == 1 else digits[tens]) + "十" + (digits[ones] if ones else "")
    # Product indexes normally stay below 100; retain a deterministic reading
    # for larger values rather than silently returning an empty label.
    return "".join(digits[int(char)] for char in str(number))


def _tts_char_half_units(char):
    return 1 if char.isspace() or ord(char) < 128 else 2


def _tts_half_unit_length(text):
    return sum(_tts_char_half_units(char) for char in str(text))


_TTS_SYNTHESIS_MAX_UNITS = 300
_TTS_SYNTHESIS_MAX_HALF_UNITS = _TTS_SYNTHESIS_MAX_UNITS * 2
_TTS_STRONG_BOUNDARY_CHARS = "。！？.!?\n"
_TTS_SOFT_BOUNDARY_CHARS = "；;，,、：:"


def _trim_tts_text_to_boundary(text, next_char):
    """Move a hard TTS cut back to a nearby sentence/phrase boundary.

    The original Cython routine searches only the trailing 40% (and at most
    the last 80 code points) of the candidate.  Strong punctuation wins over
    soft punctuation; a boundary immediately following the candidate is kept
    with it so punctuation is not stranded at the start of the next chunk.
    """
    candidate = str(text or "").strip()
    next_char = str(next_char or "")
    if not candidate:
        return candidate
    if next_char and next_char[0] in _TTS_STRONG_BOUNDARY_CHARS + _TTS_SOFT_BOUNDARY_CHARS:
        return (candidate + next_char[0]).strip()
    min_index = max(0, len(candidate) - 80, int(len(candidate) * 0.6))
    for boundary_chars in (_TTS_STRONG_BOUNDARY_CHARS, _TTS_SOFT_BOUNDARY_CHARS):
        boundary_index = max((candidate.rfind(char, min_index) for char in boundary_chars), default=-1)
        if boundary_index >= min_index:
            return candidate[:boundary_index + 1].strip()
    return candidate


def _limit_tts_synthesis_text(text):
    """Return ``(text, half_unit_length, was_truncated)`` for one TTS job."""
    text = str(text or "").strip()
    text_units = _tts_half_unit_length(text)
    if text_units <= _TTS_SYNTHESIS_MAX_HALF_UNITS:
        return text, text_units, False
    candidate_chars = []
    candidate_units = 0
    for char in text:
        char_units = _tts_char_half_units(char)
        if candidate_units + char_units > _TTS_SYNTHESIS_MAX_HALF_UNITS:
            break
        candidate_chars.append(char)
        candidate_units += char_units
    candidate = "".join(candidate_chars)
    next_char = text[len(candidate):len(candidate) + 1]
    candidate = _trim_tts_text_to_boundary(candidate, next_char)
    return candidate, _tts_half_unit_length(candidate), True


def _is_entrance_message_content(content):
    text = str(content or "").lower()
    return any(word in text for word in ("进入直播间", "进入了直播间", "joined live", "joined the live"))

def _parse_dianpin_keywords(raw):
    if raw is None: return []
    if isinstance(raw, str): values = re.split(r"[,，、;；|/\n]+", raw)
    elif isinstance(raw, (list, tuple, set)): values = raw
    else: values = [raw]
    return list(dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip()))

def _default_dianpin_keywords(product_index):
    number = int(product_index) + 1
    return [f"{number}号", f"第{number}个", f"链接{number}", f"商品{number}"]

def _default_dianpin_keywords_text(product_index): return "、".join(_default_dianpin_keywords(product_index))

def _keyword_hit(needle, text):
    needle, text = str(needle).strip().lower(), str(text).lower()
    return bool(needle and needle in text)

def _build_smart_dianpin_targets(sentences):
    targets = []
    for index, item in enumerate(sentences or []):
        if not isinstance(item, dict): continue
        product_index = int(item.get("product_index", index))
        keywords = _parse_dianpin_keywords(item.get("dianpin_keywords") or item.get("keywords"))
        if not keywords: keywords = _default_dianpin_keywords(product_index)
        targets.append({"product_index": product_index, "keywords": keywords, "item": item})
    return targets

def _build_digital_dianpin_targets(product_scripts): return _build_smart_dianpin_targets(product_scripts)

def _match_smart_dianpin(content, targets):
    for target in targets or []:
        for keyword in target.get("keywords", []):
            if _keyword_hit(keyword, content): return target, keyword
    return None

def _dianpin_transition_text(product_index, keyword=""):
    number = int(product_index) + 1
    return f"好的，接下来为大家介绍{number}号商品。"

def _fallback_reply_text(language, kind, nickname="", content=""):
    normalized_language = str(language or "zh-CN").lower()
    if _is_vietnamese_language(normalized_language):
        if kind == "danmu":
            return f"{nickname}, mình đã thấy bình luận của bạn. Mình trả lời ngắn gọn nhé."
        if kind == "enter":
            return f"Chào mừng {nickname} vào phòng live."
        if kind == "follow":
            return f"Cảm ơn {nickname} đã theo dõi."
        if kind == "like":
            return f"Cảm ơn {nickname} đã ủng hộ."
        if kind == "retention":
            return f"{nickname}, bạn còn ở đó không? Có câu hỏi thì nhắn mình nhé."
        return "Cảm ơn bạn đã theo dõi."
    if not normalized_language.startswith(("zh", "yue", "ja")):
        if kind == "danmu":
            return f"Thanks {nickname}, I got your question."
        if kind == "enter":
            return f"Welcome {nickname}!"
        if kind == "follow":
            return f"Thanks for following, {nickname}!"
        if kind == "like":
            return f"Thanks for the support, {nickname}!"
        if kind == "retention":
            return f"{nickname}, let me know if you have any questions."
        return "Thanks for watching."
    if kind == "danmu":
        if content:
            return f"{content}，{nickname}，这个问题我给你简单说一下。"
        return f"{nickname}，我看到你的问题啦。"
    if kind == "enter":
        return f"欢迎{nickname}来到直播间。"
    if kind == "follow":
        return f"感谢{nickname}的关注。"
    if kind == "like":
        return f"谢谢{nickname}的支持。"
    if kind == "retention":
        return f"{nickname}还在吗？有问题可以直接问我。"
    return "感谢宝子关注。"

def _normalize_input_device_index(value):
    if value in (None, "", -1, "-1"): return None
    try:
        result = int(value)
        return result if result >= 0 else None
    except (TypeError, ValueError): return None


class LocalLiveBrain:
    def __init__(self, *, session_id, config, llm_config, emit_task, queue_provider):
        self.session_id = session_id
        self.config = dict(config or {})
        self.llm_config = dict(llm_config or {})
        self._emit_callback = emit_task
        self._queue_provider = queue_provider
        self._stopped = False
        self._lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._sequence = itertools.count(1)
        self._manual = Queue(); self._simulated = Queue(); self._messages = Queue()
        self._scripts = self._flatten_product_scripts(self.config.get("product_scripts") or [])
        self._script_cursor = 0
        self.script_list = self._scripts
        self.broadcast_cursor = 0
        self.product_item_cursor = 0
        self.script_input_mode = str(self.config.get("script_input_mode") or "text")
        self.script_audio_count = int(self.config.get("script_audio_count", 0) or 0)
        self.script_audio_play_mode = str(self.config.get("script_audio_play_mode") or "sequential")
        self._audio_playlist = []
        self.multi_product_enabled = bool(self.config.get(
            "multi_product_enabled", self.config.get("enable_multi_product", False)))
        self.enable_smart_dianpin = bool(self.config.get(
            "enable_smart_dianpin", self.config.get("enableSmartDianpin", False)))
        self.dianpin_cooldown_seconds = float(self.config.get(
            "dianpin_cooldown_seconds", self.config.get("dianpinCooldownSeconds", 10)) or 0)
        self.origin_idle_video_mode = bool(self.config.get("origin_idle_video_mode", False))
        self._broadcast_buffer_logged = False
        self._interval_rewrite_inflight = False
        self.rewrite_every_sentence = bool(self.config.get("rewrite_every_sentence", False))
        self.script_rewrite_interval = float(self.config.get("script_rewrite_interval", 0) or 0)
        self.last_script_rewrite = float(self.config.get("last_script_rewrite", 0) or 0)
        self.voice_id = self.config.get("voice_id")
        self.voice_speed = self.config.get("voice_speed", 1.1)
        self.use_audio_cache = bool(self.config.get("use_audio_cache", True))
        self.voice_general_config = self.config.get("voice_general_config") or {}
        self.voice_general_config_map = self.config.get("voice_general_config_map") or {}
        self.prohibited_words = list(self.config.get("prohibited_words") or [])
        self.image_model_id = self.config.get("image_model_id") or self.config.get("imageModelId")
        self.voice_infer_version = self.config.get("voice_infer_version") or "v1"
        self.assistant_voice_id = self.config.get("assistant_voice_id")
        self.product_info = self.config.get("product_info")
        self.live_streamer_name = str(self.config.get("live_streamer_name") or "").strip()
        self.is_dual_streamer_mode = bool(self.config.get("is_dual_streamer_mode", False))
        self.interaction_messages = []
        self.current_product_index = int(self.config.get("current_product_index", -1))
        self.product_script_groups = self._build_product_script_groups()
        self.smart_dianpin_targets = _build_smart_dianpin_targets(self.config.get("product_scripts") or [])
        self.last_dianpin_at = 0.0
        self.audio_product_map = {}
        self.shift_schedule = list(self.config.get("shift_schedule") or [])
        self.shift_state = 0; self.shift_started_at = time.monotonic()
        self.rewrite_pool = []
        self._rewrite_inflight = set(); self._interaction_inflight = set()
        self._pending_script_tts = []
        self._executor = ThreadPoolExecutor(max_workers=int(self.config.get("interaction_llm_concurrency", 2) or 2),thread_name_prefix="live-interaction")
        self._interaction_llm_executor = self._executor
        self._rewrite_executor = self._executor
        self.language = str(self.config.get("language") or "zh-CN")
        self.qa_info = self.config.get("qa_info") or ""
        self.special_instructions = str(self.config.get("special_instructions") or "")
        self.question_blocked_keywords = list(self.config.get("question_blocked_keywords") or [])
        self.reply_blocked_keywords = list(self.config.get("reply_blocked_keywords") or [])
        self.blocked_users = list(self.config.get("blocked_users") or [])
        self.comment_reply_interval = int(self.config.get("comment_reply_interval", 0) or 0)
        self.entrance_reply_interval = int(self.config.get("entrance_reply_interval", 0) or 0)
        self.follow_reply_interval = int(self.config.get("follow_reply_interval", 0) or 0)
        self.gift_reply_interval = int(self.config.get("gift_reply_interval", 0) or 0)
        self.mention_interval = int(self.config.get("mention_interval", 100000) or 0)
        self.last_comment_reply = 0.0
        self.last_entrance_reply = 0.0
        self.last_follow_reply = 0.0
        self.last_gift_reply = 0.0
        self.last_mention = 0.0
        self.welcomed_nicknames = set()
        self.exclude_nicknames = set(self.config.get("exclude_nicknames") or [])

    @staticmethod
    def _flatten_product_scripts(product_scripts):
        result = []
        for product_index, product in enumerate(product_scripts):
            if not isinstance(product, dict): continue
            scripts = product.get("scripts") or product.get("script") or []
            if isinstance(scripts, str): scripts = [scripts]
            for script in scripts:
                if isinstance(script,dict):
                    item=dict(script);item.setdefault("type","host");item.setdefault("product_index",product_index)
                    if "content" not in item and "text" in item:item["content"]=item["text"]
                    if str(item.get("content") or "").strip():result.append(item)
                elif str(script).strip():
                    text=str(script).strip()
                    result.append({"type":"host","content":text,"text":text,
                                   "product_index":product_index})
        return result

    @staticmethod
    def _normalize_message_type(msg_type, content=""):
        value = str(msg_type or "弹幕").strip()
        if value in {"分享", "comment", "chat"}:
            value = "弹幕"
        elif value in {"enter", "进入", "进直播间", "member", "join", "进入直播间"}:
            value = "进入直播间"
        elif value in {"follow", "关注主播"}:
            value = "关注"
        elif value in {"gift", "礼物", "点赞", "like"}:
            value = "礼物"
        if value == "弹幕" and _is_entrance_message_content(content):
            return "进入直播间"
        return value

    @staticmethod
    def _summarize_task(task_type, payload):
        return f"{task_type}: {payload.get('text') or payload.get('content') or ''}".strip()

    def _emit_task(self, task_type, payload):
        task = {"id": next(self._sequence), "type": task_type, "payload": dict(payload)}
        result = self._emit_callback(task)
        return task["id"] if result is None else result

    def _enqueue_tts(self, text, *, queue, target_face_index=0, use_silent_features=False,
                     voice_id=None, product_index=None, seek_after_ms=None):
        from .language_prompts import language_forbids_han
        from .llm_reply import contains_han_text, filter_han_for_language
        from .text_processing import strip_prohibited_words

        if not text:
            return None
        original_text = strip_prohibited_words(text, self.prohibited_words).strip()
        if not original_text:
            return None
        filtered_text = filter_han_for_language(original_text, self.language)
        needs_language_translate = False
        if filtered_text:
            final_text = filtered_text
        elif language_forbids_han(self.language) and contains_han_text(original_text):
            final_text = original_text
            needs_language_translate = True
        else:
            return None

        selected_voice_id = voice_id if voice_id else self.voice_id
        payload = {
            "text": final_text,
            "voice_id": selected_voice_id,
            "voice_infer_version": self.voice_infer_version,
            "language": self.language,
            "speed": self.voice_speed,
            "queue": queue,
            "target_face_index": target_face_index,
            "use_silent_features": use_silent_features,
            "use_cache": self.use_audio_cache,
            "needs_language_translate": needs_language_translate,
        }
        if product_index is not None:
            payload["product_index"] = product_index
        if seek_after_ms is not None:
            payload["seek_after_ms"] = int(seek_after_ms)
        voice_key = str(payload.get("voice_id") or "")
        voice_general_config = self.voice_general_config_map.get(voice_key)
        if not voice_general_config:
            voice_general_config = self.voice_general_config
        if voice_general_config:
            payload["voice_general_config"] = voice_general_config
        return self._emit_task("tts_speak", payload)

    def request_manual_speak(self, text): self._manual.put(str(text))
    def request_simulated_question(self, content): self._simulated.put(str(content))
    def submit_danmu(self, message):
        nickname = (message.get("nickname") or message.get("user") or "").strip()
        content = (message.get("content") or message.get("text") or "").strip()
        msg_type = self._normalize_message_type(
            message.get("msg_type") or message.get("type") or message.get("kind") or "弹幕",
            content=content)
        if not nickname or (self.live_streamer_name and nickname == self.live_streamer_name):
            return None
        timestamp = float(message.get("timestamp") or time.time())
        value = InteractionMessage(msg_type, nickname, content, timestamp)
        with self._lock:
            if msg_type == "进入直播间":
                self.interaction_messages.insert(0, value)
                if len(self.interaction_messages) > INTERACTION_MESSAGE_CAP:
                    self.interaction_messages = self.interaction_messages[:INTERACTION_MESSAGE_CAP]
            else:
                self.interaction_messages.append(value)
                if len(self.interaction_messages) > INTERACTION_MESSAGE_CAP:
                    self.interaction_messages = self.interaction_messages[-INTERACTION_MESSAGE_CAP:]
        return None
    def stopped(self): return bool(self._stopped)
    def mark_stopped(self):
        self._stopped = True
        self._executor.shutdown(wait=False, cancel_futures=True)
    def _queue_lengths(self): return dict(self._queue_provider() or {})

    def _product_config(self, product_index):
        products = self.config.get("product_scripts") or self.config.get("multi_product_configs") or []
        return products[product_index] if 0 <= int(product_index) < len(products) and isinstance(products[product_index],dict) else {}

    def _resolve_product_info(self, product_index):
        products = self.config.get("product_scripts") or []
        for item in products:
            try:
                if int(item.get("product_index")) != int(product_index):
                    continue
                content = item.get("content")
                if content:
                    return str(content)
            except (TypeError, ValueError, AttributeError):
                continue
        return self.product_info

    def _active_product_info(self): return self._resolve_product_info(self.current_product_index)
    def _find_product_group_index(self, product_index):
        groups = self.product_script_groups or []
        for group_index, group in enumerate(groups):
            try:
                if int(group.get("product_index")) == int(product_index):
                    return group_index
            except (TypeError, ValueError, AttributeError):
                continue
        return None
    def _find_product_script_cursor(self, product_index):
        for cursor, item in enumerate(self.script_list or []):
            try:
                if int(item.get("product_index")) == int(product_index):
                    return cursor
            except (TypeError, ValueError, AttributeError):
                continue
        return None
    def _remember_audio_product(self, audio_path, product_index): self.audio_product_map[str(audio_path)] = product_index

    @staticmethod
    def _interaction_enabled(interval): return int(interval) < 100000

    def _pick_unprocessed(self, msg_type, *, exclude_nicknames=None):
        excluded = exclude_nicknames or set()
        for message in self.interaction_messages:
            if not message.processed and message.msg_type == msg_type and message.nickname not in excluded:
                message.processed = True; return message
        return None

    def _pick_comment(self): return self._pick_unprocessed("弹幕")
    def _mark_nickname_messages_processed(self, msg_type, nickname):
        for message in self.interaction_messages:
            if message.nickname == nickname and message.msg_type == msg_type:
                message.processed = True

    def _normalize_control_text_reply(self,reply, nickname):
        from .taobao_live_control import COMMENT_MAX_LEN

        text = str(reply or "").strip()
        name = str(nickname or "").strip() or "用户"
        mention = f"@{name}"
        if text.startswith(mention):
            normalized = text
        elif not text.startswith("@"):
            normalized = f"{mention} {text}"
        else:
            parts = text.split(" ", 1)
            normalized = mention + (f" {parts[1]}" if len(parts) > 1 else "")
        normalized = " ".join(normalized.split())
        if len(normalized) > int(COMMENT_MAX_LEN):
            normalized = normalized[:int(COMMENT_MAX_LEN)]
        return normalized.strip()

    def _switch_to_product(self, group_index):
        self.current_product_index = int(group_index)
        self.product_item_cursor = 0
        cursor = self._find_product_script_cursor(group_index)
        if cursor is not None: self._script_cursor = cursor
        self._emit_task("switch_product", {"product_index":self.current_product_index})
        self._sync_product_ui(self.current_product_index)

    def _sync_product_ui(self, product_index):
        self._sync_product_image_popup(product_index); self._sync_taobao_product_popup(product_index)
    def _sync_product_image_popup(self, product_index):
        if self.config.get("enable_product_image_sync"):
            self._emit_task("product_image_popup", {"product_index":product_index,"product":self._product_config(product_index)})
    def _sync_taobao_product_popup(self, product_index):
        if self.config.get("enable_taobao_product_popup"):
            self._emit_task("taobao_product_popup", {"product_index":product_index,"product":self._product_config(product_index)})

    def _jump_to_digital_dianpin(self, product_index, matched_kw, *, content=""):
        transition = _dianpin_transition_text(product_index, matched_kw)
        switch_payload = {"clear_queues": True, "product_index": product_index}
        if self.multi_product_enabled:
            group_index = self._find_product_group_index(product_index)
            if group_index is None:
                print(f"[local.live] 数字人点品未找到多品分组 product={product_index + 1} "
                      f"keyword={matched_kw!r}")
                return False
            group = self.product_script_groups[group_index]
            group_config = group.get("config") or {}
            new_image_model_id = group_config.get("imageModelId")
            new_voice_id = group_config.get("voiceModelId")
            if new_image_model_id:
                self.image_model_id = new_image_model_id
            if new_voice_id:
                self.voice_id = new_voice_id
            self.current_product_index = group_index % len(self.product_script_groups)
            self.current_product_info = group.get("product_info") or self.product_info
            self.product_item_cursor = 0
            switch_payload.update({
                "new_image_model_id": new_image_model_id,
                "new_voice_id": new_voice_id,
                "voice_infer_version": self.voice_infer_version,
            })
        else:
            if not self.script_list:
                print("[local.live] 数字人点品失败：话术列表为空")
                return False
            cursor = self._find_product_script_cursor(product_index)
            if cursor is None:
                print(f"[local.live] 数字人点品未找到话术起点 product={product_index + 1} "
                      f"keyword={matched_kw!r}")
                return False
            self.broadcast_cursor = cursor
            self.current_product_index = product_index
            self.current_product_info = self._resolve_product_info(product_index)
        self._pending_script_tts = []
        print(f"[local.live] 数字人点品命中 product={product_index + 1} "
              f"keyword={matched_kw!r} content={str(content)[:40]}")
        self._emit_task("clear_normal_queues", switch_payload)
        self._enqueue_tts(transition, queue="normal", target_face_index=0,
                          product_index=product_index)
        self._sync_product_ui(product_index)
        return True

    def _try_smart_dianpin(self, content, *, now=None):
        if not self.enable_smart_dianpin or not self.smart_dianpin_targets:
            return False
        now = time.time() if now is None else float(now)
        if self.last_dianpin_at > 0:
            cooldown = max(float(self.dianpin_cooldown_seconds), 5.0)
            elapsed = now - self.last_dianpin_at
            if elapsed < cooldown:
                remaining = int(max(cooldown - elapsed, 0))
                print(f"[local.live] 智能点品冷却中，剩余{remaining} 秒")
                return False
        matched = _match_smart_dianpin(content, self.smart_dianpin_targets)
        if not matched:
            return False
        target, keyword = matched
        product_index = int(target["product_index"])
        if not self.origin_idle_video_mode:
            if not self._jump_to_digital_dianpin(product_index, keyword, content=content):
                return False
            self.last_dianpin_at = now
            return True
        start_ms = int(target.get("start_ms") or target.get("item", {}).get("start_ms") or 0)
        transition = _dianpin_transition_text(product_index, keyword)
        print(f"[local.live] 智能点品命中 product={product_index + 1} "
              f"keyword={keyword!r} start_ms={start_ms} content={str(content)[:40]}")
        self._enqueue_tts(transition, queue="danmu", target_face_index=0,
                          seek_after_ms=start_ms)
        self.last_dianpin_at = now
        self._sync_product_ui(product_index)
        return True

    def _speak_interaction_reply(self, reply):
        from .text_processing import contains_blocked
        text=(reply or "").strip()
        if not text or contains_blocked(text,self.reply_blocked_keywords):return False
        print(f"[互动] 生成回复：{text[:80]}")
        self._enqueue_tts(text,queue="danmu",target_face_index=0)
        return True

    def _ai_control_reply_enabled(self): return bool(self.config.get("enable_ai_control_reply",False))
    def _submit_interaction_llm(self, *, kind, nickname, content, llm_call):
        language = self.language
        def worker():
            try:
                reply = llm_call()
                if not reply:
                    reply = _fallback_reply_text(language, kind, nickname, content)
                self._speak_interaction_reply(reply)
            except Exception as exc:
                print(f"[local.live] {kind} LLM 异常: {exc}")
        executor = self._interaction_llm_executor
        if executor is None:
            worker()
        else:
            executor.submit(worker)
        return None
    def _submit_ai_control_reply(self, nickname, content, product_info):
        if self._stopped:
            return None
        executor = self._interaction_llm_executor
        language = self.language
        qa_info = self.qa_info
        special = self.special_instructions

        def worker():
            from .llm_reply import generate_text_reply
            try:
                reply = generate_text_reply(nickname, content, product_info, qa_info, special)
                if not reply:
                    if _is_vietnamese_language(language):
                        reply = f"@{nickname} Mình đã收到您的提问。"
                    else:
                        reply = f"@{nickname} 收到，请稍等主播回复哦"
                reply = self._normalize_control_text_reply(reply, nickname)
                if not self._stopped:
                    print(f"[互动] 场控回复：{reply[:80]}")
                    self._send_taobao_control_reply(reply)
            except Exception as exc:
                print(f"[local.live] AI场控 LLM 异常: {exc}")

        if executor is not None:
            executor.submit(worker)
        else:
            worker()
        return None

    def _rewrite_worker(self, text):
        from .generalize_sentences import optimize_script
        try:
            rewritten=optimize_script(text)
            if rewritten:
                with self._lock:self.rewrite_pool.append(rewritten)
        finally: self._rewrite_inflight.discard(text)
    def _submit_interval_rewrite(self, processed_text, *, product_index=None):
        executor=self._interaction_llm_executor or self._rewrite_executor
        if executor is None:return False
        text=str(processed_text or "")
        self._interval_rewrite_inflight=True
        def worker():
            from .llm_reply import script_rewrite_content
            from .text_processing import process_special_variables
            rewritten=text
            try:
                candidate=script_rewrite_content(text,self.special_instructions)
                if str(candidate or "").strip():rewritten=str(candidate)
            except Exception as error:
                print(f"[local.live] 话术重写失败: {error}")
            try:
                final_text=process_special_variables(rewritten).strip()
                if not final_text:final_text=process_special_variables(text).strip()
                with self._lock:
                    if not self.stopped() and final_text:
                        self._pending_script_tts.append((final_text,product_index))
            except Exception as error:
                print(f"[local.live] 话术重写收尾失败，回退原稿: {error}")
                fallback=process_special_variables(text).strip()
                with self._lock:
                    if not self.stopped() and fallback:
                        self._pending_script_tts.append((fallback,product_index))
            finally:
                self._interval_rewrite_inflight=False
        try:
            executor.submit(worker)
        except Exception:
            self._interval_rewrite_inflight=False
            return False
        return True
    def _tick_rewrite_pool(self):
        if self._queue_lengths().get("normal",0): return
        with self._lock:
            if not self.rewrite_pool:return
            text=self.rewrite_pool.pop(0)
        self._enqueue_tts(text,queue="normal",product_index=self.current_product_index)

    def _advance_shift(self, now):
        if not self.shift_schedule: return
        self.shift_state=(self.shift_state+1)%len(self.shift_schedule); self.shift_started_at=now
        shift=self.shift_schedule[self.shift_state]
        product=shift.get("product_index")
        if product is not None: self._switch_to_product(int(product))
        self._emit_task("shift_changed",{"shift_index":self.shift_state,"shift":shift})
    def _tick_shift_schedule(self):
        if not self.shift_schedule: return
        shift=self.shift_schedule[self.shift_state]
        duration=float(shift.get("duration_seconds") or shift.get("duration") or 0)
        if duration and time.monotonic()-self.shift_started_at>=duration: self._advance_shift(time.monotonic())
    def _tick_multi_product_broadcast(self, normal_backlog, pending_normal=0):
        groups = self.product_script_groups
        if not groups:
            return
        if self.current_product_index < 0:
            if (normal_backlog > PRODUCT_SWITCH_QUEUE_THRESHOLD or
                    pending_normal > 0):
                return
            self._switch_to_product(0)
            return

        group = groups[self.current_product_index % len(groups)]
        items = group.get("items") or []
        if not items:
            self._switch_to_product((self.current_product_index + 1) % len(groups))
            return
        if self.product_item_cursor >= len(items):
            if len(groups) > 1:
                if (normal_backlog > PRODUCT_SWITCH_QUEUE_THRESHOLD or
                        pending_normal > 0):
                    return
                self._switch_to_product((self.current_product_index + 1) % len(groups))
                return
            self.product_item_cursor = 0
        item = items[self.product_item_cursor]
        self.product_item_cursor += 1
        self._emit_script_item(item)

    def _tick_broadcast(self):
        if self._interval_rewrite_inflight or self.origin_idle_video_mode:
            return
        for _ in range(TTS_EMIT_BURST_MAX):
            if self._interval_rewrite_inflight:
                return
            lengths = self._queue_lengths()
            normal_backlog = int(lengths.get("normal", 0) or 0)
            pending_normal = int(lengths.get("pending_normal", 0) or 0)
            if pending_normal >= TTS_PIPELINE_DEPTH:
                return
            if normal_backlog >= BROADCAST_QUEUE_TARGET:
                self._broadcast_buffer_logged = True
                return
            self._broadcast_buffer_logged = False
            if self.script_input_mode == "audio":
                self._emit_next_audio_index()
                continue
            if self.multi_product_enabled:
                self._tick_multi_product_broadcast(normal_backlog, pending_normal)
                continue
            if not self.script_list:
                return
            item = self.script_list[self.broadcast_cursor % len(self.script_list)]
            self.broadcast_cursor += 1
            self._script_cursor = self.broadcast_cursor
            self._emit_script_item(item)

    def _build_product_script_groups(self):
        groups=[]
        for index,item in enumerate(self.config.get("product_scripts") or []):
            if not isinstance(item,dict):
                continue
            scripts=item.get("scripts") or item.get("script") or []
            if isinstance(scripts,str): scripts=[scripts]
            items=[]
            for script in scripts:
                if isinstance(script,dict):
                    value=dict(script);value.setdefault("product_index",index);value.setdefault("type","host")
                    if "content" not in value and "text" in value:value["content"]=value["text"]
                    if str(value.get("text") or value.get("content") or "").strip():items.append(value)
                elif str(script).strip():
                    items.append({"type":"host","content":str(script).strip(),
                                  "text":str(script).strip(),"product_index":index})
            groups.append({**item,"product_index":index,"items":items})
        return groups
    def _emit_script_item(self,item):
        from .text_processing import process_special_variables

        item_type=item.get("type")
        product_index=item.get("product_index")
        now=time.time()
        if item_type == "host":
            content=item.get("content") or ""
            if self.rewrite_every_sentence:
                if isinstance(self.rewrite_pool,list) and self.rewrite_pool:
                    content=self.rewrite_pool.pop(0)
                elif (self._interaction_enabled(self.script_rewrite_interval) and
                      now-self.last_script_rewrite >= self.script_rewrite_interval and
                      self.llm_config and
                      int(self._queue_lengths().get("normal",0) or 0) <= TTS_BACKLOG_LOW_WATERMARK):
                    self.last_script_rewrite=now
                    if self._submit_interval_rewrite(content,product_index=product_index):
                        return
            processed_text=process_special_variables(content)
            return self._enqueue_tts(processed_text,queue="normal",target_face_index=0,
                                     use_silent_features=False,product_index=product_index)
        if item_type == "assistant":
            content=item.get("content") or ""
            processed_text=process_special_variables(content)
            assistant_voice_id=self.assistant_voice_id or self.voice_id
            dual=bool(self.is_dual_streamer_mode)
            return self._enqueue_tts(processed_text,queue="normal",target_face_index=int(dual),
                                     use_silent_features=not dual,voice_id=assistant_voice_id,
                                     product_index=product_index)
        if item_type == "pause":
            duration=float(item.get("duration") or 0)
            if duration <= 0:
                return
            return self._emit_task("pause",{"duration":duration,"queue":"normal",
                                   "target_face_index":0,"use_silent_features":True})
    def _emit_next_audio_index(self):
        if self.script_audio_count <= 0:
            return
        if not self._audio_playlist:
            self._audio_playlist=list(range(self.script_audio_count))
            if self.script_audio_play_mode == "random":
                random.shuffle(self._audio_playlist)
        index=self._audio_playlist.pop(0)
        self._emit_task("play_audio_index",{"index":index,"queue":"normal","target_face_index":0})
    def _drain_manual_speaks(self):
        try: self._enqueue_tts(self._manual.get_nowait(),queue="manual")
        except Empty: pass
    def _drain_simulated_questions(self):
        try: self._enqueue_tts(self._simulated.get_nowait(),queue="danmu")
        except Empty: pass
    def _drain_pending_script_tts(self):
        # The producer may finish generalized script text on an executor
        # thread.  Swap the list under the lock, then emit outside it so an
        # emit callback can safely enqueue more work.
        with self._lock:
            pending=self._pending_script_tts
            self._pending_script_tts=[]
        for text_snapshot,product_index in pending:
            self._enqueue_tts(text_snapshot,queue="normal",target_face_index=0,
                              use_silent_features=False,product_index=product_index)
    def _send_taobao_control_reply(self, reply):
        from .taobao_live_control import get_taobao_controller
        from .text_processing import contains_blocked

        text = str(reply or "").strip()
        if not text or contains_blocked(text, self.reply_blocked_keywords):
            return False
        try:
            controller = get_taobao_controller()
            if not controller.connected():
                print("[local.live] AI场控发送跳过：中控台未连接")
                return False
            result = controller.send_comment(text)
            print(f"[local.live] AI场控发送: {text[:50]}")
            return bool(result)
        except Exception as exc:
            print(f"[local.live] AI场控发送失败: {exc}")
            return False

    def _tick_interactions(self):
        from .llm_reply import reply_danmu, reply_enter, reply_follow, reply_like, reply_retention
        from .text_processing import contains_blocked, is_user_blocked

        now = time.time()
        product_info = self._active_product_info()

        if (self._interaction_enabled(self.comment_reply_interval) and
                now - self.last_comment_reply >= max(self.comment_reply_interval, 0)):
            message = self._pick_comment()
            if message is not None:
                nickname = message.nickname
                content = message.content
                if (nickname not in self.exclude_nicknames and
                        not is_user_blocked(nickname, self.blocked_users) and
                        not contains_blocked(content, self.question_blocked_keywords)):
                    if self._try_smart_dianpin(content):
                        return
                    self.last_comment_reply = now
                    self._submit_interaction_llm(
                        kind="danmu", nickname=nickname, content=content,
                        llm_call=lambda: reply_danmu(
                            nickname, content, product_info, self.qa_info,
                            self.special_instructions))
                    if self._ai_control_reply_enabled():
                        self._submit_ai_control_reply(nickname, content, product_info)

        if (self._interaction_enabled(self.entrance_reply_interval) and
                now - self.last_entrance_reply >= max(self.entrance_reply_interval, 0)):
            message = self._pick_unprocessed("进入直播间", exclude_nicknames=self.welcomed_nicknames)
            if message is not None:
                nickname = message.nickname
                if (nickname and nickname not in self.exclude_nicknames and
                        not is_user_blocked(nickname, self.blocked_users)):
                    self.welcomed_nicknames.add(nickname)
                    self.last_entrance_reply = now
                    self._submit_interaction_llm(
                        kind="enter", nickname=nickname, content="",
                        llm_call=lambda: reply_enter(
                            nickname, self._active_product_info(), self.special_instructions))

        if (self._interaction_enabled(self.follow_reply_interval) and
                now - self.last_follow_reply >= max(self.follow_reply_interval, 0)):
            message = self._pick_unprocessed("关注")
            if message is not None:
                nickname = message.nickname
                if (nickname and nickname not in self.exclude_nicknames and
                        not is_user_blocked(nickname, self.blocked_users)):
                    self.last_follow_reply = now
                    self._submit_interaction_llm(
                        kind="follow", nickname=nickname, content="",
                        llm_call=lambda: reply_follow(
                            nickname, self._active_product_info(), self.special_instructions))

        if (self._interaction_enabled(self.gift_reply_interval) and
                now - self.last_gift_reply >= max(self.gift_reply_interval, 0)):
            message = self._pick_unprocessed("礼物")
            if message is not None:
                nickname = message.nickname
                if (nickname and nickname not in self.exclude_nicknames and
                        not is_user_blocked(nickname, self.blocked_users)):
                    self.last_gift_reply = now
                    self._submit_interaction_llm(
                        kind="like", nickname=nickname, content="",
                        llm_call=lambda: reply_like(
                            nickname, self._active_product_info(), self.special_instructions))

        if (not self._interaction_enabled(self.mention_interval) or
                now - self.last_mention < max(self.mention_interval, 0)):
            return
        with self._lock:
            candidates = []
            seen = set()
            for message in self.interaction_messages:
                nickname = message.nickname.strip()
                if (not nickname or nickname in seen or nickname in self.exclude_nicknames or
                        is_user_blocked(nickname, self.blocked_users)):
                    continue
                seen.add(nickname)
                candidates.append(nickname)
                if len(candidates) >= 8:
                    break
        if not candidates:
            return
        nickname = random.choice(candidates)
        self.last_mention = now
        if not self.llm_config:
            self._speak_interaction_reply(
                _fallback_reply_text(self.language, "retention", nickname, ""))
            return
        self._submit_interaction_llm(
            kind="retention", nickname=nickname, content="",
            llm_call=lambda: reply_retention(
                nickname, self._active_product_info(), self.special_instructions))

    def tick(self):
        if self.stopped() or not self._tick_lock.acquire(blocking=False): return
        try:
            self._drain_simulated_questions()
            self._drain_manual_speaks()
            self._drain_pending_script_tts()
            self._tick_interactions()
            self._tick_broadcast()
            self._tick_rewrite_pool()
            self._tick_shift_schedule()
        finally:
            self._tick_lock.release()


class LiveManager(DigitalLiveManager):
    def __init__(self, config):
        config = dict(config or {})
        runtime_dir = config.get("runtime_dir") or config.get("base_dir") or os.getcwd()
        super().__init__(config, runtime_dir)
        self._session = None
        self._audio_task_queues = {"normal": Queue(), "danmu": Queue()}
        self._audio_worker_stop = threading.Event()
        self._audio_stop = self._audio_worker_stop
        self._audio_worker = None
        self._pending_audio_tasks = {"normal": 0, "danmu": 0}
        # Compatibility alias for callers recovered before the native field
        # name was identified.  Both names intentionally share one mapping.
        self._pending_audio = self._pending_audio_tasks
        self.host_streamer = None
        self._primary_voice_id = str(config.get("voice_id") or "").strip()
        self.voice_infer_version = str(config.get("voice_infer_version") or "v1")
        self.language = str(config.get("language") or "zh-CN")
        self.voice_speed = float(config.get("voice_speed", 1.1) or 1.1)
        self.use_audio_cache = bool(config.get("use_audio_cache", True))
        self.use_near_audio_clone = bool(config.get("use_near_audio_clone", False))
        self._normal_audio_epoch = 0
        self._script_audio_files = list(config.get("script_audio_files") or [])
        self._voice_synth = None; self._voice_synth_key = None
        self._near_clone_synth = None; self._near_clone_key = None; self._near_clone_asr_model = None
        self._interruption_stop = threading.Event(); self._interruption_thread = None; self._interruption_stream = None
        self._local_session_thread = None
        self._local_session_lock = threading.RLock()
        self._local_session_stop_event = threading.Event()

    def __del__(self):
        try: self.stop_local_runtime()
        except Exception: pass

    @staticmethod
    def _expand_square_options(text):
        match = re.search(r"\[([^\[\]]+)\]", text)
        if not match: return [text]
        options = [part.strip() for part in re.split(r"[|/]", match.group(1)) if part.strip()]
        return [text[:match.start()] + option + text[match.end():] for option in options]

    @classmethod
    def _expand_brace_options(cls, text, max_candidates=64):
        values = [text]
        pattern = re.compile(r"\{([^{}]+)\}")
        while len(values) < max_candidates:
            expanded = []; changed = False
            for value in values:
                match = pattern.search(value)
                if not match: expanded.append(value); continue
                changed = True
                for option in re.split(r"[|/]", match.group(1)):
                    expanded.append(value[:match.start()] + option.strip() + value[match.end():])
            values = expanded[:max_candidates]
            if not changed: break
        return values

    @classmethod
    def _expand_cache_text_candidates(cls, text):
        output = []
        for item in cls._expand_brace_options(text): output.extend(cls._expand_square_options(item))
        return list(dict.fromkeys(value.strip() for value in output if value.strip()))

    @staticmethod
    def _replace_time_variables(text):
        now = time.localtime()
        replacements = {"{year}":str(now.tm_year), "{month}":str(now.tm_mon), "{day}":str(now.tm_mday),
                        "{hour}":str(now.tm_hour), "{minute}":f"{now.tm_min:02d}"}
        for key, value in replacements.items(): text = text.replace(key, value)
        return text

    def _create_silent_audio(self, duration):
        path = Path(tempfile.gettempdir()) / f"yunchuang_silence_{time.time_ns()}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed")); wav.writeframes(b"\0\0" * int(max(0,duration)*16000))
        return str(path)

    def get_audio_duration(self,wav_path):
        with wave.open(str(wav_path), "rb") as wav: return wav.getnframes() / wav.getframerate()

    def _pending_audio_snapshot(self): return dict(self._pending_audio_tasks)
    def _adjust_pending_audio(self, queue_name, delta):
        queue_name = queue_name if queue_name in self._pending_audio_tasks else "normal"
        self._pending_audio_tasks[queue_name] = max(
            0, self._pending_audio_tasks.get(queue_name, 0) + delta)

    def _audio_task_queue_name(self, task):
        payload = task.get("payload") or {}
        queue_name = str(payload.get("queue") or "normal").strip() or "normal"
        if queue_name not in self._pending_audio_tasks:
            return "normal"
        return queue_name

    def get_queue_lengths(self):
        pending=self._pending_audio_snapshot()
        streamer=getattr(self,"host_streamer",None) or self._runtime
        lengths={}
        if streamer:
            try: lengths=streamer.get_queue_lengths() or {}
            except Exception: lengths={}
        return {"normal":int(lengths.get("normal") or 0),
                "danmu":int(lengths.get("danmu") or 0),
                "pending_normal":pending["normal"],
                "pending_danmu":pending["danmu"]}

    def execute_task(self, task):
        if self._audio_worker and self._audio_worker.is_alive():
            queue_name=self._audio_task_queue_name(task)
            self._adjust_pending_audio(queue_name,1)
            self._audio_task_queues[queue_name].put(task)
        else: self._execute_task_inline(task)
    def _enqueue_audio_task(self, task, queue_name):
        queue_name = queue_name if queue_name in self._audio_task_queues else "normal"
        self._adjust_pending_audio(queue_name, 1)
        self._audio_task_queues[queue_name].put(task)

    def _take_next_audio_task(self):
        try:
            return self._audio_task_queues["danmu"].get_nowait(), "danmu"
        except Empty:
            try:
                return self._audio_task_queues["normal"].get(timeout=0.2), "normal"
            except Empty:
                return None, None

    def _drain_audio_task_queue(self):
        for queue_name, task_queue in self._audio_task_queues.items():
            while True:
                try:
                    task_queue.get_nowait()
                    self._adjust_pending_audio(queue_name, -1)
                except Empty:
                    break

    def _drain_normal_audio_task_queue(self):
        task_queue = self._audio_task_queues["normal"]
        while True:
            try:
                task_queue.get_nowait()
                self._adjust_pending_audio("normal", -1)
            except Empty:
                break

    def _execute_task_inline(self, task):
        payload=task.get("payload",{}); kind=task.get("type")
        if kind=="tts_speak": self._handle_tts_speak(payload)
        elif kind=="pause": self._handle_pause(payload)
        elif kind=="clear_normal_queues": self._handle_clear_normal_queues(payload)
        elif kind=="switch_model": self._handle_switch_model(payload)
        elif kind=="play_audio_index": self._handle_play_audio_index(payload)
        elif kind=="product_image_popup": self._handle_product_image_popup(payload)
        elif kind=="taobao_product_popup": self._handle_taobao_product_popup(payload)
        elif kind=="taobao_send_comment":
            controller=getattr(self,"_taobao_controller",None)
            if controller and hasattr(controller,"send_comment"): controller.send_comment(payload.get("text",""))

    def _handle_tts_speak(self, payload):
        text = str(payload.get("text") or "").strip()
        streamer = self.host_streamer or self._runtime
        if not text or not streamer:
            return

        voice_id = str(payload.get("voice_id") or self._primary_voice_id or "").strip()
        if not voice_id:
            print("[live.local] tts_speak 缺少音色 ID")
            return
        voice_infer_version = str(
            payload.get("voice_infer_version") or self.voice_infer_version)
        language = str(payload.get("language") or self.language)
        speed = float(payload.get("speed") or self.voice_speed)
        queue_name = str(payload.get("queue") or "normal")
        target_face_index = int(payload.get("target_face_index") or 0)
        use_silent_features = bool(payload.get("use_silent_features", False))
        use_cache = bool(payload.get("use_cache", self.use_audio_cache))
        epoch_at_start = self._normal_audio_epoch

        synthesis_text = self._replace_time_variables(text)
        needs_translate = bool(payload.get("needs_language_translate"))
        if not needs_translate:
            from .language_prompts import language_forbids_han
            from .llm_reply import contains_han_text
            needs_translate = language_forbids_han(language) and contains_han_text(synthesis_text)
        if needs_translate:
            from .llm_reply import translate_text_llm
            translated = self._run_with_timeout(
                lambda: translate_text_llm(synthesis_text, language, raise_on_failure=True),
                float(self.config.get("tts_cloud_timeout_seconds", 60) or 60),
                "TTS 翻译",
            )
            if translated:
                synthesis_text = str(translated).strip()

        synthesis_text, _text_units, _was_truncated = _limit_tts_synthesis_text(synthesis_text)
        if not synthesis_text:
            return

        voice_general_config = dict(payload.get("voice_general_config") or {})
        try:
            if (self.use_near_audio_clone and queue_name == "danmu"
                    and hasattr(streamer, "get_near_audio_clip")):
                audio = self._run_with_timeout(
                    lambda: self._synthesize_with_near_clone(
                        synthesis_text=synthesis_text, speed=speed, language=language),
                    TTS_LOCAL_TIMEOUT_SECONDS,
                    "近场克隆 TTS",
                )
            elif voice_infer_version == "minimax":
                from .minimax import synthesize_speech_minimax
                minimax_config = self._build_minimax_runtime_config(voice_general_config)
                cloud_voice_id = minimax_config.get("minimax_voice_id") or voice_id
                audio = self._run_with_timeout(
                    lambda: synthesize_speech_minimax(
                        text=synthesis_text,
                        voice_id=cloud_voice_id,
                        minimax_config=minimax_config,
                        speed=speed,
                        language=language,
                        use_cache=use_cache,
                    ),
                    TTS_CLOUD_TIMEOUT_SECONDS,
                    "Minimax TTS",
                )
            elif voice_infer_version == "cosyvoice":
                from .cosyvoice import synthesize_speech_cosyvoice
                cosyvoice_config = self._build_cosyvoice_runtime_config(voice_general_config)
                cloud_voice_id = cosyvoice_config.get("cosyvoice_voice_id") or voice_id
                audio = self._run_with_timeout(
                    lambda: synthesize_speech_cosyvoice(
                        text=synthesis_text,
                        voice_id=cloud_voice_id,
                        cosyvoice_config=cosyvoice_config,
                        speed=speed,
                        language=language,
                        use_cache=use_cache,
                    ),
                    TTS_CLOUD_TIMEOUT_SECONDS,
                    "CosyVoice TTS",
                )
            else:
                provider = str(voice_general_config.get("provider") or "").strip().lower()
                if provider in {"minimax", "cosyvoice"}:
                    print(f"[live.local] {provider} 音色与推理版本不匹配")
                    return
                synthesizer = self._ensure_voice_synthesizer(
                    voice_id, voice_infer_version)
                if not synthesizer:
                    print(f"[live.local] 无法加载音色: {voice_id}")
                    return
                audio = self._run_with_timeout(
                    lambda: synthesizer.synthesize(
                        synthesis_text,
                        speed=speed,
                        language=language,
                        use_cache=use_cache,
                    ),
                    TTS_LOCAL_TIMEOUT_SECONDS,
                    f"{voice_id} TTS",
                )
        except Exception as exc:
            print(f"[live.local] TTS 合成失败: {exc}")
            return
        if not audio:
            return
        if queue_name == "normal" and epoch_at_start != self._normal_audio_epoch:
            return
        streamer.add_audio_to_queue(
            audio,
            queue_name=queue_name,
            use_silent_features=use_silent_features,
            target_face_index=target_face_index,
        )
        if queue_name == "normal":
            product_index = payload.get("product_index")
            session = self._session
            if product_index is not None and session is not None:
                session._remember_audio_product(audio, product_index)
        seek_after_ms = payload.get("seek_after_ms")
        if seek_after_ms is not None and hasattr(streamer, "schedule_seek_after_interaction"):
            try:
                streamer.schedule_seek_after_interaction(int(seek_after_ms))
            except Exception as exc:
                print(f"[live.local] 延迟跳转设置失败: {exc}")
    def _handle_pause(self,payload):
        duration = float(payload.get("duration") or 0)
        streamer = self.host_streamer or self._runtime
        if duration <= 0 or not streamer:
            return
        audio_path = self._create_silent_audio(duration)
        if not audio_path:
            return
        queue_name = str(payload.get("queue") or "normal")
        try:
            streamer.add_audio_to_queue(
                audio_path,
                queue_name,
                use_silent_features=True,
            )
        except Exception as exc:
            print(f"[live.local] 添加停顿音频失败: {exc}")
    def _handle_clear_normal_queues(self,payload):
        self._normal_audio_epoch += 1
        self._drain_normal_audio_task_queue()
        streamer = self.host_streamer or self._runtime
        if streamer:
            try:
                streamer.clear_audio_queues()
            except Exception as exc:
                print(f"[live.local] 清理普通音频队列失败: {exc}")
        if payload.get("new_image_model_id") or payload.get("new_voice_id"):
            switch_payload = dict(payload or {})
            switch_payload["clear_queues"] = False
            self._enqueue_audio_task({
                "id": 0,
                "session_id": None,
                "seq": 0,
                "type": "switch_model",
                "payload": switch_payload,
            }, "normal")
    def _handle_switch_model(self,payload):
        new_image_model_id = payload.get("new_image_model_id")
        new_voice_id = payload.get("new_voice_id")
        voice_infer_version = str(
            payload.get("voice_infer_version") or self.voice_infer_version)
        streamer = self.host_streamer or self._runtime

        if new_image_model_id and streamer and hasattr(streamer, "switch_image_model"):
            image_base_dir = self.config.get("image_base_dir")
            new_model_base = (Path(image_base_dir) / str(new_image_model_id)
                              if image_base_dir else Path(str(new_image_model_id)))
            if new_model_base.exists():
                try:
                    streamer.switch_image_model(str(new_model_base))
                except Exception as exc:
                    print(f"[live.local] 切换形象失败: {exc}")
            else:
                print(f"[live.local] 形象目录不存在: {new_model_base}")

        if new_voice_id:
            self._primary_voice_id = str(new_voice_id)
            self.voice_infer_version = voice_infer_version
            try:
                self._ensure_voice_synthesizer(
                    self._primary_voice_id,
                    self.voice_infer_version,
                    force_refresh=True,
                )
                print(f"[live.local] 已切换音色: {self._primary_voice_id}")
            except Exception as exc:
                print(f"[live.local] 切换音色失败: {exc}")

        if payload.get("clear_queues") and streamer:
            try:
                streamer.clear_audio_queues()
            except Exception as exc:
                print(f"[live.local] 切换模型清队列失败: {exc}")
    def _handle_play_audio_index(self,payload):
        index = int(payload.get("index"))
        files = self._script_audio_files
        if index < 0 or index >= len(files):
            print(f"[live.local] play_audio_index 越界: {index}/{len(files)}")
            return
        streamer = self.host_streamer or self._runtime
        if not streamer:
            return
        audio_path = files[index]
        queue_name = str(payload.get("queue") or "normal")
        target_face_index = int(payload.get("target_face_index") or 0)
        try:
            streamer.add_audio_to_queue(
                audio_path,
                queue_name,
                target_face_index=target_face_index,
            )
        except Exception as exc:
            print(f"[live.local] play_audio_index 播放失败: {exc}")
    def _handle_product_image_popup(self,payload):
        from .product_image_popup import get_product_image_popup
        item=payload.get("product") or {}; popup=get_product_image_popup()
        popup.show_product(goods_id=int(item.get("goods_id") or item.get("goodsId") or payload.get("product_index",0)),
            item_pic=item.get("item_pic") or item.get("itemPic") or "",item_name=item.get("name") or item.get("title") or "")
    def _handle_taobao_product_popup(self,payload):
        controller=getattr(self,"_taobao_controller",None); item=payload.get("product") or {}
        goods_id=item.get("goods_id") or item.get("goodsId")
        if controller and goods_id is not None and hasattr(controller,"popup"): controller.popup(int(goods_id))

    def _prepare_product_image_popup(self, session):
        if not session.config.get("enable_product_image_sync"): return
        from .product_image_popup import get_product_image_popup
        popup=get_product_image_popup(); items=session.config.get("product_scripts") or []
        popup.preload_products(items,enable_cutout=bool(session.config.get("enable_product_image_cutout")),
            enable_jitter=bool(session.config.get("enable_product_image_jitter")),jitter_level=session.config.get("product_image_jitter_level",1))

    def _build_minimax_runtime_config(self,voice_general_config):
        selected=dict((voice_general_config or {}).get("minimax") or {})
        runtime_config=dict(self.config.get("minimax_voice_config") or {})
        voice_id=str(selected.get("minimax_voice_id") or "").strip()
        if voice_id: runtime_config["minimax_voice_id"]=voice_id
        return runtime_config

    def _build_cosyvoice_runtime_config(self,voice_general_config):
        selected=dict((voice_general_config or {}).get("cosyvoice") or {})
        runtime_config=dict(self.config.get("cosyvoice_voice_config") or {})
        voice_id=str(selected.get("cosyvoice_voice_id") or "").strip()
        if voice_id: runtime_config["cosyvoice_voice_id"]=voice_id
        return runtime_config
    def _ensure_near_clone_asr(self):
        if self._near_clone_asr_model is None:
            from .funasr_runtime import load_funasr_model
            self._near_clone_asr_model=load_funasr_model(self.config.get("asr_model_dir") or self.config.get("models_base_path","assets/pretrained_models"))
        return self._near_clone_asr_model
    def _prepare_taobao_control(self,session):
        if not session.config.get("enable_taobao_control"): return
        from .taobao_live_control import TaobaoLiveControl
        self._taobao_controller=TaobaoLiveControl(); self._taobao_controller._connect_configured(storage_state=self.config.get("taobao_storage_state"))
    def _prepare_platform_control(self,session):
        self._prepare_taobao_control(session); self._prepare_product_image_popup(session)
    def _sync_taobao_playing_product(self,session): session._sync_taobao_product_popup(session.current_product_index)
    def _local_session_loop(self):
        while True:
            session = self._session
            if session is None or session.stopped() or self._script_stop.wait(.05):
                return
            session.tick()

    def _audio_worker_loop(self):
        while not self._audio_worker_stop.is_set():
            task, queue_name = self._take_next_audio_task()
            if task is None or queue_name is None:
                continue
            try:
                self._execute_task_inline(task)
            except Exception as exc:
                print(f"[live.local] 音频任务执行异常: {exc}")
                traceback.print_exc()
            finally:
                self._adjust_pending_audio(queue_name, -1)
    def _start_audio_worker(self):
        if self._audio_worker and self._audio_worker.is_alive(): return
        self._audio_worker_stop.clear(); self._audio_worker=threading.Thread(target=self._audio_worker_loop,daemon=True); self._audio_worker.start()
    def _stop_audio_worker(self):
        self._audio_worker_stop.set()
        if self._audio_worker and self._audio_worker is not threading.current_thread(): self._audio_worker.join(2)
        self._audio_worker=None

    @staticmethod
    def _near_clone_asr_char_count(text): return len(re.sub(r"[\W_]+","",str(text or ""),flags=re.UNICODE))
    def _run_with_timeout(self, func, timeout, description):
        done = threading.Event()
        outcome = {}
        def runner():
            try:
                outcome["value"] = func()
            except BaseException as exc:
                outcome["error"] = exc
            finally:
                done.set()
        thread = threading.Thread(
            target=runner,
            daemon=True,
            name="tts-timeout-" + str(description)[:24],
        )
        thread.start()
        if not done.wait(float(timeout)):
            raise TimeoutError(f"{description}超时（{timeout}秒）")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")
    _run_local_synth_with_timeout = _run_with_timeout

    def _ensure_voice_synthesizer(self, voice_id, voice_infer_version, force_refresh=False):
        key=(voice_id,voice_infer_version)
        if force_refresh or self._voice_synth_key != key:
            if self._voice_synth: self._voice_synth.clear()
            from importlib import import_module
            from .local_voice import MODULES
            cls=import_module(MODULES[voice_infer_version]).VoiceSynthesizer
            self._voice_synth=cls.from_voice_dir(self.config.get("models_base_path","assets/pretrained_models"),
                self.config["voice_base_dir"],voice_id,self.config.get("device","cuda"),voice_infer_version)
            self._voice_synth_key=key
        return self._voice_synth

    def _ensure_near_clone_synth(self, reference_audio, reference_text):
        key=(str(reference_audio),str(reference_text))
        if self._near_clone_key != key:
            if self._near_clone_synth: self._near_clone_synth.clear()
            from .voice_infer import VoiceSynthesizer
            self._near_clone_synth=VoiceSynthesizer(self.config.get("models_base_path","assets/pretrained_models"),
                reference_audio,reference_text,self.config.get("device","cuda"),"near_clone","v1")
            self._near_clone_key=key
        return self._near_clone_synth

    def _clear_near_clone_runtime(self):
        if self._near_clone_synth: self._near_clone_synth.clear()
        self._near_clone_synth=None; self._near_clone_key=None; self._near_clone_asr_model=None

    def _resolve_near_clone_warmup_ref(self):
        params=getattr(self,"_local_params",{})
        base=params.get("voice_base") or params.get("voice_base_dir") or self.config.get("voice_base_dir")
        audio=params.get("reference_audio") or params.get("ref_audio")
        text=params.get("reference_text") or params.get("ref_text")
        if base:
            audio=audio or str(Path(base)/"ref_audio.wav")
            text_path=Path(base)/"ref_text.txt"
            if not text and text_path.is_file(): text=text_path.read_text(encoding="utf-8").strip()
        return (str(audio),str(text)) if audio and Path(audio).is_file() and text else None

    def _prepare_near_clone_reference(self):
        pair=self._resolve_near_clone_warmup_ref()
        if not pair and self._runtime and hasattr(self._runtime,"get_near_audio_clip"):
            clip=self._runtime.get_near_audio_clip()
            if isinstance(clip,dict):
                pair=(clip.get("audio_path") or clip.get("reference_audio"),clip.get("text") or clip.get("reference_text"))
            elif isinstance(clip,(tuple,list)) and len(clip)>=2: pair=(clip[0],clip[1])
        if not pair or not pair[0] or not pair[1] or self._near_clone_asr_char_count(pair[1]) < 2: return None
        return {"reference_audio":str(pair[0]),"reference_text":str(pair[1])}

    def _warmup_near_clone_runtime(self):
        reference=self._prepare_near_clone_reference()
        if reference: self._ensure_near_clone_synth(reference["reference_audio"],reference["reference_text"])

    def _synthesize_with_near_clone(self, *, synthesis_text, speed, language):
        reference=self._prepare_near_clone_reference()
        if not reference: return None
        synth=self._ensure_near_clone_synth(reference["reference_audio"],reference["reference_text"])
        return synth.synthesize(synthesis_text,speed=speed,language=language,use_cache=True)

    def _interruption_mic_feeder_loop(self, chunk_secs):
        stream=self._interruption_stream
        while stream and not self._interruption_stop.wait(0):
            try: data=stream.read(max(1,int(16000*chunk_secs)),exception_on_overflow=False)
            except Exception: break
            runtime=self._runtime
            if runtime and hasattr(runtime,"add_interruption_audio"): runtime.add_interruption_audio(data,16000)

    def _start_interruption_mic(self, input_device_index=None, chunk_secs=.2):
        if self._interruption_thread and self._interruption_thread.is_alive(): return True
        try:
            import pyaudio
            pa=pyaudio.PyAudio(); kwargs={"format":pyaudio.paInt16,"channels":1,"rate":16000,"input":True,"frames_per_buffer":max(1,int(16000*chunk_secs))}
            index=_normalize_input_device_index(input_device_index)
            if index is not None: kwargs["input_device_index"]=index
            self._interruption_stream=pa.open(**kwargs); self._interruption_audio=pa
            self._interruption_stop.clear(); self._interruption_thread=threading.Thread(target=self._interruption_mic_feeder_loop,args=(chunk_secs,),daemon=True); self._interruption_thread.start(); return True
        except Exception as error: self.last_error=str(error); return False

    def _stop_interruption_mic(self):
        self._interruption_stop.set()
        if self._interruption_thread and self._interruption_thread is not threading.current_thread(): self._interruption_thread.join(2)
        self._interruption_thread=None
        for obj in (getattr(self,"_interruption_stream",None),getattr(self,"_interruption_audio",None)):
            try: obj.close() if hasattr(obj,"close") else obj.terminate()
            except Exception: pass
        self._interruption_stream=None

    def start_live(self, *, local_params, config, llm_config=None,
                   minimax_voice_config=None, cosyvoice_voice_config=None):
        """Start the image runtime and its local interaction session atomically.

        The packaged LiveManager overrides the lower-level manager entry point:
        it copies provider settings, delegates runtime startup, then creates the
        LocalLiveBrain and its workers.  Keeping that ordering matters because a
        failed runtime must never leave an apparently live interaction session.
        """
        local_params = dict(local_params or {})
        session_config = dict(config or {})
        effective_llm_config = dict(llm_config or {})
        self.minimax_voice_config = dict(minimax_voice_config or {})
        self.cosyvoice_voice_config = dict(cosyvoice_voice_config or {})
        with self._local_session_lock:
            self.stop_local_session()
            runtime_ok = super().start_live(
                local_params=local_params,
                config=session_config,
                llm_config=effective_llm_config,
                minimax_voice_config=self.minimax_voice_config,
                cosyvoice_voice_config=self.cosyvoice_voice_config,
            )
            if not runtime_ok:
                return False
            try:
                self.host_streamer = self._runtime
                self._primary_voice_id = str(local_params.get("voice_id") or "").strip()
                self.voice_infer_version = str(local_params.get("voice_infer_version") or "v1")
                self.language = str(local_params.get("language") or "zh-CN")
                self.voice_speed = float(local_params.get("voice_speed", 1.1) or 1.1)
                self.use_audio_cache = bool(local_params.get("use_audio_cache", True))
                self.use_near_audio_clone = bool(local_params.get("use_near_audio_clone", False))
                self._start_audio_worker()
                session = LocalLiveBrain(
                    session_id=str(time.time_ns()), config=session_config,
                    llm_config=effective_llm_config, emit_task=self.execute_task,
                    queue_provider=self.get_queue_lengths,
                )
                self._session = session
                self._prepare_platform_control(session)
                self._local_session_stop_event.clear()
                self._local_session_thread = threading.Thread(
                    target=self._local_session_loop, name="local-live-session", daemon=True)
                self._local_session_thread.start()
                return True
            except Exception as error:
                self.last_error = str(error)
                self._session = None
                self.host_streamer = None
                self._stop_audio_worker()
                super().stop_live()
                return False

    def start_local_runtime(self, *, model_id, voice_id, voice_infer_version="v1", language="zh-CN",
                            voice_speed=1.1, image_output_mode="window", is_interrupt=False,
                            enable_action_generalization=False, input_mode="file", camera_index=-1,
                            camera_resolution="1280x720", video_path_for_driving="",
                            rtmp_url_for_driving="", enable_occluder=False, occluder_model_path="",
                            live_streamer_name="", use_audio_cache=True, script_input_mode="text",
                            script_audio_dir="", origin_idle_video_mode=False, use_near_audio_clone=False,
                            output_resolution="720p", window_width=None, window_height=None):
        params={
            "model_id":model_id,"voice_id":voice_id,"voice_infer_version":voice_infer_version,
            "language":language,"voice_speed":voice_speed,"image_output_mode":image_output_mode,
            "is_interrupt":is_interrupt,"enable_action_generalization":enable_action_generalization,
            "input_mode":input_mode,"camera_index":camera_index,"camera_resolution":camera_resolution,
            "video_path_for_driving":video_path_for_driving,"rtmp_url_for_driving":rtmp_url_for_driving,
            "enable_occluder":enable_occluder,"occluder_model_path":occluder_model_path,
            "live_streamer_name":live_streamer_name,"use_audio_cache":use_audio_cache,
            "script_input_mode":script_input_mode,"script_audio_dir":script_audio_dir,
            "origin_idle_video_mode":origin_idle_video_mode,"use_near_audio_clone":use_near_audio_clone,
            "output_resolution":output_resolution,"window_width":window_width,"window_height":window_height,
        }
        config=dict(self.config.get("interaction_config") or self.config)
        for key in ("voice_id", "voice_infer_version", "language", "voice_speed",
                    "use_audio_cache", "use_near_audio_clone", "script_input_mode",
                    "script_audio_dir", "live_streamer_name"):
            config.setdefault(key, params[key])
        local_params=dict(params); local_params.setdefault("script_input_mode",params.get("script_input_mode","text"))
        return self.start_live(
            local_params=local_params, config=config,
            llm_config=self.config.get("llm_config"),
            minimax_voice_config=self.config.get("minimax_voice_config"),
            cosyvoice_voice_config=self.config.get("cosyvoice_voice_config"),
        )
    def stop_local_session(self):
        self._local_session_stop_event.set()
        if self._session: self._session.mark_stopped(); self._session=None
        thread,self._local_session_thread=self._local_session_thread,None
        if thread and thread is not threading.current_thread(): thread.join(2)
        return True
    def stop_local_runtime(self):
        self.stop_local_session(); self._stop_interruption_mic(); self._stop_audio_worker(); self._clear_near_clone_runtime()
        if self._voice_synth: self._voice_synth.clear(); self._voice_synth=None
        result = self.stop_live()
        if result:
            self.host_streamer = None
        return result
    def set_interruption(self,is_paused,input_device_index=None):
        if self._runtime: (self._runtime.pause if is_paused else self._runtime.resume)()
        return self._runtime is not None
    def danmu_follows_live(self): return bool(self.config.get("danmu_follows_live",True))
    def prepare_multilingual_audio_cache(self, *, scripts, voice_id, assistant_voice_id=None, shift_schedule=None,
                                         multi_product_configs=None, language="zh-CN", voice_speed=1.1, voice_infer_version="v2"):
        try:
            primary_voice_id = str(voice_id or "").strip()
            if not primary_voice_id:
                print("[live.local] 多语种音频缓存准备失败: voice_id 为空")
                return False

            assistant_voice_id = str(assistant_voice_id or "").strip()
            jobs = []

            def add_script(script, host_voice_id, helper_voice_id="", job_language=None):
                script = str(script or "").strip()
                if not script:
                    return
                for item in slice_content(script):
                    item = item or {}
                    text = str(item.get("content") or "").strip()
                    if not text:
                        continue
                    target_voice_id = (
                        helper_voice_id if item.get("type") == "assistant" and helper_voice_id
                        else host_voice_id
                    )
                    if not target_voice_id:
                        continue
                    for candidate in self._expand_cache_text_candidates(text):
                        limited_text, _units, _truncated = _limit_tts_synthesis_text(candidate)
                        if limited_text:
                            jobs.append((limited_text, target_voice_id, job_language or language))

            add_script(scripts, primary_voice_id, assistant_voice_id)

            for shift in shift_schedule or []:
                shift = shift or {}
                shifted_voice_id = str(shift.get("voiceModelId") or primary_voice_id).strip()
                shift_script = shift.get("scripts") or shift.get("script") or shift.get("content") or ""
                add_script(shift_script, shifted_voice_id, assistant_voice_id, shift.get("language"))

            for product in multi_product_configs or []:
                product = product or {}
                product_voice_id = str(product.get("voiceModelId") or primary_voice_id).strip()
                product_scripts = product.get("scripts") or product.get("product_scripts") or product.get("content") or ""
                if isinstance(product_scripts, (list, tuple)):
                    for product_script in product_scripts:
                        if isinstance(product_script, dict):
                            product_script = product_script.get("content") or product_script.get("script") or ""
                        add_script(product_script, product_voice_id, assistant_voice_id, product.get("language"))
                else:
                    add_script(product_scripts, product_voice_id, assistant_voice_id, product.get("language"))

            unique_jobs = list(dict.fromkeys(jobs))
            print(f"[live.local] 多语种音频缓存检查开始，共 {len(unique_jobs)} 条")
            for text, target_voice_id, job_language in unique_jobs:
                synthesizer = self._ensure_voice_synthesizer(target_voice_id, voice_infer_version)
                if not synthesizer:
                    return False
                synthesizer.synthesize(text, voice_speed, language=job_language, use_cache=True)
            print("[live.local] 多语种音频缓存已准备")
            return True
        except Exception as error:
            self.last_error = str(error)
            print(f"[live.local] 多语种音频缓存准备失败: {error}")
            traceback.print_exc()
            return False
