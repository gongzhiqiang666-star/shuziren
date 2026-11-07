"""Recovered synthesized-audio metadata cache from ``tools.audio_cache``."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional


class AudioCacheStore:
    """Manage synthesized audio metadata records in a line-delimited index."""

    INDEX_FILE_NAME = "audio_cache_index.txt"
    _lock = threading.Lock()

    @classmethod
    def _index_path(cls, temp_dir: str) -> str:
        return os.path.join(os.path.abspath(temp_dir), cls.INDEX_FILE_NAME)

    @staticmethod
    def _file_signature(file_path: Optional[str]) -> Optional[Dict[str, Any]]:
        if not file_path:
            return None
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return None
        stat = os.stat(abs_path)
        return {
            "abs_path": abs_path,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }

    @classmethod
    def _build_payload(
        cls,
        voice_id: Optional[str],
        text: str,
        speed: float,
        voice_infer_version: Optional[str],
        language: Optional[str],
        reference_audio: Optional[str],
        reference_text: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "voice_id": (voice_id or "").strip(),
            "text": (text or "").strip(),
            "speed": round(float(speed), 4),
            "voice_infer_version": (voice_infer_version or "").strip(),
            "language": (language or "").strip(),
            "reference_audio": cls._file_signature(reference_audio),
            "reference_text": (reference_text or "").strip(),
        }

    @staticmethod
    def _cache_key(payload: Dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def find_cached_audio(
        cls,
        temp_dir: str,
        voice_id: Optional[str],
        text: str,
        speed: float,
        voice_infer_version: Optional[str],
        language: Optional[str] = None,
        reference_audio: Optional[str] = None,
        reference_text: Optional[str] = None,
    ) -> Optional[str]:
        payload = cls._build_payload(
            voice_id,
            text,
            speed,
            voice_infer_version,
            language,
            reference_audio,
            reference_text,
        )
        target_key = cls._cache_key(payload)
        index_path = cls._index_path(temp_dir)
        if not os.path.exists(index_path):
            return None

        with cls._lock:
            try:
                with open(index_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
            except OSError:
                return None

        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("cache_key") != target_key:
                continue
            audio_path = record.get("audio_path")
            if audio_path and os.path.exists(audio_path):
                return os.path.abspath(audio_path)
        return None

    @classmethod
    def append_record(
        cls,
        temp_dir: str,
        audio_path: str,
        voice_id: Optional[str],
        text: str,
        speed: float,
        voice_infer_version: Optional[str],
        language: Optional[str] = None,
        reference_audio: Optional[str] = None,
        reference_text: Optional[str] = None,
    ) -> None:
        os.makedirs(temp_dir, exist_ok=True)
        abs_audio_path = os.path.abspath(audio_path)
        payload = cls._build_payload(
            voice_id,
            text,
            speed,
            voice_infer_version,
            language,
            reference_audio,
            reference_text,
        )
        record = {
            "cache_key": cls._cache_key(payload),
            "payload": payload,
            "audio_path": abs_audio_path,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        index_path = cls._index_path(temp_dir)
        serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with cls._lock:
            with open(index_path, "a", encoding="utf-8") as file:
                file.write(serialized + "\n")

