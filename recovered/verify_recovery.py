"""Repeatable structural and dependency-light checks for the recovered tree."""
from __future__ import annotations

import asyncio
import argparse
import base64
import compileall
import contextlib
import gzip
import importlib
import inspect
import json
import hashlib
import os
import struct
import ast
import re
import subprocess
import sys
import threading
import time
import types
import tempfile
import wave
import yaml
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
ORIGINAL = WORKSPACE / "yunchuang_v122" / "_internal"


def resolve_runtime_internal(runtime_root):
    """Accept a distribution root or its _internal directory; never guess a fallback."""
    root = Path(runtime_root).expanduser().resolve()
    internal = root if root.name.casefold() == "_internal" else root / "_internal"
    if not internal.is_dir() or not (internal / "main.cp310-win_amd64.pyd").is_file():
        raise ValueError(f"Original v122 runtime is missing: {internal}")
    return internal


def first_party_extensions(runtime_internal=None):
    """Prune bundled environments and macOS resource forks on every host OS."""
    root = Path(runtime_internal) if runtime_internal is not None else ORIGINAL
    excluded = {"env", "env_50", "site-packages", "dlls"}
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names
                          if name.casefold() not in excluded and not name.startswith("._"))
        for name in sorted(files):
            if name.casefold().endswith(".pyd") and not name.startswith("._"):
                yield Path(directory) / name


def binary_strings(binary):
    """Read printable ASCII runs (minimum four bytes), without a Unix strings executable."""
    return "\n".join(match.decode("ascii") for match in
                     re.findall(rb"[\x09\x20-\x7e]{4,}", Path(binary).read_bytes()))


def verify_forbidden_word_replacement_contract():
    from recovered import replace_forbidden_words as module
    from recovered.forbidden_words import FORBIDDEN_WORDS

    assert len(FORBIDDEN_WORDS) == 147
    assert len({item["word"] for item in FORBIDDEN_WORDS}) == 146
    assert [item["word"] for item in FORBIDDEN_WORDS[:3]] == ["", "今天", "钱"]
    assert [item["word"] for item in FORBIDDEN_WORDS[-3:]] == [
        "行业第一",
        "全网第一",
        "全网",
    ]
    assert {
        item["word"]: item["replacements"]
        for item in FORBIDDEN_WORDS
        if item["replacements"]
    } == {
        "今天": ["今儿"],
        "原价": ["日常价"],
        "优秀": ["棒"],
        "块钱": ["块"],
        "囤": ["豚"],
        "周末": ["双休"],
        "扣个1": ["扣个一"],
        "扣1": ["扣一"],
    }

    assert module._SAFE_FROM_ZUI_REGEX == ("最近", "最终")
    assert module._remove_superlative_patterns("最近最终全网最低价史上最好") == "全网上"
    protected, slots = module._protect_phrases("最近和最终", module._SAFE_FROM_ZUI_REGEX)
    assert slots == ["最近", "最终"]
    assert module._restore_phrases(protected, slots) == "最近和最终"
    protected, slots = module._protect_phrases("最终", module._SAFE_FROM_ZUI_REGEX)
    assert slots == ["最终"]
    assert module._restore_phrases(protected, slots) == "最终"

    initialized = []
    added = []
    original_initialize = module.jieba.initialize
    original_add_word = module.jieba.add_word
    original_cut = module.jieba.cut
    original_words = module.FORBIDDEN_WORDS
    try:
        module.jieba.initialize = lambda: initialized.append(True)
        module.jieba.add_word = lambda word: added.append(word)
        module.jieba.cut = lambda text: iter((text,))
        module.FORBIDDEN_WORDS = []
        assert module.replace_forbidden_words(
            "禁，最，双词", ["禁", "最", "双词"]
        ) == "禁，*，**"
    finally:
        module.jieba.initialize = original_initialize
        module.jieba.add_word = original_add_word
        module.jieba.cut = original_cut
        module.FORBIDDEN_WORDS = original_words
    assert initialized == [True]
    assert added == ["禁", "最", "双词"]


def verify_audio_cache_contract():
    from recovered.audio_cache import AudioCacheStore

    with tempfile.TemporaryDirectory() as temp_dir:
        reference_path = Path(temp_dir) / "reference.wav"
        reference_path.write_bytes(b"reference")
        audio_path = Path(temp_dir) / "result.wav"
        audio_path.write_bytes(b"audio")
        payload = AudioCacheStore._build_payload(
            " voice ", " hello ", 1.23456, " v3 ", " zh-CN ",
            str(reference_path), " prompt ",
        )
        assert payload == {
            "voice_id": "voice", "text": "hello", "speed": 1.2346,
            "voice_infer_version": "v3", "language": "zh-CN",
            "reference_audio": {
                "abs_path": os.path.abspath(reference_path),
                "size": 9,
                "mtime_ns": reference_path.stat().st_mtime_ns,
            },
            "reference_text": "prompt",
        }
        native_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        compact_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert AudioCacheStore._cache_key(payload) == hashlib.sha256(native_json.encode("utf-8")).hexdigest()
        assert native_json != compact_json
        AudioCacheStore.append_record(
            temp_dir, str(audio_path), " voice ", " hello ", 1.23456,
            " v3 ", " zh-CN ", str(reference_path), " prompt ",
        )
        assert AudioCacheStore.find_cached_audio(
            temp_dir, " voice ", " hello ", 1.23456, " v3 ", " zh-CN ",
            str(reference_path), " prompt ",
        ) == os.path.abspath(audio_path)


def verify_audio_devices_contract():
    from recovered import audio_devices

    calls = []
    class FakePyAudio:
        def get_host_api_info_by_index(self, index):
            calls.append(("host", index))
            return {"deviceCount": 3}
        def get_device_info_by_host_api_device_index(self, host, index):
            calls.append(("device", host, index))
            return (
                {"index": 99, "name": "mic", "maxInputChannels": 1, "maxOutputChannels": 0},
                {"index": 98, "name": "speaker", "maxInputChannels": 0, "maxOutputChannels": 2},
                {"index": 97, "name": "duplex", "maxInputChannels": 1, "maxOutputChannels": 1},
            )[index]
        def terminate(self): calls.append(("terminate",))

    previous = sys.modules.get("pyaudio")
    sys.modules["pyaudio"] = types.SimpleNamespace(PyAudio=FakePyAudio)
    try:
        assert audio_devices.get_audio_devices() == {
            "input": [{"index": 99, "name": "mic"}, {"index": 97, "name": "duplex"}],
            "output": [{"index": 98, "name": "speaker"}, {"index": 97, "name": "duplex"}],
        }
    finally:
        if previous is None: sys.modules.pop("pyaudio", None)
        else: sys.modules["pyaudio"] = previous
    assert calls == [
        ("host", 0), ("device", 0, 0), ("device", 0, 1),
        ("device", 0, 2), ("terminate",),
    ]

    class BrokenPyAudio(FakePyAudio):
        def get_device_info_by_host_api_device_index(self, host, index):
            if index == 1: raise RuntimeError("portaudio failure")
            return {"name": "mic", "maxInputChannels": 1, "maxOutputChannels": 0}
    sys.modules["pyaudio"] = types.SimpleNamespace(PyAudio=BrokenPyAudio)
    output = types.SimpleNamespace(text="")
    sink = types.SimpleNamespace(
        write=lambda text: setattr(output, "text", output.text + text),
        flush=lambda: None,
    )
    try:
        with contextlib.redirect_stdout(sink):
            partial = audio_devices.get_audio_devices()
        assert partial == {"input": [{"index": 0, "name": "mic"}, {"index": 2, "name": "mic"}], "output": []}
        assert output.text == "枚举音频设备 1 失败: portaudio failure\n"
    finally:
        if previous is None: sys.modules.pop("pyaudio", None)
        else: sys.modules["pyaudio"] = previous


def verify_audio_player_scan_contract():
    from recovered import audio_player

    original_listdir = audio_player.os.listdir
    original_isfile = audio_player.os.path.isfile
    try:
        audio_player.os.listdir = lambda directory: [
            "z.WAV", "folder.mp3", "a.mp3", "voice.flac", "notes.txt", "b.wav"
        ]
        audio_player.os.path.isfile = lambda path: not path.endswith("folder.mp3")
        assert audio_player.scan_audio_files("audio-root") == [
            os.path.join("audio-root", "z.WAV"),
            os.path.join("audio-root", "a.mp3"),
            os.path.join("audio-root", "b.wav"),
        ]
    finally:
        audio_player.os.listdir = original_listdir
        audio_player.os.path.isfile = original_isfile

    try:
        audio_player.scan_audio_files("/definitely/missing/audio-player-directory")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("scan_audio_files must preserve os.listdir errors")

    backend_calls = []
    class PlayerBackend:
        def terminate(self): backend_calls.append("terminate")
    previous_pyaudio = sys.modules.get("pyaudio")
    sys.modules["pyaudio"] = types.SimpleNamespace(PyAudio=PlayerBackend)
    player = audio_player.AudioPlayer()
    try:
        marker = object()
        assert player.insert_audio(marker, "DaNmU") is None
        assert player.danmu_queue.get_nowait() is marker
        assert player.insert_audio("not-yet-created.wav", "other") is None
        assert player.normal_queue.get_nowait() == "not-yet-created.wav"
        thread_calls = []
        class FakeThread:
            def __init__(self, target):
                self.target = target; self.daemon = False; self.alive = False
            def start(self): self.alive = True; thread_calls.append("start")
            def is_alive(self): return self.alive
            def join(self, timeout=None): self.alive = False; thread_calls.append(("join", timeout))
        original_thread = audio_player.threading.Thread
        audio_player.threading.Thread = FakeThread
        output = types.SimpleNamespace(text="")
        sink = types.SimpleNamespace(
            write=lambda text: setattr(output, "text", output.text + text),
            flush=lambda: None,
        )
        try:
            with contextlib.redirect_stdout(sink):
                assert player.start() is True
                assert player.start() is False
                player.stop()
            assert player.play_thread.daemon is True
            assert thread_calls == ["start", ("join", 2)]
            assert output.text == "音频播放器已启动\n音频播放器已停止\n"
            assert backend_calls == []
            player.set_output_device(4)
            assert player.output_device_index == 4
            try: player.set_output_device("4")
            except ValueError: pass
            else: raise AssertionError("non-integer output device must fail")
        finally:
            audio_player.threading.Thread = original_thread

        player.stop_flag = False
        player.normal_queue.put("normal.wav")
        player.danmu_queue.put("danmu.wav")
        played = []
        def play_once(path):
            played.append(path)
            player.stop_flag = True
        player._play_audio_file = play_once
        player._play_audio_thread()
        assert played == ["danmu.wav"]

        player.stop_flag = False
        player.danmu_queue.get_nowait() if not player.danmu_queue.empty() else None
        player.normal_queue.get_nowait() if not player.normal_queue.empty() else None
        original_sleep = audio_player.time.sleep
        sleeps = []
        def stop_after_sleep(seconds):
            sleeps.append(seconds); player.stop_flag = True
        audio_player.time.sleep = stop_after_sleep
        try:
            player._play_audio_thread()
        finally:
            audio_player.time.sleep = original_sleep
        assert sleeps == [0.1]

        conversion_events = []
        original_join = audio_player.os.path.join
        original_dirname = audio_player.os.path.dirname
        original_makedirs = audio_player.os.makedirs
        original_run = audio_player.subprocess.run
        original_uuid4 = audio_player.uuid4
        original_os_name = audio_player.os.name
        audio_player.os.path.dirname = lambda path: (
            "/app/internal" if path == "/app/internal/tools" else "/app/internal/tools"
        )
        audio_player.os.path.join = lambda *parts: "/".join(parts)
        audio_player.os.makedirs = lambda path, **kwargs: conversion_events.append(
            ("makedirs", path, kwargs))
        audio_player.uuid4 = lambda: "fixed-uuid"
        audio_player.subprocess.run = lambda command, **kwargs: conversion_events.append(
            ("run", command, kwargs))
        audio_player.os.name = "posix"
        try:
            converted = audio_player.AudioPlayer._convert_audio_with_ffmpeg(player, "voice.mp3")
        finally:
            audio_player.os.path.join = original_join
            audio_player.os.path.dirname = original_dirname
            audio_player.os.makedirs = original_makedirs
            audio_player.subprocess.run = original_run
            audio_player.uuid4 = original_uuid4
            audio_player.os.name = original_os_name
        target = "/app/internal/../temp/converted_audio_for_player"
        output_path = target + "/fixed-uuid.wav"
        assert converted == output_path
        assert conversion_events == [
            ("makedirs", target, {"exist_ok":True}),
            ("run", ["ffmpeg", "-i", "voice.mp3", "-ar", "44100", "-ac", "2",
                     "-acodec", "pcm_s16le", "-y", "-hide_banner", "-loglevel", "error",
                     output_path], {"check":True, "startupinfo":None}),
        ]

        missing_outputs = []
        player._ffmpeg_error_printed = False
        audio_player.os.makedirs = lambda *_args, **_kwargs: None
        audio_player.uuid4 = lambda: "missing"
        audio_player.subprocess.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileNotFoundError("ffmpeg"))
        try:
            with contextlib.redirect_stdout(types.SimpleNamespace(
                    write=lambda text: missing_outputs.append(text), flush=lambda: None)):
                assert audio_player.AudioPlayer._convert_audio_with_ffmpeg(player, "bad.mp3") is None
                assert audio_player.AudioPlayer._convert_audio_with_ffmpeg(player, "bad.mp3") is None
        finally:
            audio_player.os.makedirs = original_makedirs
            audio_player.subprocess.run = original_run
            audio_player.uuid4 = original_uuid4
        missing_text = "".join(missing_outputs)
        assert missing_text.count("严重错误: `ffmpeg` 命令未找到") == 1
        assert player._ffmpeg_error_printed is True

        playback_events = []
        class FakeChunk:
            def __init__(self, data): self._data = data
        class FakeSound:
            sample_width = 2
            def set_channels(self, channels):
                playback_events.append(("channels", channels)); return self
            def set_frame_rate(self, rate):
                playback_events.append(("rate", rate)); return self
        class FakeStream:
            def __init__(self): self.stopped = False
            def is_stopped(self): return self.stopped
            def write(self, data): playback_events.append(("write", data))
            def stop_stream(self): self.stopped = True; playback_events.append("stop_stream")
            def close(self): playback_events.append("close")
        stream = FakeStream()
        player.player = types.SimpleNamespace(
            get_format_from_width=lambda width: playback_events.append(("width", width)) or "fmt",
            open=lambda **kwargs: playback_events.append(("open", kwargs)) or stream,
            terminate=lambda: backend_calls.append("terminate"),
        )
        previous_pydub = sys.modules.get("pydub")
        previous_pydub_utils = sys.modules.get("pydub.utils")
        sys.modules["pydub"] = types.SimpleNamespace(
            AudioSegment=types.SimpleNamespace(
                from_wav=lambda path: playback_events.append(("from_wav", path)) or FakeSound()))
        sys.modules["pydub.utils"] = types.SimpleNamespace(
            make_chunks=lambda sound, size: playback_events.append(("chunks", sound, size)) or
                [FakeChunk(b"one"), FakeChunk(b"two")])
        original_exists = audio_player.os.path.exists
        original_remove = audio_player.os.remove
        player._convert_audio_with_ffmpeg = lambda path: "/tmp/native-converted.wav"
        audio_player.os.path.exists = lambda path: path == "/tmp/native-converted.wav"
        audio_player.os.remove = lambda path: playback_events.append(("remove", path))
        player.stop_flag = False
        try:
            assert audio_player.AudioPlayer._play_audio_file(player, "input.mp3") is None
        finally:
            audio_player.os.path.exists = original_exists
            audio_player.os.remove = original_remove
            if previous_pydub is None: sys.modules.pop("pydub", None)
            else: sys.modules["pydub"] = previous_pydub
            if previous_pydub_utils is None: sys.modules.pop("pydub.utils", None)
            else: sys.modules["pydub.utils"] = previous_pydub_utils
        assert len(playback_events) >= 4, playback_events
        chunk_sound = playback_events[3][1]
        assert playback_events == [
            ("from_wav", "/tmp/native-converted.wav"), ("channels", 2), ("rate", 44100),
            ("chunks", chunk_sound, 1024), ("width", 2),
            ("open", {"format":"fmt", "channels":2, "rate":44100, "output":True,
                      "output_device_index":4}),
            ("write", b"one"), ("write", b"two"), "stop_stream", "close",
            ("remove", "/tmp/native-converted.wav"),
        ]

        player.stop_flag = False
        player.danmu_queue.put("bad.wav")
        player._play_audio_file = lambda _path: (_ for _ in ()).throw(RuntimeError("decode failed"))
        try:
            player._play_audio_thread()
        except RuntimeError as error:
            assert str(error) == "decode failed"
        else:
            raise AssertionError("player thread must preserve playback exceptions")
    finally:
        with contextlib.redirect_stdout(types.SimpleNamespace(write=lambda _text: None, flush=lambda: None)):
            player.close(); player.close()
        if previous_pyaudio is None: sys.modules.pop("pyaudio", None)
        else: sys.modules["pyaudio"] = previous_pyaudio
    assert backend_calls == ["terminate"]


def verify_edit_audio_contract():
    import hashlib
    import wave
    import recovered.edit_audio as edit_audio
    from recovered.edit_audio import AudioEditorAPI, EDIT_AUDIO_HTML

    assert len(EDIT_AUDIO_HTML.encode("utf-8")) == 12028
    assert hashlib.sha256(EDIT_AUDIO_HTML.encode("utf-8")).hexdigest() == (
        "4d5e47cecbcccb6778c29d82333871fd335eb51040dc98e24d4f2a6a2aec286f"
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        api = AudioEditorAPI.__new__(AudioEditorAPI)
        api.current_folder = ""
        api.items = []
        api.synthesizer = None
        api.config = dict(items_per_page=50, last_folder="")
        api.config_path = root / "config.yaml"
        api.runtime_dir = root

        try:
            api._load_folder(root)
        except ValueError as error:
            assert str(error) == "文件夹中没有 wav 文件"
        else:
            raise AssertionError("empty edit-audio folder must fail")

        (root / "10.wav").write_bytes(b"RIFF")
        try:
            api._load_folder(root)
        except ValueError as error:
            assert str(error) == (
                "找到 1 个 wav，但缺少同名 txt，无法加载。"
                "请先用「AI碎片化音频处理」生成带文本的切片。"
            )
        else:
            raise AssertionError("wav without matching txt must fail")

        (root / "10.txt").write_text("苹果苹果", encoding="utf-8")
        try:
            api._load_folder(root)
        except ValueError as error:
            assert "10.wav 不是有效的 WAV" in str(error)
        else:
            raise AssertionError("damaged wav must fail before entering editor")
        def write_wav(path, frames=160):
            with wave.open(str(path), "wb") as target:
                target.setnchannels(1); target.setsampwidth(2); target.setframerate(16000)
                target.writeframes(bytes(frames * 2))
        write_wav(root / "10.wav")
        write_wav(root / "2.WAV")
        (root / "2.txt").write_text("苹果", encoding="utf-8")
        assert api._load_folder(root) == str(root.resolve())
        assert list(api.items) == ["2", "10"]
        assert api.get_audio_base64("2")["audio_data"].startswith("data:audio/wav;base64,")
        assert api.get_audio_base64("missing")["message"] == "目标音频不存在"
        original_preview_limit = api.MAX_PREVIEW_BYTES
        api.MAX_PREVIEW_BYTES = 1
        assert api.get_audio_base64("2")["message"] == "音频超过 64 MiB 预览上限"
        api.MAX_PREVIEW_BYTES = original_preview_limit
        result = api.apply_keyword_replace("苹果", "香蕉", api._serialize_items())
        assert result["replaced_count"] == 2
        assert result["message"] == "替换完成，共处理 2 条"
        assert (root / "10.txt").read_text(encoding="utf-8") == "香蕉香蕉"

        synthesis_calls = []
        generated = root / "generated.wav"
        write_wav(generated, 320)
        generated_bytes = generated.read_bytes()
        class Synthesizer:
            def synthesize(self, **kwargs):
                synthesis_calls.append(kwargs)
                return str(generated)
        api._ensure_synthesizer = lambda sample_audio, sample_text: (
            synthesis_calls.append((sample_audio, sample_text)) or Synthesizer()
        )
        converted = api.convert_item("2", "新文本")
        assert converted["success"] is True and converted["message"] == "转化完成"
        resolved_root = Path(api.current_folder)
        assert synthesis_calls == [
            (str(resolved_root / "2.wav"), "香蕉"),
            {"text":"新文本", "speed":1.0, "reference_audio":str(resolved_root / "2.wav"),
             "reference_text":"香蕉"},
        ]
        assert (root / "2.wav").read_bytes() == generated_bytes
        assert (root / "2.txt").read_text(encoding="utf-8") == "新文本"
        rollback_audio = (root / "2.wav").read_bytes()
        rollback_text = (root / "2.txt").read_text(encoding="utf-8")
        generated_failure = root / "generated-failure.wav"
        write_wav(generated_failure, 480)
        api._ensure_synthesizer = lambda *_args: types.SimpleNamespace(
            synthesize=lambda **_kwargs: str(generated_failure))
        original_replace = edit_audio.os.replace
        replace_calls = []
        def fail_second_replace(source, target):
            replace_calls.append((str(source), str(target)))
            if len(replace_calls) == 2:
                raise OSError("txt replace failed")
            return original_replace(source, target)
        edit_audio.os.replace = fail_second_replace
        try:
            rolled_back = api.convert_item("2", "失败文本")
        finally:
            edit_audio.os.replace = original_replace
        assert rolled_back["success"] is False and "txt replace failed" in rolled_back["message"]
        assert (root / "2.wav").read_bytes() == rollback_audio
        assert (root / "2.txt").read_text(encoding="utf-8") == rollback_text
        assert api.items["2"]["original_text"] == "新文本"
        api.items["2"]["current_text"] = "新文本"
        assert api.convert_item("missing", "x")["message"] == "目标音频不存在"
        unchanged = api.convert_all(api._serialize_items())
        assert unchanged["success"] is False
        assert unchanged["message"] == "没有检测到修改过的文本"

    lifecycle = []
    class ClosedEvent:
        def __init__(self): self.callback = None
        def __iadd__(self, callback): self.callback = callback; return self
    closed = ClosedEvent()
    window = types.SimpleNamespace(events=types.SimpleNamespace(closed=closed))
    fake_webview = types.SimpleNamespace(
        create_window=lambda *args, **kwargs: lifecycle.append(("window", args, kwargs)) or window,
        start=lambda **kwargs: lifecycle.append(("start", kwargs)),
    )
    fake_api = types.SimpleNamespace(shutdown=lambda: lifecycle.append(("shutdown",)))
    previous_webview = sys.modules.get("webview")
    original_api_class = edit_audio.AudioEditorAPI
    original_exit = edit_audio.os._exit
    sys.modules["webview"] = fake_webview
    edit_audio.AudioEditorAPI = lambda: fake_api
    edit_audio.os._exit = lambda code: lifecycle.append(("exit", code))
    try:
        assert edit_audio.main() is None
        closed.callback()
    finally:
        edit_audio.AudioEditorAPI = original_api_class
        edit_audio.os._exit = original_exit
        if previous_webview is None: sys.modules.pop("webview", None)
        else: sys.modules["webview"] = previous_webview
    assert lifecycle == [
        ("window", ("碎片化音频编辑",), {
            "html":EDIT_AUDIO_HTML, "js_api":fake_api, "width":1400, "height":860,
            "min_size":(1100,720), "resizable":True, "text_select":True,
        }),
        ("start", {"debug":False, "private_mode":False}),
        ("shutdown",), ("exit", 0),
    ]


def verify_cloud_avatar_prompt_contract():
    from recovered.cloud_dh_prompts import (
        DEFAULT_HALFBODY_GREENSCREEN_PROMPT, build_avatar_prompt,
    )
    assert DEFAULT_HALFBODY_GREENSCREEN_PROMPT.startswith(
        "一张适合口播直播的数字人主播照片。年轻中国女性")
    assert DEFAULT_HALFBODY_GREENSCREEN_PROMPT.endswith("面部清晰，照片级写实。")
    assert build_avatar_prompt() == DEFAULT_HALFBODY_GREENSCREEN_PROMPT
    assert build_avatar_prompt("  ") == DEFAULT_HALFBODY_GREENSCREEN_PROMPT
    assert build_avatar_prompt("  长发\n蓝色西装  ") == (
        DEFAULT_HALFBODY_GREENSCREEN_PROMPT + "人物外观补充要求：长发\n蓝色西装。"
    )


def verify_live_sticker_title_routing_contract():
    from recovered import live_sticker_titles as module

    assert module.ARK_TITLE_MODEL == "doubao-seed-1-6-flash-250828"
    original_base_chat, original_chat_ark = module.base_chat, module._chat_ark
    try:
        calls = []
        module.base_chat = lambda *args, **kwargs: calls.append("llm") or "本地标题"
        module._chat_ark = lambda *args, **kwargs: calls.append("ark") or "回退标题"
        result = module.generate_room_titles({"name": "商品"}, ark_api_key="key")
        assert result == {"room_titles": ["本地标题"], "room_title": "本地标题",
                          "title_model": "llm_config"}
        assert calls == ["llm"]

        calls.clear()
        def fail_llm(*args, **kwargs):
            calls.append("llm")
            raise RuntimeError("LLM unavailable")
        module.base_chat = fail_llm
        result = module.generate_room_titles({"name": "商品"}, ark_api_key="key")
        assert result == {"room_titles": ["回退标题"], "room_title": "回退标题",
                          "title_model": "ark: doubao-seed-1-6-flash-250828"}
        assert calls == ["llm", "ark"]
    finally:
        module.base_chat, module._chat_ark = original_base_chat, original_chat_ark

    class Response:
        status_code = 200
        text = "ok"
        def json(self):
            return {"choices": [{"message": {"content": "  标题一  "}}]}

    original_post = module.requests.post
    captured = {}
    try:
        def post(url, **kwargs):
            captured.update({"url": url, **kwargs})
            return Response()
        module.requests.post = post
        assert module._chat_ark("  secret  ", {"name": "商品"}) == "标题一"
        assert captured["url"] == module.ARK_CHAT_URL and captured["timeout"] == 120
        assert captured["headers"] == {
            "Authorization": "Bearer secret", "Content-Type": "application/json"
        }
        assert captured["json"]["model"] == module.ARK_TITLE_MODEL
        assert captured["json"]["temperature"] == 0.7
        assert captured["json"]["thinking"] == {"type": "disabled"}
        assert [item["role"] for item in captured["json"]["messages"]] == ["system", "user"]
        try:
            module._chat_ark("", {})
        except ValueError as error:
            assert str(error) == "缺少火山引擎 API Key，无法生成直播间标题"
        else:
            raise AssertionError("empty Ark key must fail")

        Response.status_code, Response.text = 503, "down"
        try:
            module._chat_ark("key", {})
        except RuntimeError as error:
            assert str(error) == "Ark 标题生成失败 HTTP 503: down"
        else:
            raise AssertionError("non-200 Ark response must fail")
    finally:
        module.requests.post = original_post


def verify_live_sticker_prompt_contract():
    from recovered import live_sticker_prompts as prompts

    product = {"product_name":"轻薄羽绒服","product_selling_points":"保暖轻便",
               "product_price":"299","product_content":"冬季通勤"}
    assert prompts.build_product_brief(product) == (
        "商品名称：轻薄羽绒服\n卖点：保暖轻便\n价格：299\n补充信息：冬季通勤")
    assert prompts.build_product_brief({}) == "未提供商品信息"
    assert prompts.build_room_title_user_prompt(product).startswith("商品信息：\n商品名称：")
    assert "恰好 3 条中文标题" in prompts.ROOM_TITLE_SYSTEM_PROMPT
    vibe = "轻薄羽绒服，保暖轻便，冬季通勤"
    assert prompts.build_product_vibe(product) == vibe
    assert prompts.build_background_prompt(product) == prompts.BACKGROUND_PREFIX + vibe + prompts.BACKGROUND_SUFFIX
    assert prompts.build_foreground_prompt(product) == prompts.FOREGROUND_PREFIX + vibe + prompts.FOREGROUND_SUFFIX
    assert prompts.build_cover_prompt(product) == prompts.COVER_PREFIX + vibe + prompts.COVER_SUFFIX
    noisy = {"itemName":"【官方正品】 超长商品名称测试一二三四五六七八九十甲乙丙丁戊己庚辛壬癸！",
             "product_selling_points":"券后价轻便，保暖/包邮；多余", "content":"支持花呗 冬季通勤～"}
    assert prompts.build_product_vibe(noisy) == (
        "官方 超长商品名称测试一二三四五六七八九十甲乙丙丁戊己庚，轻便、保暖，冬季通勤")
    assert prompts._clip("abc，def", 4) == "abc"
    assert prompts.build_product_vibe({}) == ""
    try: prompts.parse_room_titles("")
    except ValueError as error: assert str(error) == "标题解析结果为空"
    else: raise AssertionError("empty title result must fail")


def recovered_path(extension):
    relative = extension.relative_to(ORIGINAL)
    stem = relative.name.split(".cp310-win_amd64", 1)[0]
    if stem.endswith(".pyd"):
        stem = stem[:-4]
    return HERE / relative.parent / f"{stem}.py"


def verify_mapping():
    extensions = list(first_party_extensions())
    missing = [recovered_path(path) for path in extensions if not recovered_path(path).is_file()]
    assert len(extensions) == 128, f"unexpected first-party extension count: {len(extensions)}"
    assert not missing, "missing recovered modules:\n" + "\n".join(map(str, missing))


def verify_all_modules_importable():
    failures = {}
    for extension in first_party_extensions():
        relative = extension.relative_to(ORIGINAL)
        stem = relative.name.split(".cp310-win_amd64", 1)[0]
        if stem.endswith(".pyd"): stem = stem[:-4]
        module_name = ".".join(("recovered", *relative.parent.parts, stem))
        try: importlib.import_module(module_name)
        except BaseException as error: failures[module_name] = f"{type(error).__name__}: {error}"
    assert not failures, f"recovered modules failed to import: {failures}"


async def verify_live_protocols():
    from assets.ws_danmu_capture.pdd.pinduoduo_danmu import PinduoduoDanmu
    from assets.ws_danmu_capture.pdd.pinduoduo_pb2 import Body, Command
    from assets.ws_danmu_capture.tb.taobao_danmu import TaobaoDanmu
    for cls, value in ((Command, Command(command="push", body=b"[]", downstreamSeq=2**40)),
                       (Body, Body(bizType=3, groupId="g", needAck=True))):
        decoded = cls.FromString(value.SerializeToString())
        assert all(getattr(decoded, name) == getattr(value, name) for name in cls.FIELD_NAMES)
    received = []
    async def capture(message): received.append(message)
    pdd = PinduoduoDanmu(); pdd.broadcast = capture
    messages = [{"message_type": "live_chat", "message_data": {"live_chat_list": [
        {"nickname": "测试用户", "chat_message": "测试弹幕"}]}}]
    packet = gzip.compress(Command(command="push", body=json.dumps(messages, ensure_ascii=False).encode()).SerializeToString())
    await pdd.on_frame_received(b"\0" * 12 + struct.pack(">I", len(packet)) + packet)
    assert received.pop() == {"type": "弹幕", "nickname": "测试用户", "content": "测试弹幕"}
    tb = TaobaoDanmu(); tb.broadcast = capture
    response = {"data": {"comments": [{"content": "欢迎", "timestamp": "1000", "publisherNick": "主播"}]}}
    await tb.parse_danmu_data("mtopjsonp1(" + json.dumps(response, ensure_ascii=False) + ")")
    assert received.pop() == {"type": "弹幕", "nickname": "主播", "content": "欢迎"}
    from recovered.kuaishou_v2.protocol import _encode_frame, decode_frame, proto
    enter=proto.CSWebEnterRoom(liveStreamId="stream",token="token",pageId="page")
    enter_roundtrip=proto.CSWebEnterRoom.FromString(enter.SerializeToString())
    assert (enter_roundtrip.liveStreamId,enter_roundtrip.token,enter_roundtrip.pageId)==("stream","token","page")
    user=proto.SimpleUserInfo(principalId="u",userName="用户")
    feed=proto.SCWebFeedPush(commentFeeds=[proto.WebCommentFeed(user=user,content="快手弹幕")])
    kind,decoded=decode_frame(_encode_frame(proto.SC_FEED_PUSH,feed))
    assert kind==proto.SC_FEED_PUSH and decoded.commentFeeds[0].content=="快手弹幕"


def verify_voice_helpers():
    from recovered.voice_infer_common import atempo_filters
    from recovered.voice_infer_v2 import VoiceSynthesizer,detect_language, normalize_omnivoice_language
    assert atempo_filters(4) == ["atempo=2", "atempo=2"]
    assert atempo_filters(.25) == ["atempo=0.5", "atempo=0.5"]
    assert detect_language("你好") == "Chinese"
    assert normalize_omnivoice_language("zh") == "Chinese"
    aliases={"zh-CN":"Chinese","zh-Hant":"Chinese","zh-TW":"Chinese",
             "en-US":"English","en-GB":"English","en-AU":"English",
             "ja-JP":"Japanese","ko-KR":"Korean","my-MM":"my-mm"}
    for source,target in aliases.items():assert normalize_omnivoice_language(source)==target
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);default_audio=base/"default.wav";override_audio=base/"override.wav"
        default_audio.write_bytes(b"RIFF");override_audio.write_bytes(b"RIFF")
        model_dir=base/"pretrained_models"/"OmniVoice";model_dir.mkdir(parents=True)
        (model_dir/"pytorch_model.bin").write_bytes(b"weights")
        fake_model=types.SimpleNamespace(sampling_rate=24000)
        fake_omni=types.SimpleNamespace(from_pretrained=lambda *_args,**_kwargs:fake_model)
        module_name="bin.voice_infer_v2.omnivoice.models.omnivoice"
        original_omni=sys.modules.get(module_name);original_torch=sys.modules.get("torch")
        sys.modules[module_name]=types.SimpleNamespace(OmniVoice=fake_omni)
        sys.modules["torch"]=types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda:False),float16=object(),float32=object())
        try:synthesizer=VoiceSynthesizer(base,default_audio,"默认文本",voice_id="voice-v2",device="cpu")
        finally:
            if original_omni is None:sys.modules.pop(module_name,None)
            else:sys.modules[module_name]=original_omni
            if original_torch is None:sys.modules.pop("torch",None)
            else:sys.modules["torch"]=original_torch
        cache_calls=[]
        synthesizer._cached=lambda *args:cache_calls.append(args) or "cached.wav"
        assert synthesizer.synthesize(
            "测试",reference_audio=str(override_audio),reference_text="  临时文本  ",
            language="zh-CN",use_cache=True)=="cached.wav"
        assert synthesizer.reference_audio==str(default_audio)
        assert synthesizer.reference_text=="默认文本"
        assert cache_calls==[("测试",1.0,"Chinese",True,str(override_audio),"临时文本")]
        synthesizer._cached=lambda *_args:None
        synthesizer._get_voice_clone_prompt=lambda *_args:"prompt"
        synthesizer._load_model=lambda:types.SimpleNamespace(generate=lambda **_kwargs:[])
        fake_torchaudio=types.SimpleNamespace(save=lambda *_args,**_kwargs:None)
        original_torchaudio=sys.modules.get("torchaudio")
        sys.modules["torchaudio"]=fake_torchaudio
        try:
            assert synthesizer.synthesize("空结果",language="zh-CN") is None
        finally:
            if original_torchaudio is None:sys.modules.pop("torchaudio",None)
            else:sys.modules["torchaudio"]=original_torchaudio

def verify_asr_temp_audio_lifecycle():
    import recovered.asr_main as asr
    with tempfile.TemporaryDirectory() as directory:
        source=Path(directory)/"sample.mp4";source.write_bytes(b"video")
        converted_paths=[];cleaned=[]
        originals=(asr.subprocess.run,asr.load_whisper_model,asr.transcribe_with_whisper,
                   asr.whisper_result_to_text,asr.cleanup_whisper_model)
        def convert(command,**_kwargs):
            converted_paths.append(Path(command[-1]));Path(command[-1]).write_bytes(b"RIFF")
            return types.SimpleNamespace(returncode=0)
        try:
            asr.subprocess.run=convert;asr.load_whisper_model=lambda _path:"model"
            asr.transcribe_with_whisper=lambda *_args,**_kwargs:{"text":"识别结果"}
            asr.whisper_result_to_text=lambda result:result["text"]
            asr.cleanup_whisper_model=lambda model:cleaned.append(model)
            result=asr.recognize_audio(source,Path(directory)/"weights")
            assert result=={"text":"识别结果","output_path":str(source.with_suffix('.txt'))}
            assert source.with_suffix('.txt').read_text(encoding="utf-8")=="识别结果"
            assert converted_paths[0].parent!=source.parent and not converted_paths[0].exists()
            assert cleaned==["model"]
            asr.transcribe_with_whisper=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError("asr failed"))
            try:asr.recognize_audio(source,Path(directory)/"weights")
            except RuntimeError as error:assert str(error)=="asr failed"
            else:raise AssertionError("ASR failure must propagate")
            assert source.with_suffix('.txt').read_text(encoding="utf-8")=="识别结果"
            assert not converted_paths[1].exists() and cleaned==["model","model"]
            assert not list(source.parent.glob(".*.pending"))
        finally:
            (asr.subprocess.run,asr.load_whisper_model,asr.transcribe_with_whisper,
             asr.whisper_result_to_text,asr.cleanup_whisper_model)=originals

def verify_audio_duration_fallbacks():
    import recovered.audio_duration as duration
    with tempfile.TemporaryDirectory() as directory:
        media=Path(directory)/"sample.mp3";media.write_bytes(b"audio")
        original_find=duration._find_ffprobe;original_run=duration.subprocess.run
        original_librosa=sys.modules.get("librosa")
        fake=types.SimpleNamespace(get_duration=lambda *,path:3.25 if path==str(media) else -1)
        try:
            duration._find_ffprobe=lambda:None;sys.modules["librosa"]=fake
            assert duration.get_audio_duration(str(media))==3.25
            calls=[]
            duration._find_ffprobe=lambda:"probe.exe"
            duration.subprocess.run=lambda *args,**kwargs: calls.append((args,kwargs)) or types.SimpleNamespace(stdout="4.75\n")
            assert duration.get_audio_duration(str(media))==4.75
            assert calls==[(([
                "probe.exe","-v","error","-show_entries","format=duration","-of",
                "default=noprint_wrappers=1:nokey=1",str(media)
            ],),{"capture_output":True,"text":True,"check":True})]
            try:duration.get_audio_duration(str(Path(directory)/"missing.wav"))
            except FileNotFoundError as error:assert str(error).endswith("音频不存在: "+str(Path(directory)/"missing.wav"))
            else:raise AssertionError("missing audio must fail")
        finally:
            duration._find_ffprobe=original_find;duration.subprocess.run=original_run
            if original_librosa is None:sys.modules.pop("librosa",None)
            else:sys.modules["librosa"]=original_librosa
        bundled=Path(directory)/"_internal"/"env"/"ffmpeg"/"bin"/"ffprobe.exe"
        bundled.parent.mkdir(parents=True);bundled.write_bytes(b"exe")
        original_file=duration.__file__;original_run=duration.subprocess.run
        try:
            duration.__file__=str(Path(directory)/"_internal"/"tools"/"cloud_dh"/"audio_duration.py")
            probe_calls=[]
            duration.subprocess.run=lambda *args,**kwargs: probe_calls.append((args,kwargs)) or types.SimpleNamespace()
            assert duration._find_ffprobe()==str(bundled)
            assert probe_calls==[(( [str(bundled),"-version"], ),{"capture_output":True,"check":True})]
        finally:
            duration.__file__=original_file;duration.subprocess.run=original_run

def verify_output_resolution_contract():
    import recovered.output_resolution as resolution
    assert resolution.DEFAULT_RESOLUTION=="720p"
    assert resolution.PORTRAIT_RESOLUTION_MAP=={
        "480p":(480,854),"720p":(720,1280),"1080p":(1080,1920),
        "2k":(1440,2560),"4k":(2160,3840),
    }
    assert resolution.RESOLUTION_RANK=={"480p":0,"720p":1,"1080p":2,"2k":3,"4k":4}
    assert resolution.normalize_resolution_key(" 1080P ")=="1080p"
    assert resolution.normalize_resolution_key("bad")=="720p"
    assert resolution.normalize_resolution_key("bad",None) is None
    assert resolution.resolve_portrait_size("480P")== (480,854)
    assert resolution.resolution_rank("480p")==0 and resolution.resolution_rank("4K")==4
    assert resolution.resolve_portrait_size("2K")== (1440,2560)
    assert resolution.normalize_target_height("720p",False)==1280
    assert resolution.normalize_target_height("720p",True)==720
    assert resolution.clamp_output_to_source("720p","1080p")== ("720p",None)
    assert resolution.clamp_output_to_source("1080p","unknown")== ("1080p",None)
    assert resolution.clamp_output_to_source("4k","2k")[0]=="2k"
    downgraded,message=resolution.clamp_output_to_source("1080p","480p")
    assert downgraded=="480p" and message==(
        "输出清晰度 1080p 高于形象素材 480p，已按素材清晰度输出，避免放大发糊；"
        "若要 1080p 请重新按该清晰度克隆形象"
    )
    calls=[];original_run=resolution.subprocess.run
    try:
        resolution.subprocess.run=lambda *args,**kwargs:(
            calls.append((args,kwargs)) or types.SimpleNamespace(stdout="  NVIDIA RTX 4090  \n\nRTX 3060\n")
        )
        assert resolution.detect_primary_gpu_name()=="NVIDIA RTX 4090"
        args,kwargs=calls[0]
        assert args==(["nvidia-smi","--query-gpu=gpu_name","--format=csv,noheader"],)
        assert kwargs["capture_output"] is kwargs["text"] is kwargs["check"] is True
        resolution.subprocess.run=lambda *_args,**_kwargs:(_ for _ in ()).throw(ValueError("bad output"))
        assert resolution.detect_primary_gpu_name()==""
    finally:resolution.subprocess.run=original_run

def verify_customer_pack_contract():
    import recovered.tools.customer_pack as customer
    assert isinstance(customer._client_base_dir(),str)
    assert Path(customer._client_base_dir())==HERE
    assert customer.read_admin_id()==62 and customer.is_vietnam_customer_pack() is False
    original_file=customer.__file__;had_frozen=hasattr(customer.sys,"frozen")
    original_frozen=getattr(customer.sys,"frozen",None);original_executable=customer.sys.executable
    original_bases=customer._asset_base_dirs
    try:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tools_dir=root/"tools";tools_dir.mkdir()
            executable=root/"client.exe";executable.write_bytes(b"")
            internal=root/"_internal";internal.mkdir()
            customer.__file__=str(tools_dir/"customer_pack.py")
            customer.sys.frozen=True;customer.sys.executable=str(executable)
            assert customer._client_base_dir()==str(root)
            assert customer._asset_base_dirs()==[str(internal),str(root)]
            invalid=root/"invalid"/"assets"/"web";invalid.mkdir(parents=True)
            (invalid/"id.txt").write_text("not-an-id",encoding="utf-8")
            vietnam=root/"vietnam"/"assets"/"web";vietnam.mkdir(parents=True)
            (vietnam/"id.txt").write_text(" 21\n",encoding="utf-8")
            customer._asset_base_dirs=lambda:[str(invalid.parent.parent),str(vietnam.parent.parent)]
            assert customer.read_admin_id()==21 and customer.is_vietnam_customer_pack() is True
    finally:
        customer.__file__=original_file;customer.sys.executable=original_executable
        customer._asset_base_dirs=original_bases
        if had_frozen:customer.sys.frozen=original_frozen
        else:delattr(customer.sys,"frozen")

def verify_title_fallback_parser():
    import recovered.generate_title as title
    original=title.base_chat
    try:
        title.base_chat=lambda *_args,**_kwargs:"{'title': '夏日好物', 'tags': ['#夏日', ' 好物推荐 ', '直播']}"
        result=title.generate_title_and_tags("脚本")
        assert result=={"title":"夏日好物","tags":["夏日","好物推荐","直播"]}
        title.base_chat=lambda *_args,**_kwargs:'prefix {"title":"标准标题","tags":["标签A"]} suffix'
        assert title.generate_title_and_tags("脚本")=={"title":"标准标题","tags":["标签A"]}
    finally:title.base_chat=original

def verify_sentence_generalization_contract():
    import recovered.generalize_sentences as generalize
    assert generalize.slice_content("第一句。[已有一。|已有二！]\n第三句") == ["第一句。","[已有一。|已有二！]","第三句"]
    original_optimize=generalize.optimize_script;original_limiter=generalize.RateLimiter
    values=iter(("改写一","[改写二]","第三句改写"))
    class Limiter:
        def __init__(self,*_args,**_kwargs):pass
        def wait_if_needed(self):pass
    try:
        generalize.RateLimiter=Limiter;generalize.optimize_script=lambda _sentence:next(values)
        result=generalize.generalize_sentences("原句。[已有一。|已有二！]\n第三句",variations=1)
        assert result=="[原句。|改写一]\n[已有一。|已有二！|改写二]\n[第三句|第三句改写]"
    finally:
        generalize.optimize_script=original_optimize;generalize.RateLimiter=original_limiter
    limiter=generalize.RateLimiter(2);limiter.window_size=0
    limiter.wait_if_needed();limiter.wait_if_needed();limiter.wait_if_needed()
    assert len(limiter.requests)<=2

def verify_short_video_language_routing():
    from recovered.short_video_audio_synthesis import normalize_tts_language,resolve_voice_version
    expected={"chinese":"zh-CN","zh-hant":"zh-TW","english":"en-US","en-gb":"en-GB",
              "french":"fr-FR","german":"de-DE","spanish":"es-ES","italian":"it-IT",
              "portuguese":"pt-PT","pt-br":"pt-BR","russian":"ru-RU",
              "japanese":"ja-JP","korean":"ko-KR"}
    for source,target in expected.items():
        assert normalize_tts_language(source,"v3")==target
    assert resolve_voice_version("short_video","zh-CN")=="v2"
    for language in ("en-US","fr-FR","de-DE","es-ES","it-IT","pt-BR","ru-RU","ja-JP","ko-KR"):
        assert resolve_voice_version("short_video",language)=="v3"
    assert resolve_voice_version("ip_agent","zh-CN")=="v3"
    assert resolve_voice_version("other","zh-CN")=="v1"

def verify_short_video_render_parameters():
    import recovered.generate_lip_sync_video as video
    calls=[]
    class Manager:
        def __init__(self,**kwargs):calls.append(("init",kwargs))
        def process_single_file(self,audio_path,output_path=None):
            calls.append(("render",audio_path,output_path));Path(output_path).write_bytes(b"mp4");return output_path
        def stop_playing(self):calls.append(("stop",))
    original=video.importlib.import_module
    try:
        video.importlib.import_module=lambda name:types.SimpleNamespace(VideoStreamManager=Manager)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);audio=root/"audio.wav";audio.write_bytes(b"RIFF");output=root/"video.mp4"
            params={"wenet_conf_path":"conf","wenet_model_path":"wenet","model_path":"unet",
                    "enable_action_generalization":True,"batch_size":6}
            assert video._render_pencil_art_short_video("character",str(audio),str(output),params)==str(output)
        init=calls[0][1]
        assert init["enable_action_generalization"] is True and init["batch_size"]==6
        assert calls[-1]==("stop",)
    finally:video.importlib.import_module=original

def verify_short_video_metadata_lifecycle():
    import recovered.generate_lip_sync_video as video
    import yaml
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);audio=root/"input.wav";audio.write_bytes(b"RIFF")
        originals=(video._resolve_model_dir,video._render_pencil_art_short_video)
        try:
            video._resolve_model_dir=lambda *_args:("character","unet.onnx")
            def render(_model,_audio,output,_params):Path(output).write_bytes(b"mp4");return output
            video._render_pencil_art_short_video=render
            result=video.create_short_video(
                {"name":"商品短片","model_id":"model-1","mode":"audio","audio_path":str(audio),
                 "short_video_id":"video-1","enable_action_generalization":True},
                {"project_root":str(root),"video_output_dir":str(root/"short_videos"),
                 "wenet_config":"conf","wenet_model":"wenet"})
            assert result["success"] is True
            info_path=root/"short_videos"/"video-1"/"video_info.yaml"
            info=yaml.safe_load(info_path.read_text(encoding="utf-8"))
            assert info["id"]=="video-1" and info["name"]=="商品短片"
            assert info["model_id"]=="model-1" and info["mode"]=="audio"
            assert info["video_path"].endswith("video.mp4") and info["audio_path"]==str(audio.resolve())
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",info["create_time"])
            from recovered.main import Api
            api=Api.__new__(Api);api.runtime_dir=root
            listed=api.get_all_short_videos()
            assert listed["status"]=="success" and len(listed["videos"])==1
            item=listed["videos"][0]
            assert item["id"]=="video-1" and item["name"]=="商品短片" and item["model_id"]=="model-1"
        finally:
            video._resolve_model_dir,video._render_pencil_art_short_video=originals

def verify_voice_v2_lifecycle():
    from recovered.voice_infer_v2 import VoiceSynthesizer
    with tempfile.TemporaryDirectory() as directory:
        model_dir=Path(directory)/"pretrained_models"/"OmniVoice"
        model_dir.mkdir(parents=True);(model_dir/"pytorch_model.bin").write_bytes(b"weights")
        reference=Path(directory)/"ref.wav";reference.write_bytes(b"RIFF")
        calls=[]
        fake_model=types.SimpleNamespace(sampling_rate=0)
        fake_omni=types.SimpleNamespace(from_pretrained=lambda *args,**kwargs:(calls.append((args,kwargs)) or fake_model))
        module_name="bin.voice_infer_v2.omnivoice.models.omnivoice"
        original_omni=sys.modules.get(module_name);original_torch=sys.modules.get("torch")
        sys.modules[module_name]=types.SimpleNamespace(OmniVoice=fake_omni)
        sys.modules["torch"]=types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda:False),float16=object(),float32=object())
        try:synthesizer=VoiceSynthesizer(directory,str(reference)," reference ",device="cpu")
        finally:
            if original_omni is None:sys.modules.pop(module_name,None)
            else:sys.modules[module_name]=original_omni
            if original_torch is None:sys.modules.pop("torch",None)
            else:sys.modules["torch"]=original_torch
        assert synthesizer._model_dir()==model_dir
        assert synthesizer.model_dir==model_dir and synthesizer.reference_text=="reference"
        assert synthesizer.sampling_rate==24000 and calls[0][0]==(str(model_dir),)
        assert calls[0][1]["device_map"]=="cpu" and calls[0][1]["dtype"] is synthesizer.dtype
        assert calls[0][1]["load_asr"] is False
        key=synthesizer._build_prompt_cache_key(str(reference),"reference")
        stat=reference.stat();assert key==(reference.resolve(),stat.st_mtime_ns,stat.st_size,"reference")
        synthesizer._prompt_cache["x"]=object();assert synthesizer.clear() is None
        assert not hasattr(synthesizer,"synthesizer") and synthesizer.model is None and not synthesizer._prompt_cache

def verify_voice_v3_lifecycle():
    from recovered.voice_infer_v3 import VoiceSynthesizer
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);model_dir=base/"pretrained_models"/"indextts"
        model_dir.mkdir(parents=True);(model_dir/"config.yaml").write_text("model: test",encoding="utf-8")
        reference=base/"ref.wav";reference.write_bytes(b"RIFF")
        constructor_calls=[];infer_calls=[]
        class FakeIndexTTS:
            def __init__(self,**kwargs):constructor_calls.append(kwargs)
            def infer_fast(self,*args,**kwargs):
                infer_calls.append((args,kwargs))
                with wave.open(str(args[2]),"wb") as output:
                    output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000)
                    output.writeframes(b"\0\0" * 16)
        module_name="bin.voice_infer_v3.indextts.infer"
        original_index=sys.modules.get(module_name);original_torch=sys.modules.get("torch")
        fake_torch=types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda:False,empty_cache=lambda:None),
            inference_mode=contextlib.nullcontext)
        sys.modules[module_name]=types.SimpleNamespace(IndexTTS=FakeIndexTTS);sys.modules["torch"]=fake_torch
        try:
            synth=VoiceSynthesizer(base,str(reference)," reference ",device="cuda",voice_id="v3")
            assert synth.device=="cpu" and synth.is_fp16 is False and synth.sampling_rate==24000
            assert synth.model_dir==model_dir and synth.reference_text=="reference"
            assert constructor_calls==[{"cfg_path":str(model_dir/"config.yaml"),"model_dir":str(model_dir),
                                       "is_fp16":False,"device":"cpu"}]
            override=base/"override.wav";override.write_bytes(b"RIFF")
            synth._cached=lambda *_args:None;synth._record=lambda *_args:None
            assert synth.synthesize("测试",reference_audio=str(override),reference_text=" 临时 ")
            assert infer_calls[0][0][:2]==(str(override),"测试") and infer_calls[0][1]=={"verbose":False}
            assert synth.reference_audio==str(reference) and synth.reference_text=="reference"
            assert synth.clear() is None and not hasattr(synth,"model")
        finally:
            if original_index is None:sys.modules.pop(module_name,None)
            else:sys.modules[module_name]=original_index
            if original_torch is None:sys.modules.pop("torch",None)
            else:sys.modules["torch"]=original_torch

def verify_zipvoice_lifecycle():
    from recovered.voice_infer import VoiceSynthesizer
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);model_dir=base/"zipvoice_distill"
        model_dir.mkdir();(model_dir/"model.json").write_text('{"feature":{"sampling_rate":24000}}')
        (model_dir/"model.pt").write_bytes(b"weights")
        reference=base/"ref.wav";reference.write_bytes(b"RIFF")
        original_load=VoiceSynthesizer._load_model;original_check=VoiceSynthesizer._check_and_download_model
        original_torch=sys.modules.get("torch");module_name="bin.voice_infer.zipvoice.bin.infer_zipvoice"
        original_generate=sys.modules.get(module_name);events=[]
        fake_torch=types.SimpleNamespace(
            no_grad=contextlib.nullcontext,
            cuda=types.SimpleNamespace(is_available=lambda:False,empty_cache=lambda:None))
        def fake_load(self):
            events.append("load");self.model=object();self.vocoder=object();self.tokenizer=object();self.feature_extractor=object();return self.model
        def fake_generate(*args,**kwargs):events.append((args,kwargs));Path(args[0]).write_bytes(b"RIFF")
        VoiceSynthesizer._load_model=fake_load;VoiceSynthesizer._check_and_download_model=lambda self:str(self.model_dir)
        sys.modules["torch"]=fake_torch;sys.modules[module_name]=types.SimpleNamespace(generate_sentence=fake_generate)
        try:
            synth=VoiceSynthesizer(base,str(reference)," reference ",device="cuda",voice_id="zip")
            assert events==["load"] and synth.device=="cpu" and synth.model_dir==model_dir
            assert synth.reference_text=="reference" and synth.voice_infer_version is None
            override=base/"override.wav";override.write_bytes(b"RIFF")
            synth._cached=lambda *_args:None;synth._record=lambda *_args:None
            assert synth.synthesize("测试",reference_audio=str(override),reference_text=" 临时 ")
            call=events[-1];assert call[0][1:4]==("临时",str(override),"测试")
            assert call[1]=={"speed":1.0,"sampling_rate":24000}
            assert synth.reference_audio==str(reference) and synth.reference_text=="reference"
            assert synth.clear() is None
            assert all(not hasattr(synth,name) for name in ("model","vocoder","tokenizer","feature_extractor"))
        finally:
            VoiceSynthesizer._load_model=original_load;VoiceSynthesizer._check_and_download_model=original_check
            if original_torch is None:sys.modules.pop("torch",None)
            else:sys.modules["torch"]=original_torch
            if original_generate is None:sys.modules.pop(module_name,None)
            else:sys.modules[module_name]=original_generate

def verify_taobao_explain_cycle():
    from recovered.taobao_live_control import TaobaoLiveControl
    control=TaobaoLiveControl._create()
    control._active_goods_id=123;control._popup_pending=True
    control._explain_fail_streak=4;control._control_recover_streak=3
    before=time.monotonic();control._arm_explain_watch(-5)
    first=control._explain_watch_until
    assert first>=before+1 and control._arm_explain_watch(0) is None
    assert control._explain_watch_until>=first
    assert control._stop_explain_cycle(reason=None) is None
    assert control._active_goods_id is None and control._popup_pending is False
    assert control._explain_watch_until==0 and control._explain_fail_streak==0 and control._control_recover_streak==0
    calls=[];control._active_goods_id=456;control._popup_interval_sec=999
    control._last_popup_at=time.monotonic();control._popup_pending=False
    control._do_popup=lambda goods_id:calls.append(("popup",goods_id))
    assert control._pump_active_popup() is None and not calls
    control._popup_pending=True;assert control._pump_active_popup() is None
    assert calls==[("popup",456)] and control._popup_pending is False
    def closed_target(_goods_id):raise RuntimeError("Target page, context or browser has been closed")
    control._do_popup=closed_target;control._popup_pending=True
    control._do_recycle_page=lambda:calls.append(("recycle",None))
    control._active_goods_id=789;control._pump_active_popup()
    assert control._active_goods_id is None and calls[-1]==("recycle",None)

def verify_taobao_action_dispatch():
    from recovered.taobao_live_control import TaobaoLiveControl
    control=TaobaoLiveControl._create()
    control._explain_fail_streak=7;control._control_recover_streak=4
    assert control._handle_action("set_active_goods",{"goods_id":"123","interval_sec":1}) is True
    assert control._active_goods_id==123 and control._popup_interval_sec==5.0
    assert control._popup_pending is True and control._explain_fail_streak==0 and control._control_recover_streak==0
    closed=[];control._safe_close_browser=lambda:closed.append(True)
    control._initializing=True
    assert control._handle_action("disconnect",{}) is True
    assert closed==[True] and control._active_goods_id is None and control._initializing is False
    try:control._handle_action("not-an-action",{})
    except ValueError as error:assert "not-an-action" in str(error)
    else:raise AssertionError("unknown Taobao action must fail")

def verify_taobao_control_recovery():
    from recovered.taobao_live_control import TaobaoLiveControl
    class Page:
        def __init__(self,url="about:blank"):self.url=url;self.closed=False;self.waits=[]
        def is_closed(self):return self.closed
        def close(self):self.closed=True
        def wait_for_timeout(self,_milliseconds):return None
        def wait_for_selector(self,selector,**kwargs):self.waits.append((selector,kwargs));return None
        def get_by_text(self,*_args,**_kwargs):
            return types.SimpleNamespace(count=lambda:0)
    class Context:
        def __init__(self,page):self.pages=[page];self.created=[]
        def new_page(self):
            page=Page();self.pages.append(page);self.created.append(page);return page
    control=TaobaoLiveControl._create();control._playwright=object();control._live_id="123"
    page=Page("https://liveplatform.taobao.com/restful/index/live/control?liveId=123")
    control._page=page;control._context=Context(page);control._control_recover_streak=2
    assert control._ensure_on_control_page(reason="test") is True and control._control_recover_streak==0
    control._dismiss_guides=lambda _page:None;control._dismiss_explain_dialogs=lambda _page,retries=1:None
    control._settle_control_page(page,comment_wait_ms=321)
    assert page.waits==[(".tcp-commodity-item",{"timeout":180000}),("#comment-page",{"timeout":321})]
    page.url="about:blank";control.open_control_page=lambda live_id:setattr(control._page,"url",f"https://liveplatform.taobao.com/restful/index/live/control?liveId={live_id}") or True
    assert control._ensure_on_control_page(reason="redirect") is True
    assert control._control_recover_streak==0 and control._control_recover_at==0 and control._page_ready_at>0
    control._active_goods_id=9;control._page=page;page.closed=False
    control._do_recycle_page();assert page.closed and control._popup_pending is True
    assert control._page in control._context.created
    import recovered.taobao_live_control as taobao_module
    recycled=[];control._do_recycle_page=lambda:recycled.append(True)
    control._page_ready_at=time.monotonic();control._pump_page_recycle();assert not recycled
    old_interval=taobao_module._PAGE_RECYCLE_INTERVAL_SEC
    try:
        taobao_module._PAGE_RECYCLE_INTERVAL_SEC=0
        control._page_ready_at=max(.000001,time.monotonic()/2);control._pump_page_recycle()
    finally:taobao_module._PAGE_RECYCLE_INTERVAL_SEC=old_interval
    assert recycled==[True]

def verify_live_brain():
    from recovered.digital_live_manager import DigitalLiveManager
    from recovered.live_manager_runtime import (BROADCAST_QUEUE_TARGET,
        INTERACTION_MESSAGE_CAP, PRODUCT_SWITCH_QUEUE_THRESHOLD, TTS_EMIT_BURST_MAX,
        TTS_PIPELINE_DEPTH, InteractionMessage, LiveManager, LocalLiveBrain,
        _build_smart_dianpin_targets, _fallback_reply_text, _match_smart_dianpin)
    assert (BROADCAST_QUEUE_TARGET,PRODUCT_SWITCH_QUEUE_THRESHOLD,
            TTS_EMIT_BURST_MAX,TTS_PIPELINE_DEPTH)==(1000,0,4,4)
    assert INTERACTION_MESSAGE_CAP==500
    def assert_tts_payload(payload,text,queue,**extra):
        expected={"text":text,"voice_id":None,"voice_infer_version":"v1",
                  "language":"zh-CN","speed":1.1,"queue":queue,
                  "target_face_index":0,"use_silent_features":False,
                  "use_cache":True,"needs_language_translate":False}
        expected.update(extra)
        assert payload==expected
    assert LocalLiveBrain._normalize_message_type("comment","你好")=="弹幕"
    assert LocalLiveBrain._normalize_message_type("COMMENT","你好")=="COMMENT"
    assert LocalLiveBrain._normalize_message_type("chat","进入了直播间")=="进入直播间"
    assert LocalLiveBrain._normalize_message_type("follow","")=="关注"
    assert LocalLiveBrain._normalize_message_type("like","")=="礼物"
    assert _fallback_reply_text("zh-CN","danmu","小云","怎么用")=="怎么用，小云，这个问题我给你简单说一下。"
    assert _fallback_reply_text("ja-JP","danmu","小云","")=="小云，我看到你的问题啦。"
    assert _fallback_reply_text("yue","enter","阿明","")=="欢迎阿明来到直播间。"
    assert _fallback_reply_text("zh-CN","follow","阿明","")=="感谢阿明的关注。"
    assert _fallback_reply_text("zh-CN","like","阿明","")=="谢谢阿明的支持。"
    assert _fallback_reply_text("zh-CN","retention","阿明","")=="阿明还在吗？有问题可以直接问我。"
    assert _fallback_reply_text("zh-CN","gift","阿明","")=="感谢宝子关注。"
    assert _fallback_reply_text("en-US","danmu","Amy","")=="Thanks Amy, I got your question."
    assert _fallback_reply_text("en-US","enter","Amy","")=="Welcome Amy!"
    assert _fallback_reply_text("en-US","follow","Amy","")=="Thanks for following, Amy!"
    assert _fallback_reply_text("en-US","like","Amy","")=="Thanks for the support, Amy!"
    assert _fallback_reply_text("en-US","retention","Amy","")=="Amy, let me know if you have any questions."
    assert _fallback_reply_text("en-US","gift","Amy","")=="Thanks for watching."
    assert _fallback_reply_text("vi-VN","danmu","Lan","")==(
        "Lan, mình đã thấy bình luận của bạn. Mình trả lời ngắn gọn nhé.")
    assert _fallback_reply_text("vi-VN","enter","Lan","")=="Chào mừng Lan vào phòng live."
    assert _fallback_reply_text("vi-VN","follow","Lan","")=="Cảm ơn Lan đã theo dõi."
    assert _fallback_reply_text("vi","like","Lan","")=="Cảm ơn Lan đã ủng hộ."
    assert _fallback_reply_text("vi","retention","Lan","")==(
        "Lan, bạn còn ở đó không? Có câu hỏi thì nhắn mình nhé.")
    assert _fallback_reply_text("vi","gift","Lan","")=="Cảm ơn bạn đã theo dõi."
    targets = _build_smart_dianpin_targets([{"keywords":"苹果"},{"keywords":"香蕉"}])
    assert _match_smart_dianpin("介绍香蕉", targets)[0]["product_index"] == 1
    protocol_brain=LocalLiveBrain(session_id="message-protocol",config={
        "live_streamer_name":"主播本人"},llm_config={},emit_task=lambda _task:None,
        queue_provider=lambda:{})
    protocol_brain.submit_danmu({"user":" 甲 ","text":" 问题 ","kind":"comment",
                                  "timestamp":"12.5"})
    protocol_brain.submit_danmu({"nickname":"乙","content":"进入了直播间","type":"chat"})
    protocol_brain.submit_danmu({"nickname":"主播本人","content":"忽略","type":"comment"})
    assert all(isinstance(item,InteractionMessage) for item in protocol_brain.interaction_messages)
    assert [(item.msg_type,item.nickname,item.content) for item in protocol_brain.interaction_messages]==[
        ("进入直播间","乙","进入了直播间"),("弹幕","甲","问题")]
    assert protocol_brain.interaction_messages[1].timestamp==12.5
    protocol_brain.interaction_messages.clear()
    for index in range(INTERACTION_MESSAGE_CAP+5):
        protocol_brain.submit_danmu({"nickname":str(index),"content":"消息","type":"comment"})
    assert len(protocol_brain.interaction_messages)==INTERACTION_MESSAGE_CAP
    assert protocol_brain.interaction_messages[0].nickname=="5"
    protocol_brain.submit_danmu({"nickname":"优先进场","content":"进入直播间","type":"enter"})
    assert len(protocol_brain.interaction_messages)==INTERACTION_MESSAGE_CAP
    assert protocol_brain.interaction_messages[0].nickname=="优先进场"
    protocol_brain._executor.shutdown(wait=False,cancel_futures=True)
    enqueue_tasks=[]
    enqueue_brain=LocalLiveBrain(session_id="enqueue-protocol",config={
        "language":"en-US","voice_id":"voice-a","voice_infer_version":"v3",
        "voice_speed":1.25,"use_audio_cache":False,"prohibited_words":["删除"],
        "voice_general_config":{"fallback":True},
        "voice_general_config_map":{"voice-b":{"selected":True}}},llm_config={},
        emit_task=enqueue_tasks.append,queue_provider=lambda:{})
    enqueue_brain._enqueue_tts("删除 hello 中文",queue="manual",voice_id="voice-b",
                               product_index=3,seek_after_ms="42")
    assert enqueue_tasks[-1]["payload"]=={
        "text":"hello","voice_id":"voice-b","voice_infer_version":"v3",
        "language":"en-US","speed":1.25,"queue":"manual","target_face_index":0,
        "use_silent_features":False,"use_cache":False,"needs_language_translate":False,
        "product_index":3,"seek_after_ms":42,
        "voice_general_config":{"selected":True}}
    enqueue_brain._enqueue_tts("纯中文",queue="danmu")
    assert enqueue_tasks[-1]["payload"]["text"]=="纯中文"
    assert enqueue_tasks[-1]["payload"]["needs_language_translate"] is True
    assert enqueue_tasks[-1]["payload"]["voice_general_config"]=={"fallback":True}
    before_empty=len(enqueue_tasks)
    enqueue_brain._enqueue_tts("删除",queue="normal")
    assert len(enqueue_tasks)==before_empty
    enqueue_brain._executor.shutdown(wait=False,cancel_futures=True)
    emitted = []
    brain = LocalLiveBrain(session_id="verify", config={"enableSmartDianpin":True,
        "dianpinCooldownSeconds":0,"product_scripts":[{"scripts":["A"],"keywords":["苹果"]},
        {"scripts":["B"],"keywords":["香蕉"]}]}, llm_config={}, emit_task=emitted.append,
        queue_provider=lambda:{"normal":1,"pending_normal":4})
    brain.product_script_groups=[{"product_index":"8"},{"product_index":"bad"},
                                 {"product_index":3}]
    assert brain._find_product_group_index(8)==0
    assert brain._find_product_group_index("3")==2
    assert brain._find_product_group_index(99) is None
    brain.product_script_groups=brain._build_product_script_groups()
    brain.script_list=[{"product_index":"7"},None,{"product_index":2}]
    assert brain._find_product_script_cursor(7)==0
    assert brain._find_product_script_cursor("2")==2
    assert brain._find_product_script_cursor(99) is None
    brain.script_list=brain._scripts
    brain.config["product_scripts"]=[{"product_index":"9","content":123},None,
                                      {"product_index":4,"content":""}]
    brain.product_info="全局商品信息"
    assert brain._resolve_product_info(9)=="123"
    assert brain._resolve_product_info("4")=="全局商品信息"
    assert brain._resolve_product_info(99)=="全局商品信息"
    brain.submit_danmu({"type":"comment","nickname":"测试","content":"看看香蕉"}); brain.tick()
    assert brain.current_product_index == 1
    assert [task["type"] for task in emitted] == ["clear_normal_queues", "tts_speak"]
    assert emitted[0]["payload"]=={"clear_queues":True,"product_index":1}
    assert_tts_payload(emitted[1]["payload"],"好的，接下来为大家介绍2号商品。","normal",
                       product_index=1)
    assert brain.broadcast_cursor==1 and brain._pending_script_tts==[]
    assert brain._try_smart_dianpin("看看苹果",now=brain.last_dianpin_at+4.9) is False
    assert brain.current_product_index==1
    assert brain._try_smart_dianpin("看看苹果",now=brain.last_dianpin_at+5.0) is True
    empty_brain=LocalLiveBrain(session_id="empty-dianpin",config={},llm_config={},
        emit_task=lambda _task:None,queue_provider=lambda:{})
    assert empty_brain._jump_to_digital_dianpin(0,"苹果") is False
    sparse_brain=LocalLiveBrain(session_id="sparse-dianpin",
        config={"product_scripts":[{"product_index":7,"scripts":["七号"]}]},llm_config={},
        emit_task=lambda _task:None,queue_provider=lambda:{})
    assert sparse_brain._jump_to_digital_dianpin(8,"八号") is False
    multi_jump=[]
    multi_brain=LocalLiveBrain(session_id="multi-dianpin",config={"multi_product_enabled":True,
        "voice_infer_version":"v3","product_info":"默认信息","product_scripts":[
            {"product_info":"一号信息","config":{"imageModelId":"image-1","voiceModelId":"voice-1"},
             "scripts":["一号"]}]},llm_config={},emit_task=multi_jump.append,queue_provider=lambda:{})
    assert multi_brain._jump_to_digital_dianpin(0,"一号",content="介绍一号") is True
    assert multi_brain.image_model_id=="image-1" and multi_brain.voice_id=="voice-1"
    assert multi_brain.current_product_index==0 and multi_brain.current_product_info=="一号信息"
    assert multi_jump[0]["type"]=="clear_normal_queues"
    assert multi_jump[0]["payload"]=={"clear_queues":True,"product_index":0,
        "new_image_model_id":"image-1","new_voice_id":"voice-1","voice_infer_version":"v3"}
    assert multi_jump[1]["payload"]["queue"]=="normal"
    multi_brain.product_script_groups=[]
    assert multi_brain._jump_to_digital_dianpin(4,"缺失") is False
    idle_tasks=[]
    idle_brain=LocalLiveBrain(session_id="idle-dianpin",config={"enableSmartDianpin":True,
        "origin_idle_video_mode":True,"product_scripts":[{"keywords":["苹果"],"start_ms":2345}]},
        llm_config={},emit_task=idle_tasks.append,queue_provider=lambda:{})
    assert idle_brain._try_smart_dianpin("介绍苹果",now=100.0) is True
    assert idle_brain.current_product_index==-1
    assert idle_tasks[0]["type"]=="tts_speak"
    assert_tts_payload(idle_tasks[0]["payload"],"好的，接下来为大家介绍1号商品。","danmu",
                       seek_after_ms=2345)
    assert LocalLiveBrain._interaction_enabled(99999) is True
    assert LocalLiveBrain._interaction_enabled(100000) is False
    import recovered.llm_reply as live_llm_reply
    interaction_calls=[]
    original_replies=(live_llm_reply.reply_danmu,live_llm_reply.reply_enter,
                      live_llm_reply.reply_follow,live_llm_reply.reply_like)
    live_llm_reply.reply_danmu=lambda *args:interaction_calls.append(("danmu",args)) or "弹幕回复"
    live_llm_reply.reply_enter=lambda *args:interaction_calls.append(("enter",args)) or "进场回复"
    live_llm_reply.reply_follow=lambda *args:interaction_calls.append(("follow",args)) or "关注回复"
    live_llm_reply.reply_like=lambda *args:interaction_calls.append(("like",args)) or "点赞回复"
    interaction_tasks=[]
    interaction_brain=LocalLiveBrain(session_id="interaction",config={"product_info":"商品",
        "qa_info":"问答","special_instructions":"要求"},llm_config={"enabled":True},
        emit_task=interaction_tasks.append,queue_provider=lambda:{})
    interaction_brain._interaction_llm_executor=None
    try:
        for kind,name in (("comment","甲"),("enter","乙"),("follow","丙"),("gift","丁")):
            interaction_brain.submit_danmu({"type":kind,"nickname":name,"content":"问题"})
        interaction_brain._tick_interactions()
    finally:
        (live_llm_reply.reply_danmu,live_llm_reply.reply_enter,
         live_llm_reply.reply_follow,live_llm_reply.reply_like)=original_replies
        interaction_brain._executor.shutdown(wait=False,cancel_futures=True)
    assert interaction_calls==[
        ("danmu",("甲","问题","商品","问答","要求")),
        ("enter",("乙","商品","要求")),
        ("follow",("丙","商品","要求")),
        ("like",("丁","商品","要求"))]
    assert [task["payload"]["text"] for task in interaction_tasks]==[
        "弹幕回复","进场回复","关注回复","点赞回复"]
    assert "乙" in interaction_brain.welcomed_nicknames
    original_retention=live_llm_reply.reply_retention
    import recovered.live_manager_runtime as live_runtime_module
    original_choice=live_runtime_module.random.choice
    retention_calls=[];choice_candidates=[];retention_tasks=[]
    live_llm_reply.reply_retention=lambda *args:retention_calls.append(args) or "留人回复"
    live_runtime_module.random.choice=lambda values:(choice_candidates.extend(values),values[-1])[1]
    retention_brain=LocalLiveBrain(session_id="retention",config={
        "comment_reply_interval":100000,"entrance_reply_interval":100000,
        "follow_reply_interval":100000,"gift_reply_interval":100000,
        "mention_interval":0,"blocked_users":["黑名单"],"exclude_nicknames":["主播"],
        "product_info":"留人商品","special_instructions":"留人要求"},
        llm_config={"enabled":True},emit_task=retention_tasks.append,queue_provider=lambda:{})
    retention_brain._interaction_llm_executor=None
    for name in ["甲","甲","黑名单","主播","乙","丙","丁","戊","己","庚","辛","壬"]:
        retention_brain.submit_danmu({"type":"comment","nickname":name,"content":"历史消息"})
    try:
        retention_brain._tick_interactions()
    finally:
        live_llm_reply.reply_retention=original_retention
        live_runtime_module.random.choice=original_choice
        retention_brain._executor.shutdown(wait=False,cancel_futures=True)
    assert choice_candidates==["甲","乙","丙","丁","戊","己","庚","辛"]
    assert retention_calls==[("辛","留人商品","留人要求")]
    assert retention_tasks[-1]["payload"]["text"]=="留人回复"
    fallback_retention=[]
    fallback_brain=LocalLiveBrain(session_id="retention-fallback",config={
        "comment_reply_interval":100000,"entrance_reply_interval":100000,
        "follow_reply_interval":100000,"gift_reply_interval":100000,
        "mention_interval":0},llm_config={},emit_task=fallback_retention.append,
        queue_provider=lambda:{})
    fallback_brain._interaction_llm_executor=None
    fallback_brain.submit_danmu({"type":"comment","nickname":"小留","content":"历史消息"})
    fallback_brain._tick_interactions()
    fallback_brain._executor.shutdown(wait=False,cancel_futures=True)
    assert fallback_retention[-1]["payload"]["text"]=="小留还在吗？有问题可以直接问我。"
    emitted.clear()
    brain._pending_script_tts=[("第一段",0),("第二段",1)]
    brain._drain_pending_script_tts()
    assert brain._pending_script_tts==[]
    assert [(task["payload"]["text"],task["payload"]["queue"],task["payload"]["target_face_index"],
             task["payload"]["use_silent_features"],task["payload"]["product_index"])
            for task in emitted]==[("第一段","normal",0,False,0),("第二段","normal",0,False,1)]
    ordered=LocalLiveBrain(session_id="order",config={},llm_config={},emit_task=lambda _task:None,
                           queue_provider=lambda:{})
    calls=[]
    method_order=("_drain_simulated_questions","_drain_manual_speaks","_drain_pending_script_tts",
                  "_tick_interactions","_tick_broadcast","_tick_rewrite_pool","_tick_shift_schedule")
    for name in method_order:setattr(ordered,name,lambda name=name:calls.append(name))
    ordered.tick();assert calls==list(method_order)
    calls.clear();assert ordered._tick_lock.acquire(blocking=False)
    try:assert ordered.tick() is None and calls==[]
    finally:ordered._tick_lock.release()
    ordered.mark_stopped();ordered.tick();assert calls==[]
    from unittest.mock import patch

    shifts = [{"duration_seconds": 3, "product_index": 0},
              {"duration": 5, "product_index": 1}]
    events, products = [], []
    scheduler = LocalLiveBrain(session_id="shifts", config={"shift_schedule": shifts},
                               llm_config={}, emit_task=events.append, queue_provider=lambda: {})
    scheduler._switch_to_product = products.append
    scheduler.shift_started_at = 100
    clock = sys.modules[LocalLiveBrain.__module__].time
    for _ in range(20):
        current = scheduler.shift_state
        deadline = scheduler.shift_started_at + (3, 5)[current]
        with patch.object(clock, "monotonic", return_value=deadline - 0.001):
            scheduler._tick_shift_schedule()
        assert scheduler.shift_state == current
        with patch.object(clock, "monotonic", return_value=deadline):
            scheduler._tick_shift_schedule()
        assert scheduler.shift_state == 1 - current
        assert scheduler.shift_started_at == deadline
    assert products == [1, 0] * 10
    assert [event["payload"]["shift_index"] for event in events] == products
    scheduler._executor.shutdown(wait=False, cancel_futures=True)
    broadcast=[]
    feeder=LocalLiveBrain(session_id="broadcast",config={"product_scripts":[{"scripts":["甲","乙"]}]},
                          llm_config={},emit_task=broadcast.append,queue_provider=lambda:{})
    feeder._tick_broadcast()
    assert [task["payload"]["text"] for task in broadcast]==["甲","乙","甲","乙"]
    assert feeder.broadcast_cursor==4
    typed=[]
    typed_brain=LocalLiveBrain(session_id="typed",config={"voice_id":"host-voice",
        "assistant_voice_id":"assistant-voice","is_dual_streamer_mode":True},llm_config={},
        emit_task=typed.append,queue_provider=lambda:{})
    typed_brain._emit_script_item({"type":"host","content":"主播话术","product_index":2})
    typed_brain._emit_script_item({"type":"assistant","content":"助播话术","product_index":3})
    typed_brain._emit_script_item({"type":"pause","duration":"1.5","product_index":3})
    typed_brain._emit_script_item({"type":"pause","duration":0,"product_index":3})
    assert_tts_payload(typed[0]["payload"],"主播话术","normal",voice_id="host-voice",
                       product_index=2)
    assert_tts_payload(typed[1]["payload"],"助播话术","normal",voice_id="assistant-voice",
                       target_face_index=1,product_index=3)
    assert typed[2]=={"id":3,"type":"pause","payload":{"duration":1.5,"queue":"normal",
                     "target_face_index":0,"use_silent_features":True}}
    assert len(typed)==3
    from recovered import llm_reply as live_llm_reply
    class ImmediateExecutor:
        def submit(self,callable_):callable_();return object()
    original_rewrite=live_llm_reply.script_rewrite_content
    rewrite_brain=LocalLiveBrain(session_id="rewrite",config={"special_instructions":"keep facts"},
        llm_config={},emit_task=lambda _task:None,queue_provider=lambda:{})
    rewrite_brain._interaction_llm_executor=ImmediateExecutor()
    try:
        live_llm_reply.script_rewrite_content=lambda text,instructions:f"{text}-改写-{instructions}"
        assert rewrite_brain._submit_interval_rewrite("原稿",product_index=7)
        assert rewrite_brain._pending_script_tts==[("原稿-改写-keep facts",7)]
        assert rewrite_brain._interval_rewrite_inflight is False
        live_llm_reply.script_rewrite_content=lambda *_args:(_ for _ in ()).throw(RuntimeError("LLM断开"))
        assert rewrite_brain._submit_interval_rewrite("回退原稿",product_index=8)
        assert rewrite_brain._pending_script_tts[-1]==("回退原稿",8)
        assert rewrite_brain._interval_rewrite_inflight is False
    finally:live_llm_reply.script_rewrite_content=original_rewrite
    replies=[]
    reply_brain=LocalLiveBrain(session_id="reply",config={"reply_blocked_keywords":["禁词"]},
        llm_config={},emit_task=replies.append,queue_provider=lambda:{})
    assert reply_brain._normalize_control_text_reply("  欢迎   来到直播间  "," 小云 ")=="@小云 欢迎 来到直播间"
    assert reply_brain._normalize_control_text_reply("@别人 请看一号商品","小云")=="@小云 请看一号商品"
    assert reply_brain._normalize_control_text_reply("@小云 已经正确","小云")=="@小云 已经正确"
    assert reply_brain._normalize_control_text_reply("@别人","   ")=="@用户"
    assert reply_brain._normalize_control_text_reply("甲"*100,"昵称")==("@昵称 "+"甲"*46)
    assert len(reply_brain._normalize_control_text_reply("甲"*100,"昵称"))==50
    assert reply_brain._speak_interaction_reply("  正常回复  ") is True
    assert reply_brain._speak_interaction_reply("含有禁词") is False
    assert reply_brain._speak_interaction_reply("   ") is False
    assert len(replies)==1
    assert_tts_payload(replies[0]["payload"],"正常回复","danmu")
    reply_brain._interaction_llm_executor=None
    reply_brain._submit_interaction_llm(kind="comment",nickname="小云",content="问题",
                                        llm_call=lambda:"直接回答")
    assert replies[-1]["payload"]["text"]=="直接回答"
    reply_brain._submit_interaction_llm(kind="follow",nickname="小云",content="",
                                        llm_call=lambda:"")
    assert replies[-1]["payload"]["text"]=="感谢小云的关注。"
    before_interaction_error=len(replies)
    reply_brain._submit_interaction_llm(kind="gift",nickname="小云",content="",
        llm_call=lambda:(_ for _ in ()).throw(RuntimeError("互动断开")))
    assert len(replies)==before_interaction_error
    reply_brain._interaction_llm_executor=ImmediateExecutor()
    reply_brain._submit_interaction_llm(kind="like",nickname="小云",content="",
                                        llm_call=lambda:None)
    assert replies[-1]["payload"]["text"]=="谢谢小云的支持。"
    from recovered import taobao_live_control as taobao_control
    original_get_controller=taobao_control.get_taobao_controller
    class FakeTaobaoController:
        def __init__(self,connected=True,result=True,error=None):
            self._connected=connected;self._result=result;self._error=error;self.sent=[]
        def connected(self):return self._connected
        def send_comment(self,text):
            self.sent.append(text)
            if self._error:raise self._error
            return self._result
    try:
        disconnected=FakeTaobaoController(connected=False)
        taobao_control.get_taobao_controller=lambda:disconnected
        assert reply_brain._send_taobao_control_reply(" 测试评论 ") is False and not disconnected.sent
        connected=FakeTaobaoController(result=True)
        taobao_control.get_taobao_controller=lambda:connected
        assert reply_brain._send_taobao_control_reply(" 测试评论 ") is True
        assert connected.sent==["测试评论"]
        assert reply_brain._send_taobao_control_reply("含有禁词") is False
        failed=FakeTaobaoController(error=RuntimeError("发送断开"))
        taobao_control.get_taobao_controller=lambda:failed
        assert reply_brain._send_taobao_control_reply("异常评论") is False
    finally:taobao_control.get_taobao_controller=original_get_controller
    original_generate_text_reply=live_llm_reply.generate_text_reply
    control_replies=[]
    reply_brain._interaction_llm_executor=ImmediateExecutor()
    reply_brain._send_taobao_control_reply=lambda text:control_replies.append(text) or True
    try:
        live_llm_reply.generate_text_reply=lambda *args:" 原始回答 "
        assert reply_brain._submit_ai_control_reply("小云","问题",{"name":"商品"}) is None
        assert control_replies.pop()=="@小云 原始回答"
        live_llm_reply.generate_text_reply=lambda *args:""
        reply_brain.language="zh-CN"
        reply_brain._submit_ai_control_reply("小云","问题",{})
        assert control_replies.pop()=="@小云 收到，请稍等主播回复哦"
        reply_brain.language="vi-VN"
        reply_brain._submit_ai_control_reply("Lan","问题",{})
        assert control_replies.pop()=="@Lan Mình đã收到您的提问。"
        live_llm_reply.generate_text_reply=lambda *args:(_ for _ in ()).throw(RuntimeError("模型异常"))
        reply_brain._submit_ai_control_reply("小云","问题",{})
        assert not control_replies
        reply_brain._stopped=True
        live_llm_reply.generate_text_reply=lambda *args:"不应调用"
        reply_brain._submit_ai_control_reply("小云","问题",{})
        assert not control_replies
        reply_brain._stopped=False
    finally:live_llm_reply.generate_text_reply=original_generate_text_reply
    blocked=LocalLiveBrain(session_id="blocked",config={"product_scripts":[{"scripts":["不应发射"]}]},
                           llm_config={},emit_task=broadcast.append,
                           queue_provider=lambda:{"pending_normal":TTS_PIPELINE_DEPTH})
    before=len(broadcast);blocked._tick_broadcast();assert len(broadcast)==before
    blocked._queue_provider=lambda:{"normal":BROADCAST_QUEUE_TARGET}
    blocked._tick_broadcast();assert len(broadcast)==before and blocked._broadcast_buffer_logged
    audio=[]
    audio_brain=LocalLiveBrain(session_id="audio",config={"script_input_mode":"audio",
        "script_audio_count":4},llm_config={},
                               emit_task=audio.append,queue_provider=lambda:{})
    audio_brain._tick_broadcast()
    assert [task["payload"]["index"] for task in audio]==[0,1,2,3]
    assert all(task["payload"]["queue"]=="normal" and
               task["payload"]["target_face_index"]==0 for task in audio)
    multi=[]
    multi_brain=LocalLiveBrain(session_id="multi",config={"multi_product_enabled":True,
        "product_scripts":[{"scripts":["商品一"]},{"scripts":["商品二"]}]},llm_config={},
        emit_task=multi.append,queue_provider=lambda:{})
    multi_brain.current_product_index=1;multi_brain._tick_broadcast()
    assert [(task["type"],task["payload"].get("text"),task["payload"].get("product_index"))
            for task in multi]==[("tts_speak","商品二",1),("switch_product",None,0),
                                  ("tts_speak","商品一",0),("switch_product",None,1)]
    waiting=[]
    waiting_brain=LocalLiveBrain(session_id="multi-wait",config={"multi_product_enabled":True,
        "product_scripts":[{"scripts":["商品"]}]},llm_config={},emit_task=waiting.append,
        queue_provider=lambda:{"normal":1})
    waiting_brain._tick_broadcast()
    assert waiting==[] and waiting_brain.current_product_index==-1
    manager=LiveManager({"minimax_voice_config":{"api_key":"mini-key","model":"m"},
                         "cosyvoice_voice_config":{"api_key":"cosy-key","region":"r"}})
    mini=manager._build_minimax_runtime_config({"minimax":{"minimax_voice_id":"  mini-voice  ","ignored":1}})
    cosy=manager._build_cosyvoice_runtime_config({"cosyvoice":{"cosyvoice_voice_id":"  cosy-voice  ","ignored":1}})
    assert mini=={"api_key":"mini-key","model":"m","minimax_voice_id":"mini-voice"}
    assert cosy=={"api_key":"cosy-key","region":"r","cosyvoice_voice_id":"cosy-voice"}
    assert manager._build_minimax_runtime_config({"minimax":{}})=={"api_key":"mini-key","model":"m"}
    cache_manager=LiveManager({})
    cache_synth_calls=[]
    class CacheSynth:
        def synthesize(self,text,speed,**kwargs):
            cache_synth_calls.append((text,speed,kwargs));return "/tmp/cached.wav"
    cache_voice_requests=[]
    cache_manager._ensure_voice_synthesizer=lambda voice_id,version:(
        cache_voice_requests.append((voice_id,version)) or CacheSynth()
    )
    assert cache_manager.prepare_multilingual_audio_cache(
        scripts="主播{A|B}。{助:助播话。}",voice_id=" host ",assistant_voice_id=" helper ",
        shift_schedule=[{"voiceModelId":" shift ","content":"换班话。"}],
        multi_product_configs=[{"voiceModelId":"product","scripts":[{"content":"商品话。"}]}],
        language="zh-CN",voice_speed=1.2,voice_infer_version="v2",
    ) is True
    assert set(cache_voice_requests)=={
        ("host","v2"),("helper","v2"),("shift","v2"),("product","v2")
    }
    assert all(speed==1.2 and options=={"language":"zh-CN","use_cache":True}
               for _text,speed,options in cache_synth_calls)
    assert {text for text,_speed,_options in cache_synth_calls}=={
        "主播A。","主播B。","助播话。","换班话。","商品话。"
    }
    assert cache_manager.prepare_multilingual_audio_cache(scripts="x",voice_id=None) is False
    class TTSStreamer:
        def __init__(self):self.items=[]
        def add_audio_to_queue(self,audio,queue_name=None,**kwargs):
            if queue_name is not None:kwargs={"queue_name":queue_name,**kwargs}
            self.items.append((audio,kwargs))
    tts_manager=LiveManager({"voice_id":"primary","language":"zh-CN","voice_speed":1.25})
    tts_manager.host_streamer=TTSStreamer()
    synth_calls=[]
    class TTSSynth:
        def synthesize(self,text,**kwargs):
            synth_calls.append((text,kwargs));return "/tmp/test.wav"
    tts_manager._ensure_voice_synthesizer=lambda voice_id,version:TTSSynth()
    long_text="中"*200+"。"+"中"*200
    tts_manager._handle_tts_speak({"text":long_text,"queue":"danmu","target_face_index":"2",
                                   "use_silent_features":True,"use_cache":False})
    assert len(synth_calls)==1
    synth_text,synth_options=synth_calls[0]
    assert synth_options=={"speed":1.25,"language":"zh-CN","use_cache":False}
    assert len(synth_text)<len(long_text)
    assert tts_manager.host_streamer.items==[("/tmp/test.wav",{
        "queue_name":"danmu","use_silent_features":True,"target_face_index":2})]
    from recovered.live_manager_runtime import TTS_CLOUD_TIMEOUT_SECONDS,TTS_LOCAL_TIMEOUT_SECONDS
    assert (TTS_CLOUD_TIMEOUT_SECONDS,TTS_LOCAL_TIMEOUT_SECONDS)==(90.0,120.0)
    import recovered.minimax as minimax_runtime
    import recovered.cosyvoice as cosyvoice_runtime
    original_cloud_synths=(minimax_runtime.synthesize_speech_minimax,
                           cosyvoice_runtime.synthesize_speech_cosyvoice)
    cloud_calls=[]
    try:
        minimax_runtime.synthesize_speech_minimax=lambda **kwargs:cloud_calls.append(("minimax",kwargs)) or "/tmp/mini.mp3"
        cosyvoice_runtime.synthesize_speech_cosyvoice=lambda **kwargs:cloud_calls.append(("cosyvoice",kwargs)) or "/tmp/cosy.wav"
        cloud_manager=LiveManager({"voice_id":"fallback","minimax_voice_config":{"api_key":"m"},
                                   "cosyvoice_voice_config":{"api_key":"c"}})
        cloud_manager.host_streamer=TTSStreamer()
        timeouts=[]
        cloud_manager._run_with_timeout=lambda func,timeout,description:(timeouts.append((timeout,description)),func())[1]
        cloud_manager._handle_tts_speak({"text":"云端一","voice_infer_version":"minimax",
            "voice_general_config":{"minimax":{"minimax_voice_id":"mini-id"}}})
        cloud_manager._handle_tts_speak({"text":"云端二","voice_infer_version":"cosyvoice",
            "voice_general_config":{"cosyvoice":{"cosyvoice_voice_id":"cosy-id"}}})
        assert [item[0] for item in cloud_calls]==["minimax","cosyvoice"]
        assert cloud_calls[0][1]["voice_id"]=="mini-id"
        assert cloud_calls[1][1]["voice_id"]=="cosy-id"
        assert timeouts==[(90.0,"Minimax TTS"),(90.0,"CosyVoice TTS")]
    finally:
        minimax_runtime.synthesize_speech_minimax,cosyvoice_runtime.synthesize_speech_cosyvoice=original_cloud_synths
    class NearStreamer(TTSStreamer):
        def get_near_audio_clip(self):return ("/tmp/ref.wav","参考文本")
    near_manager=LiveManager({"voice_id":"primary","use_near_audio_clone":True})
    near_manager.host_streamer=NearStreamer();near_calls=[];local_calls=[]
    near_manager._run_with_timeout=lambda func,timeout,description:(near_calls.append((timeout,description)),func())[1]
    near_manager._synthesize_with_near_clone=lambda **kwargs:"/tmp/near.wav"
    near_manager._ensure_voice_synthesizer=lambda voice_id,version:TTSSynth()
    near_manager._handle_tts_speak({"text":"弹幕近场","queue":"danmu"})
    near_manager._handle_tts_speak({"text":"普通本地","queue":"normal"})
    assert near_calls[0]==(120.0,"近场克隆 TTS")
    assert [item[0] for item in near_manager.host_streamer.items]==["/tmp/near.wav","/tmp/test.wav"]
    class SeekStreamer(TTSStreamer):
        def __init__(self):super().__init__();self.seeks=[]
        def schedule_seek_after_interaction(self,start_ms):self.seeks.append(start_ms)
    class ProductSession:
        def __init__(self):self.audio_product_map={}
        def _remember_audio_product(self,audio,product):self.audio_product_map[audio]=product
    post_manager=LiveManager({"voice_id":"primary"})
    post_manager.host_streamer=SeekStreamer();post_manager._session=ProductSession()
    post_manager._ensure_voice_synthesizer=lambda voice_id,version:TTSSynth()
    post_manager._handle_tts_speak({"text":"商品播报","queue":"normal",
                                    "product_index":7,"seek_after_ms":"2345"})
    assert post_manager._session.audio_product_map=={"/tmp/test.wav":7}
    assert post_manager.host_streamer.seeks==[2345]
    timeout_manager=LiveManager({})
    assert timeout_manager._run_with_timeout(lambda:"完成",.2,"成功任务")=="完成"
    def timeout_error():raise ValueError("原始异常")
    try:timeout_manager._run_with_timeout(timeout_error,.2,"异常任务")
    except ValueError as exc:assert str(exc)=="原始异常"
    else:raise AssertionError("_run_with_timeout did not re-raise worker exception")
    release_timeout=threading.Event()
    try:timeout_manager._run_with_timeout(lambda:release_timeout.wait(1),.01,"慢任务")
    except TimeoutError as exc:assert str(exc)=="慢任务超时（0.01秒）"
    else:raise AssertionError("_run_with_timeout did not time out")
    finally:release_timeout.set()
    stale_manager=LiveManager({"voice_id":"primary"})
    stale_manager.host_streamer=TTSStreamer()
    class StaleSynth:
        def synthesize(self,text,**kwargs):
            stale_manager._normal_audio_epoch+=1
            return "/tmp/stale.wav"
    stale_manager._ensure_voice_synthesizer=lambda voice_id,version:StaleSynth()
    stale_manager._handle_tts_speak({"text":"过期普通音频","queue":"normal"})
    assert stale_manager.host_streamer.items==[]
    class ClearStreamer:
        def __init__(self):self.cleared=0
        def clear_audio_queues(self):self.cleared+=1
    clear_manager=LiveManager({"voice_id":"primary"})
    clear_manager.host_streamer=ClearStreamer()
    clear_manager._enqueue_audio_task({"payload":{"queue":"normal"}},"normal")
    clear_manager._enqueue_audio_task({"payload":{"queue":"danmu"}},"danmu")
    clear_manager._handle_clear_normal_queues({})
    assert clear_manager._normal_audio_epoch==1
    assert clear_manager.host_streamer.cleared==1
    assert clear_manager._pending_audio_snapshot()=={"normal":0,"danmu":1}
    danmu_task,danmu_queue=clear_manager._take_next_audio_task()
    assert danmu_task is not None and danmu_queue=="danmu"
    clear_manager._adjust_pending_audio("danmu",-1)
    clear_manager._handle_clear_normal_queues({"new_image_model_id":"image-2",
                                               "new_voice_id":"voice-2","clear_queues":True})
    switch_task,switch_queue=clear_manager._take_next_audio_task()
    assert switch_queue=="normal"
    assert switch_task=={"id":0,"session_id":None,"seq":0,"type":"switch_model","payload":{
        "new_image_model_id":"image-2","new_voice_id":"voice-2","clear_queues":False}}
    clear_manager._adjust_pending_audio("normal",-1)
    with tempfile.TemporaryDirectory() as switch_root:
        model_dir=Path(switch_root)/"image-2";model_dir.mkdir()
        class SwitchStreamer(ClearStreamer):
            def __init__(self):super().__init__();self.models=[]
            def switch_image_model(self,path):self.models.append(path)
        switch_manager=LiveManager({"image_base_dir":switch_root,"voice_id":"voice-1"})
        switch_manager.host_streamer=SwitchStreamer();voice_switches=[]
        switch_manager._ensure_voice_synthesizer=lambda voice_id,version,force_refresh=False:voice_switches.append(
            (voice_id,version,force_refresh)) or object()
        switch_manager._handle_switch_model({"new_image_model_id":"image-2","new_voice_id":"voice-2",
            "voice_infer_version":"v2","clear_queues":True})
        assert switch_manager.host_streamer.models==[str(model_dir)]
        assert voice_switches==[("voice-2","v2",True)]
        assert (switch_manager._primary_voice_id,switch_manager.voice_infer_version)==("voice-2","v2")
        assert switch_manager.host_streamer.cleared==1
    task_manager=LiveManager({"script_audio_files":["/tmp/a.wav","/tmp/b.wav"]})
    task_manager.host_streamer=TTSStreamer()
    task_manager._create_silent_audio=lambda duration:f"/tmp/pause-{duration}.wav"
    task_manager._handle_pause({"duration":"1.5","queue":"danmu"})
    task_manager._handle_pause({"duration":0})
    task_manager._handle_play_audio_index({"index":"1","queue":"normal","target_face_index":"3"})
    task_manager._handle_play_audio_index({"index":-1})
    assert task_manager.host_streamer.items==[
        ("/tmp/pause-1.5.wav",{"queue_name":"danmu","use_silent_features":True}),
        ("/tmp/b.wav",{"queue_name":"normal","target_face_index":3}),
    ]
    startup_manager=LiveManager({"interaction_config":{},
        "minimax_voice_config":{"api_key":"mini"},
        "cosyvoice_voice_config":{"api_key":"cosy"}})
    startup_runtime=object();captured_start={}
    def fake_start_live(**kwargs):
        captured_start.update(kwargs);startup_manager._runtime=startup_runtime;return True
    startup_manager._start_audio_worker=lambda:None
    startup_manager._prepare_platform_control=lambda session:None
    original_parent_start=DigitalLiveManager.start_live
    DigitalLiveManager.start_live=lambda _self,**kwargs:fake_start_live(**kwargs)
    try:
        assert startup_manager.start_local_runtime(model_id="image-1",voice_id="voice-start",
            voice_infer_version="v3",language="en-US",voice_speed=1.4,use_audio_cache=False,
            use_near_audio_clone=True) is True
    finally:
        DigitalLiveManager.start_live=original_parent_start
    assert startup_manager.host_streamer is startup_runtime
    assert (startup_manager._primary_voice_id,startup_manager.voice_infer_version,
            startup_manager.language,startup_manager.voice_speed)==("voice-start","v3","en-US",1.4)
    assert startup_manager.use_audio_cache is False and startup_manager.use_near_audio_clone is True
    assert captured_start["config"]["voice_id"]=="voice-start"
    assert captured_start["config"]["voice_infer_version"]=="v3"
    assert captured_start["minimax_voice_config"]=={"api_key":"mini"}
    assert captured_start["cosyvoice_voice_config"]=={"api_key":"cosy"}
    assert startup_manager._session is not None
    startup_manager.stop_local_session();startup_manager._runtime=None;startup_manager.host_streamer=None
    class Streamer:
        def get_queue_lengths(self):return {"normal":"2","danmu":3,"manual":9}
    manager.host_streamer=Streamer();manager._adjust_pending_audio("normal",2);manager._adjust_pending_audio("danmu",1)
    assert manager.get_queue_lengths()=={"normal":2,"danmu":3,"pending_normal":2,"pending_danmu":1}
    class BrokenStreamer:
        def get_queue_lengths(self):raise RuntimeError("closed")
    manager.host_streamer=BrokenStreamer()
    assert manager.get_queue_lengths()=={"normal":0,"danmu":0,"pending_normal":2,"pending_danmu":1}
    priority_manager=LiveManager({})
    priority_manager._enqueue_audio_task(
        {"type":"tts_speak","payload":{"text":"普通","queue":"normal"}},"normal")
    priority_manager._enqueue_audio_task(
        {"type":"tts_speak","payload":{"text":"弹幕","queue":"danmu"}},"danmu")
    priority_manager._enqueue_audio_task(
        {"type":"tts_speak","payload":{"text":"未知","queue":"manual"}},"manual")
    first,first_queue=priority_manager._take_next_audio_task()
    second,second_queue=priority_manager._take_next_audio_task()
    third,third_queue=priority_manager._take_next_audio_task()
    assert (first["payload"]["text"],first_queue)==("弹幕","danmu")
    assert (second["payload"]["text"],second_queue)==("普通","normal")
    assert (third["payload"]["text"],third_queue)==("未知","normal")
    assert priority_manager._audio_task_queue_name({"payload":{"queue":"manual"}})=="normal"
    assert priority_manager._audio_task_queue_name({"payload":None})=="normal"
    priority_manager._adjust_pending_audio(first_queue,-1)
    priority_manager._adjust_pending_audio(second_queue,-1)
    priority_manager._adjust_pending_audio(third_queue,-1)
    assert priority_manager._pending_audio_snapshot()=={"normal":0,"danmu":0}
    worker_manager=LiveManager({})
    worker_manager._adjust_pending_audio("normal",1)
    worker_manager._adjust_pending_audio("danmu",1)
    worker_items=[({"id":"bad"},"normal"),({"id":"good"},"danmu")]
    worker_calls=[]
    def take_worker_item():
        if worker_items:return worker_items.pop(0)
        worker_manager._audio_worker_stop.set();return None,None
    worker_manager._take_next_audio_task=take_worker_item
    def execute_worker_item(task):
        worker_calls.append(task["id"])
        if task["id"]=="bad":raise RuntimeError("合成失败")
    worker_manager._execute_task_inline=execute_worker_item
    worker_manager._audio_worker_loop()
    assert worker_calls==["bad","good"]
    assert worker_manager._pending_audio["normal"]==0
    assert worker_manager._pending_audio["danmu"]==0
    manager.stop_local_runtime()

def verify_face_hand_manager():
    from recovered.face_hand_live_manager import (
        BROADCAST_QUEUE_TARGET as FACE_HAND_BROADCAST_QUEUE_TARGET,
        INTERACTION_OFF_SECONDS,
        INTERACTION_MESSAGE_CAP,
        InteractionMessage,
        FaceHandLiveManager,
    )
    assert FACE_HAND_BROADCAST_QUEUE_TARGET == 800
    assert INTERACTION_OFF_SECONDS == 100000
    assert INTERACTION_MESSAGE_CAP == 500
    assert FaceHandLiveManager._interaction_enabled(99999) is True
    assert FaceHandLiveManager._interaction_enabled(100000) is False
    assert FaceHandLiveManager._interaction_enabled("42") is True
    class Player:
        is_playing=True; last_error=None
        def __init__(self):self.phases=[]
        def get_queue_lengths(self): return {"normal":2}
        def clear_audio_queues(self):pass
        def play_face_clip(self):self.phases.append("face");return True
        def play_hand_clip(self):self.phases.append("hand");return True
    manager=FaceHandLiveManager({"voice_base_dir":"."}); manager._player=Player()
    tick_manager=FaceHandLiveManager({"voice_base_dir":"."})
    tick_calls=[]
    tick_manager._enter_face_phase=lambda group_index:tick_calls.append(("face",group_index)) or True
    tick_manager._drain_manual_and_simulated=lambda:tick_calls.append("manual")
    tick_manager._tick_interactions=lambda:tick_calls.append("interactions")
    tick_manager._tick_broadcast=lambda:tick_calls.append("broadcast")
    tick_manager._tick()
    assert tick_calls==[("face",0)]
    tick_manager._tick()
    assert tick_calls==[("face",0),"manual","interactions","broadcast"]
    tick_manager._tick_lock.acquire()
    tick_manager._tick()
    tick_manager._tick_lock.release()
    assert tick_calls==[("face",0),"manual","interactions","broadcast"]
    image_items=manager._build_product_image_items([
        {"itemPic":" //img.example/a.jpg ","itemName":" 商品 A ","itemId":" 101 "},
        {"item_pic":"https://img.example/b.jpg","item_name":"商品 B","item_id":202},
        "invalid",
    ])
    assert image_items==[
        {"itemPic":"https://img.example/a.jpg","itemName":"商品 A","itemId":"101"},
        {"itemPic":"https://img.example/b.jpg","itemName":"商品 B","itemId":"202"},
    ]
    class ProductPopup:
        def __init__(self):self.preloaded=[];self.shown=[];self.greenscreen_count=0
        def preload_products(self,items,**kwargs):self.preloaded.append((items,kwargs))
        def show_product(self,**kwargs):self.shown.append(kwargs)
        def show_greenscreen(self):self.greenscreen_count+=1
    popup=ProductPopup()
    manager._live_config={"enable_product_image_sync":True}
    manager.product_image_items=image_items;manager._product_popup=popup
    manager._sync_product_image(0);manager._sync_product_image(0);manager._sync_product_image(1)
    assert popup.shown==[
        {"goods_id":101,"item_pic":"https://img.example/a.jpg","item_name":"商品 A"},
        {"goods_id":202,"item_pic":"https://img.example/b.jpg","item_name":"商品 B"},
    ]
    import recovered.taobao_live_control as taobao_live_control
    original_get_taobao_controller=taobao_live_control.get_taobao_controller
    class ProductController:
        def __init__(self,connected=True):self._connected=connected;self.goods=[];self.cleared=0
        def connected(self):return self._connected
        def set_active_goods(self,goods_id):self.goods.append(goods_id)
        def clear_active_goods(self):self.cleared+=1
    product_controller=ProductController()
    taobao_live_control.get_taobao_controller=lambda:product_controller
    original_sync_product_image=manager._sync_product_image
    synced_images=[]
    manager._sync_product_image=lambda product_index:synced_images.append(product_index)
    manager._live_config={"enable_taobao_product_sync":True}
    manager._sync_product_ui(-4);manager._sync_product_ui(0);manager._sync_product_ui(3)
    assert product_controller.goods==[0,3]
    assert synced_images==[0,0,3]
    import recovered.product_image_popup as product_image_popup
    original_get_product_image_popup=product_image_popup.get_product_image_popup
    product_image_popup.get_product_image_popup=lambda:popup
    manager._live_config={"enable_taobao_product_sync":True,"enable_product_image_sync":True}
    manager._synced_goods_id=3;manager._synced_image_goods_id=202
    manager._pause_product_ui()
    assert product_controller.cleared==1
    assert popup.greenscreen_count==1
    assert manager._synced_goods_id is None
    assert manager._synced_image_goods_id is None
    product_image_popup.get_product_image_popup=original_get_product_image_popup
    taobao_live_control.get_taobao_controller=original_get_taobao_controller
    manager._sync_product_image=original_sync_product_image
    class PlayingAudio:
        def __init__(self,path):self.path=path
        def get_current_playing_audio_path(self):return self.path
    synced=[]
    manager._sync_product_ui=lambda product_index:synced.append(product_index)
    manager.host_streamer=PlayingAudio("/tmp/product-2.wav")
    manager._audio_product_map={"/tmp/product-2.wav":2,"<silence>":9}
    manager.phase="face"
    manager._sync_playing_product()
    manager.phase="hand"
    manager._sync_playing_product()
    manager.host_streamer.path="<silence>"
    manager._sync_playing_product()
    manager.host_streamer.path="/tmp/unmapped.wav"
    manager._sync_playing_product()
    assert synced==[2]
    manager.minimax_voice_config={"api_key":"mini","model":"speech"}
    manager.cosyvoice_voice_config={"api_key":"cosy","region":"international"}
    selected_voices={
        "minimax":{"minimax_voice_id":"  mini-selected  ","ignored":True},
        "cosyvoice":{"cosyvoice_voice_id":"  cosy-selected  ","ignored":True},
    }
    minimax_runtime=manager._build_minimax_runtime_config(selected_voices)
    cosyvoice_runtime=manager._build_cosyvoice_runtime_config(selected_voices)
    assert minimax_runtime=={
        "api_key":"mini","model":"speech","minimax_voice_id":"mini-selected"
    }
    assert cosyvoice_runtime=={
        "api_key":"cosy","region":"international",
        "base_http_api_url":"https://dashscope-intl.aliyuncs.com/api/v1",
        "base_websocket_api_url":"wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        "http_url":"https://dashscope-intl.aliyuncs.com/api/v1",
        "websocket_url":"wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        "cosyvoice_voice_id":"cosy-selected",
    }
    assert manager.minimax_voice_config=={"api_key":"mini","model":"speech"}
    assert manager.cosyvoice_voice_config=={"api_key":"cosy","region":"international"}
    class FaceTTSPlayer:
        is_playing=True
        def __init__(self):self.items=[]
        def add_audio_to_queue(self,path,queue_name=None):self.items.append((path,queue_name))
    provider_manager=FaceHandLiveManager({"voice_base_dir":"."})
    provider_manager._player=FaceTTSPlayer();provider_manager._primary_voice_id="fallback"
    provider_manager.minimax_voice_config={"api_key":"mini"}
    provider_manager.cosyvoice_voice_config={"api_key":"cosy"}
    provider_manager._run_with_timeout=lambda call,timeout,description:call()
    import recovered.minimax as face_minimax
    import recovered.cosyvoice as face_cosyvoice
    original_face_cloud=(face_minimax.synthesize_speech_minimax,
                         face_cosyvoice.synthesize_speech_cosyvoice)
    face_cloud_calls=[]
    face_minimax.synthesize_speech_minimax=lambda **kwargs:(
        face_cloud_calls.append(("minimax",kwargs)) or "/tmp/face-mini.mp3")
    face_cosyvoice.synthesize_speech_cosyvoice=lambda **kwargs:(
        face_cloud_calls.append(("cosyvoice",kwargs)) or "/tmp/face-cosy.mp3")
    try:
        provider_manager._handle_tts_speak({
            "text":"云端一","queue":"danmu","voice_infer_version":"minimax",
            "voice_speed":1.3,"language":"en-US","use_audio_cache":False,
            "voice_general_config":{"minimax":{"minimax_voice_id":"mini-id"}},
        })
        provider_manager._handle_tts_speak({
            "text":"云端二","voice_infer_version":"cosyvoice",
            "voice_general_config":{"cosyvoice":{"cosyvoice_voice_id":"cosy-id"}},
        })
    finally:
        (face_minimax.synthesize_speech_minimax,
         face_cosyvoice.synthesize_speech_cosyvoice)=original_face_cloud
    assert provider_manager._player.items==[
        ("/tmp/face-mini.mp3","danmu"),("/tmp/face-cosy.mp3","normal")
    ]
    assert face_cloud_calls[0]==("minimax",{
        "text":"云端一","voice_id":"mini-id",
        "minimax_config":{"api_key":"mini","minimax_voice_id":"mini-id"},
        "speed":1.3,"language":"en-US","use_cache":False,
    })
    assert face_cloud_calls[1][0]=="cosyvoice"
    assert face_cloud_calls[1][1]["voice_id"]=="cosy-id"
    assert face_cloud_calls[1][1]["cosyvoice_config"]["api_key"]=="cosy"
    local_calls=[]
    class FaceLocalSynth:
        def synthesize(self,**kwargs):local_calls.append(kwargs);return "/tmp/face-local.wav"
    provider_manager._ensure_voice_synthesizer=lambda voice_id,version:FaceLocalSynth()
    provider_manager._normal_audio_epoch=3
    provider_manager._handle_tts_speak({
        "text":"过期商品话术","queue":"normal","epoch":2,
        "voice_id":"local-id","voice_infer_version":"v2","product_index":7,
    })
    assert provider_manager._player.items==[
        ("/tmp/face-mini.mp3","danmu"),("/tmp/face-cosy.mp3","normal")
    ]
    assert provider_manager._audio_product_map=={}
    provider_manager._handle_tts_speak({
        "text":"有效商品话术","queue":"normal","epoch":3,
        "voice_id":"local-id","voice_infer_version":"v2","product_index":"7",
    })
    assert provider_manager._player.items[-1]==("/tmp/face-local.wav","normal")
    assert provider_manager._audio_product_map=={"/tmp/face-local.wav":7}
    assert local_calls[-1]=={
        "text":"有效商品话术","speed":1.1,"language":"zh-CN","use_cache":True
    }
    worker_manager=FaceHandLiveManager({})
    worker_manager._adjust_pending_audio("normal",2)
    worker_items=[
        ({"type":"tts_speak","payload":{"id":"bad"}},"normal"),
        ({"type":"tts_speak","payload":{"id":"good"}},"normal"),
    ]
    worker_calls=[]
    def take_face_worker_item():
        if worker_items:return worker_items.pop(0)
        worker_manager._audio_stop.set();return None,None
    def handle_face_worker_item(payload):
        worker_calls.append(payload["id"])
        if payload["id"]=="bad":raise RuntimeError("人脸合成失败")
    worker_manager._take_next_audio_task=take_face_worker_item
    worker_manager._handle_tts_speak=handle_face_worker_item
    worker_manager._audio_worker_loop()
    assert worker_calls==["bad","good"]
    assert worker_manager._pending_audio["normal"]==0
    groups=manager._build_product_groups([
        {"product_index":"7","content":" 商品资料 ","scripts":"第一句。{助:助播句}{停:1.5}"},
        {"product_index":"bad","itemName":"备用商品","scripts":"第二句。"},
        {"scripts":"   "},
        "坏项",
    ])
    assert groups[0]["product_index"]==7 and groups[0]["product_info"]==" 商品资料 "
    assert [item["type"] for item in groups[0]["items"]]==["host","assistant","pause"]
    assert groups[0]["items"][0]["content"]=="第一句。"
    assert groups[0]["items"][1]["content"]=="助播句"
    assert all(item["product_index"]==7 for item in groups[0]["items"])
    assert groups[1]["product_index"]==1 and groups[1]["product_info"]=="备用商品"
    assert len(groups)==2
    manager._emit_script_item({"type":"host","content":"  主播正文  ","product_index":7})
    host_task,host_queue=manager._take_next_audio_task()
    assert host_queue=="normal" and host_task["payload"]=={
        "text":"主播正文","queue":"normal","product_index":7,"epoch":0}
    manager._adjust_pending_audio("normal",-1)
    manager._emit_script_item({"type":"assistant","content":"不应进入队列","product_index":7})
    manager._emit_script_item({"type":"pause","duration":1.5,"product_index":7})
    assert manager._take_next_audio_task()==(None,None)
    manager.product_script_groups=groups;manager._product_script_groups=groups
    assert manager._enter_face_phase(0) is True
    assert (manager.phase,manager._pending_group,manager.current_product_index,manager.product_item_cursor)==("face",0,-1,0)
    manager._on_face_done()
    assert (manager.phase,manager.current_product_index,manager.product_item_cursor)==("hand",0,0)
    emitted=[];manager._emit_script_item=lambda item:emitted.append(item)
    original_get_queue_lengths=manager.get_queue_lengths
    manager.get_queue_lengths=lambda:{"normal":0,"pending_normal":0}
    manager._tick_broadcast()
    assert emitted==groups[0]["items"] and manager.phase=="face" and manager._pending_group==1
    manager.get_queue_lengths=original_get_queue_lengths
    assert manager.request_manual_speak("  手动一  ") is True
    assert manager.request_manual_speak("手动二") is True
    assert manager.request_simulated_question("  问题一  ") is True
    assert manager.request_simulated_question("问题二") is True
    manager._drain_manual_and_simulated()
    manual_one,name=manager._take_next_audio_task(); manual_two,name_two=manager._take_next_audio_task()
    assert (name,manual_one["payload"]["text"])==("danmu","手动一")
    assert (name_two,manual_two["payload"]["text"])==("danmu","手动二")
    assert all(isinstance(item,InteractionMessage) for item in manager.interaction_messages[-2:])
    assert [(item.msg_type,item.nickname,item.content,item.processed)
            for item in manager.interaction_messages[-2:]]==[
                ("弹幕","模拟用户","问题一",False),
                ("弹幕","模拟用户","问题二",False),
            ]
    assert not manager._manual_speaks and not manager._simulated_questions
    manager.interaction_messages.clear()
    manager.product_script_groups=[{"product_info":" 当前商品资料 "},{"product_info":" 待切商品资料 "}]
    manager.current_product_index=0; manager._pending_group=1; manager.product_info="全局资料"
    assert manager._active_product_info()=="当前商品资料"
    manager.current_product_index=-1
    assert manager._active_product_info()=="待切商品资料"
    manager._pending_group=99
    assert manager._active_product_info()=="全局资料"
    manager._adjust_pending_audio("danmu",-2)
    manager._adjust_pending_audio("manual",1)
    assert manager.get_queue_lengths()=={"normal":2,"manual":1,"danmu":0}
    manager.llm_config={"provider":"test"};manager._interaction_llm_executor=None
    import recovered.llm_reply as interaction_reply
    original_interaction_replies=(interaction_reply.reply_danmu,interaction_reply.reply_enter,
                                  interaction_reply.reply_follow,interaction_reply.reply_like)
    interaction_calls=[]
    try:
        interaction_reply.reply_danmu=lambda *args:interaction_calls.append(("comment",args)) or "你好，测试用户"
        interaction_reply.reply_enter=lambda *args:interaction_calls.append(("enter",args)) or "欢迎进入"
        interaction_reply.reply_follow=lambda *args:interaction_calls.append(("follow",args)) or "感谢关注"
        interaction_reply.reply_like=lambda *args:interaction_calls.append(("like",args)) or "感谢支持"
        manager._live_config={};manager.product_info="商品资料";manager.qa_info="问答资料";manager.special_instructions="特别要求"
        manager.submit_danmu({"type":"comment","nickname":"测试用户","content":"你好"}); manager._tick_interactions()
        task,name=manager._take_next_audio_task()
        assert name=="danmu" and task["payload"]["text"]=="你好，测试用户"
        assert interaction_calls.pop()==("comment",("测试用户","你好","商品资料","问答资料","特别要求"))
        manager.interaction_messages.clear()
        for index in range(25):
            manager.submit_danmu({"type":"comment","nickname":f"用户{index}","content":"批量"})
        manager._tick_interactions()
        assert sum(item.processed for item in manager.interaction_messages)==20
        assert [manager._take_next_audio_task()[1] for _ in range(20)]==["danmu"]*20
        interaction_calls.clear();manager.interaction_messages.clear()
        for msg_type in ("gift","follow","进入直播间"):
            manager.submit_danmu({"type":msg_type,"nickname":msg_type,"content":"互动"})
        manager._tick_interactions()
        assert [kind for kind,_ in interaction_calls]==["enter","like","follow"]
        assert [manager._take_next_audio_task()[0]["payload"]["text"] for _ in range(3)]==[
            "欢迎进入","感谢支持","感谢关注"]
        manager.submit_danmu({"type":"enter","nickname":"进入直播间","content":"再次进入"})
        manager._tick_interactions()
        assert manager._take_next_audio_task()==(None,None)
    finally:
        (interaction_reply.reply_danmu,interaction_reply.reply_enter,
         interaction_reply.reply_follow,interaction_reply.reply_like)=original_interaction_replies
    manager._submit_interaction_llm(kind="comment",llm_call=lambda:"  同步回复  ")
    task,name=manager._take_next_audio_task()
    assert name=="danmu" and task["payload"]["text"]=="同步回复"
    manager._submit_interaction_llm(kind="comment",llm_call=lambda:"   ")
    assert manager._take_next_audio_task()==(None,None)
    manager._submit_interaction_llm(kind="gift",
        llm_call=lambda:(_ for _ in ()).throw(RuntimeError("互动失败")))
    assert manager.last_error is None
    class ImmediateExecutor:
        def submit(self,callable_): callable_(); return object()
    manager._interaction_llm_executor=ImmediateExecutor()
    manager._submit_interaction_llm(kind="like",llm_call=lambda:"异步回复")
    task,name=manager._take_next_audio_task()
    assert name=="danmu" and task["payload"]["text"]=="异步回复"
    import recovered.llm_reply as face_llm_reply
    original_generate_text_reply=face_llm_reply.generate_text_reply
    control_replies=[]; calls=[]
    manager.qa_info="问答资料"; manager.special_instructions="特别要求"
    original_send_control_reply=manager._send_taobao_control_reply
    manager._send_taobao_control_reply=lambda text:control_replies.append(text) or True
    try:
        face_llm_reply.generate_text_reply=lambda *args:calls.append(args) or " 原始回答 "
        assert manager._submit_ai_control_reply("小云","问题","商品资料") is None
        assert calls.pop()==("小云","问题","商品资料","问答资料","特别要求")
        assert control_replies.pop()=="@小云 原始回答"
        face_llm_reply.generate_text_reply=lambda *args:""
        manager._submit_ai_control_reply("小云","问题","商品资料")
        assert control_replies.pop()=="@小云 收到，稍等主播回复哦"
        face_llm_reply.generate_text_reply=lambda *args:(_ for _ in ()).throw(RuntimeError("模型异常"))
        manager._submit_ai_control_reply("小云","问题","商品资料")
        assert not control_replies
        manager._player.is_playing=False
        face_llm_reply.generate_text_reply=lambda *args:"停止后不发送"
        manager._submit_ai_control_reply("小云","问题","商品资料")
        assert not control_replies
        manager._player.is_playing=True
    finally:
        face_llm_reply.generate_text_reply=original_generate_text_reply
        manager._send_taobao_control_reply=original_send_control_reply
    from recovered import taobao_live_control as face_taobao_control
    original_get_controller=face_taobao_control.get_taobao_controller
    class FaceController:
        def __init__(self,connected=True,result=True,error=None):
            self._connected=connected;self.result=result;self.error=error;self.sent=[]
        def connected(self):return self._connected
        def send_comment(self,text):
            self.sent.append(text)
            if self.error:raise self.error
            return self.result
    try:
        controller=FaceController(connected=False)
        face_taobao_control.get_taobao_controller=lambda:controller
        manager.reply_blocked_keywords=[]
        assert manager._send_taobao_control_reply(" 回复 ") is False and not controller.sent
        controller=FaceController(result=True)
        face_taobao_control.get_taobao_controller=lambda:controller
        assert manager._send_taobao_control_reply(" 回复 ") is True and controller.sent==["回复"]
        manager.reply_blocked_keywords=["禁词"]
        assert manager._send_taobao_control_reply("含有禁词") is False
        controller=FaceController(error=RuntimeError("发送失败"))
        face_taobao_control.get_taobao_controller=lambda:controller
        manager.reply_blocked_keywords=[]
        assert manager._send_taobao_control_reply("异常回复") is False
    finally:face_taobao_control.get_taobao_controller=original_get_controller

def verify_face_hand_player_av_queue():
    import numpy as np
    from recovered.face_hand_player import FaceHandVideoStreamManager
    player=FaceHandVideoStreamManager(face_videos=[],hand_videos=[],fps=25)
    frame=np.zeros((4,4,3),np.uint8); audio=np.arange(8,dtype=np.float32)
    assert player._put_av(frame,audio,"voice.wav",meta="face")
    payload,status=player._audio_callback(None,8,None,None)
    assert np.array_equal(np.frombuffer(payload,np.float32),audio)
    assert player.get_current_playing_audio_path()=="voice.wav"
    assert player._latest_frame is frame
    player._put_av(frame,audio,"voice.wav"); player._drain_av_queue()
    assert not player._av_queue

def verify_language_and_live_helpers():
    import io
    import wave
    from recovered.tools.llm import llm_reply
    from recovered.live import live_manager
    assert llm_reply._resolve_language_code("[TARGET_LANGUAGE=vi-VN] x") == "vi-VN"
    assert llm_reply._resolve_language_code("", "en") == "en-US"
    assert llm_reply._is_multilingual_mode("vi-VN") and not llm_reply._is_multilingual_mode("zh-CN")
    assert llm_reply._is_vietnamese_language("vi")
    assert "Vietnamese" in llm_reply._translation_prompt("vi-VN")
    assert "TARGET_LANGUAGE=vi-VN" in llm_reply._language_rules("vi")
    assert llm_reply._extra_persona("[TARGET_LANGUAGE=en-US]\ncheerful") == "cheerful"
    prompt=llm_reply._append_extra_instructions("base", "en", "[TARGET_LANGUAGE=en-US]\ncheerful")
    assert "base" in prompt and "cheerful" in prompt and "TARGET_LANGUAGE=en-US" in prompt
    assert "Lan" in llm_reply._fallback_reply("vi", "enter", "Lan")
    assert live_manager._is_vietnamese_language("vi_VN")
    assert [live_manager._to_chinese_num(value) for value in (0,10,11,20,21)] == ["零","十","十一","二十","二十一"]
    wav_bytes=live_manager._pcm_to_wav_bytes(b"\x00\x00\x01\x00",8000)
    with wave.open(io.BytesIO(wav_bytes),"rb") as stream:
        assert (stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getnframes())==(1,2,8000,2)
    from recovered.live import face_hand_live_manager
    assert face_hand_live_manager._is_entrance_message_content("Alice joined the live")
    assert face_hand_live_manager._normalize_interaction_msg_type("chat", "") == "弹幕"
    assert face_hand_live_manager._normalize_interaction_msg_type("chat", "进入了直播间") == "进入直播间"
    assert face_hand_live_manager._normalize_interaction_msg_type("关注主播", "") == "关注"
    assert face_hand_live_manager._normalize_interaction_msg_type("like", "") == "礼物"
    assert face_hand_live_manager._normalize_interaction_msg_type("COMMENT", "") == "COMMENT"
    helper_modules=(
        "recovered.bin.image_infer_origin_frame.tools.frame_player.player_cam",
        "recovered.bin.image_infer_origin_frame.tools.frame_player.player_main",
        "recovered.bin.image_infer_v2.tools.frame_player.player_cam",
        "recovered.bin.image_infer_v2.tools.frame_player.player_main",
    )
    for name in helper_modules:
        module=importlib.import_module(name)
        assert callable(module._apply_kt_overlay) and callable(module._resolve_output_sample_rate)
    for name in ("recovered.bin.image_infer_v2.tools.realtime_face_reader.realtime_face_reader",
                 "recovered.bin.image_infer_v2.tools.rtmp_face_reader.rtmp_face_reader"):
        module=importlib.import_module(name)
        assert callable(module._env_int) and callable(module._env_float)

def verify_video_player_stream_helpers():
    import io
    import contextlib
    from recovered.bin.video_player import infer_api as video
    assert video._parse_fps_value("30000/1001") == 30000/1001
    assert video._parse_fps_value("25") == 25.0
    assert video._parse_fps_value("0/0") == float(video.DEFAULT_FPS)
    assert video._parse_fps_value("not-a-rate") == float(video.DEFAULT_FPS)
    class Audio:
        def get_default_output_device_info(self): return {"defaultSampleRate":48000,"index":2}
        def is_format_supported(self,rate,**kwargs): return rate==48000
    old_pyaudio=sys.modules.get("pyaudio");sys.modules["pyaudio"]=types.SimpleNamespace(paFloat32=1)
    try: assert video._resolve_output_sample_rate(Audio())==48000
    finally:
        if old_pyaudio is None: sys.modules.pop("pyaudio",None)
        else: sys.modules["pyaudio"]=old_pyaudio
    class Pipe:
        def __init__(self): self.lines=iter((b"first\n",b"second\n",b""));self.closed=False
        def readline(self): return next(self.lines)
        def close(self): self.closed=True
    pipe=Pipe(); output=io.StringIO()
    with contextlib.redirect_stdout(output): video._drain_process_pipe(pipe,"[p] ")
    assert output.getvalue()=="[p] first\n[p] second\n" and pipe.closed
    class Process:
        def __init__(self): self.actions=[];self.waits=0
        def poll(self): return None
        def terminate(self): self.actions.append("terminate")
        def wait(self,timeout):
            self.waits+=1
            if self.waits==1: raise subprocess.TimeoutExpired("ffmpeg",timeout)
            self.actions.append(("wait",timeout));return 0
        def kill(self): self.actions.append("kill")
    process=Process();video._close_stream_process(process,None)
    assert process.actions==["terminate","kill",("wait",1)]

def verify_taobao_private_helpers():
    import os
    import recovered.taobao_live_control as taobao
    assert taobao._decode_cookie_value("%E6%B5%8B%E8%AF%95") == "测试"
    assert taobao._decode_cookie_value(r"hello\u4e16\u754c") == "hello世界"
    assert taobao._browser_context_kwargs(use_storage=False)=={"viewport":{"width":1440,"height":900}}
    payload={"data":{"result":{"list":[{"liveId":"1","status":"未开播"},{"liveId":"2","status":"living"}]}}}
    lives=taobao._parse_live_item_list(payload);assert len(lives)==2
    assert taobao._parse_live_item_list("callback("+json.dumps(payload,ensure_ascii=False)+")")==lives
    assert taobao._pick_latest_unpublished_live(lives)["liveId"]=="1"
    ordered=[{"liveId":"old","status":"0","startTime":"2025-01-01"},
             {"liveId":"new","status":"0","startTime":"2026-01-01"}]
    assert taobao._pick_latest_unpublished_live(ordered)["liveId"]=="new"
    old=os.environ.get("CHROME_PATH")
    with tempfile.TemporaryDirectory() as directory:
        executable=Path(directory)/"chrome";executable.write_text("",encoding="utf-8")
        os.environ["CHROME_PATH"]=str(executable)
        try: assert taobao._resolve_chrome_path()==str(executable)
        finally:
            if old is None:os.environ.pop("CHROME_PATH",None)
            else:os.environ["CHROME_PATH"]=old
    class Keyboard:
        def __init__(self):self.keys=[]
        def press(self,key):self.keys.append(key)
    class EmptyLocator:
        def count(self):return 0
    class Page:
        def __init__(self):self.keyboard=Keyboard();self.waited=None
        def locator(self,_selector):return EmptyLocator()
        def wait_for_url(self,predicate,timeout):
            self.waited=timeout;assert predicate("https://liveplatform.taobao.com/path")
    page=Page();taobao._wait_taobao_login(page,target_url="https://liveplatform.taobao.com/list")
    assert page.waited==600000 and page.keyboard.keys==["Escape"]
    import recovered.main as main_module
    api=main_module.Api.__new__(main_module.Api);api.runtime_dir=Path("/runtime")
    api.config={"taobao_storage_state":"state.json"};calls=[]
    originals=(taobao._fetch_taobao_commodity_products,taobao._fetch_taobao_live_plan_products)
    try:
        taobao._fetch_taobao_commodity_products=lambda **kwargs:calls.append(("commodity",kwargs)) or [{"itemId":"1"}]
        taobao._fetch_taobao_live_plan_products=lambda **kwargs:calls.append(("plan",kwargs)) or [{"itemId":"2"}]
        assert api.sync_taobao_products("commodity")["products"][0]["itemId"]=="1"
        assert api.sync_taobao_products("plan")["products"][0]["itemId"]=="2"
        assert api.sync_taobao_products("unknown")["status"]=="error"
    finally:taobao._fetch_taobao_commodity_products,taobao._fetch_taobao_live_plan_products=originals
    assert [item[0] for item in calls]==["commodity","plan"]

def verify_product_kt_geometry_helpers():
    import numpy as np
    import cv2
    import recovered.product_kt_overlay as kt
    markers=[kt._Marker(10,10,4,4,16),kt._Marker(90,10,4,4,16),
             kt._Marker(90,90,4,4,16),kt._Marker(10,90,4,4,16),kt._Marker(50,50,4,4,16)]
    kept=kt._nms_markers(markers+[kt._Marker(11,11,3,3,9)],5)
    assert len(kept)==5
    board=np.asarray([[0,0],[100,0],[100,100],[0,100]],np.float32)
    selected=kt._select_corners_and_center(markers,board);assert selected is not None
    quad=kt._quad_from_selection(selected,1.0)
    expected=np.asarray([[10,10],[90,10],[90,90],[10,90]],np.float32)
    assert np.allclose(quad,expected) and kt._quad_score(quad)>0
    mask=np.zeros((120,120),np.uint8);cv2.fillConvexPoly(mask,board.astype(np.int32),255)
    assert kt._quad_board_overlap(quad,mask)>.99
    incomplete=[markers[0],markers[1],markers[3],markers[4]]
    completed=kt._complete_fourth_corner(incomplete)
    assert len(completed)==5 and np.allclose(kt._marker_point(completed[-1]),(90,90))
    image=np.zeros((120,120,3),np.uint8);image[5:115,5:115]=255
    board_mask,box=kt._find_white_board(image)
    assert board_mask is not None and box.shape==(4,2)
    roots=kt._client_search_roots();assert roots and len(roots)==len(set(roots))
    with tempfile.TemporaryDirectory() as directory:
        model=Path(directory)/"model";frames=model/"frames";frames.mkdir(parents=True)
        boxes=[expected.copy(),None,expected.copy()+5]
        kt.save_kt_board_cache(model,boxes,(120,120),2)
        overlay=kt.ProductKtOverlay()
        assert overlay.load_from_model_dir(model)==2
        assert len(overlay._boxes)==3 and overlay._boxes[1] is None
        assert overlay._frame_size==(120,120) and overlay._frames_dir==str(frames.resolve())
        assert overlay.has_precomputed()
        frame=np.zeros((240,240,3),np.uint8);product=np.full((10,10,3),127,np.uint8)
        overlay._enabled=True;overlay._product=product
        calls=[];original_paste=kt._paste_on_board;original_detect=kt.detect_kt_board_quad
        try:
            kt.detect_kt_board_quad=lambda _frame:None
            kt._paste_on_board=lambda source,_product,box:calls.append(box.copy()) or source.copy()
            assert overlay.apply(frame,physical_index=3) is not frame
            assert np.allclose(calls[-1],expected*2)
            overlay._tracker.reset()
            assert overlay.apply(frame,physical_index=1) is frame
            kt._paste_on_board=lambda *_args:(_ for _ in ()).throw(ValueError("bad quad"))
            assert overlay.apply(frame,physical_index=0) is frame
            marker=object();assert overlay.apply(marker,0) is marker and overlay.apply(None,0) is None
        finally:
            kt._paste_on_board=original_paste;kt.detect_kt_board_quad=original_detect

def verify_remaining_private_entrypoints():
    from recovered.tools import virtual_cam
    from recovered import win_power_throttling
    from recovered.tools.danmu_capture.kuaishou_v2 import KsLive
    from recovered.bin.image_clone.tools.frame_synthesizer import infer_api, infer_api_save_frame
    expected_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0
    assert virtual_cam._creationflags() == expected_flags
    assert win_power_throttling._set_process_power_throttling(None) is False
    assert all(hasattr(win_power_throttling,name) for name in (
        "_KEEP_ALIVE_LOCK","_KEEP_ALIVE_STOP","_KEEP_ALIVE_THREAD"))
    original_platform=win_power_throttling.sys.platform
    original_disable=win_power_throttling.disable_execution_speed_throttling
    original_start=win_power_throttling._start_keep_alive
    original_thread_class=win_power_throttling.Thread
    original_stop=win_power_throttling._KEEP_ALIVE_STOP
    original_thread=win_power_throttling._KEEP_ALIVE_THREAD
    had_windll=hasattr(win_power_throttling.ctypes,"windll")
    original_windll=getattr(win_power_throttling.ctypes,"windll",None)
    starts=[]
    try:
        win_power_throttling.sys.platform="win32"
        setter_calls=[]
        class Setter:
            def __call__(self,*args):setter_calls.append(args);return 1
        setter=Setter()
        class Kernel32: SetProcessInformation=setter
        class Windll: kernel32=Kernel32()
        win_power_throttling.ctypes.windll=Windll()
        assert win_power_throttling._set_process_power_throttling(123) is True
        assert setter.argtypes==[
            win_power_throttling.wintypes.HANDLE,
            win_power_throttling.ctypes.c_int,
            win_power_throttling.ctypes.c_void_p,
            win_power_throttling.wintypes.DWORD,
        ]
        assert setter.restype is win_power_throttling.wintypes.BOOL
        assert setter_calls[0][0:2]==(123,4)
        assert setter_calls[0][3]==win_power_throttling.ctypes.sizeof(
            win_power_throttling.PROCESS_POWER_THROTTLING_STATE)
        def fail(*_args):raise OSError("SetProcessInformation failed")
        Windll.kernel32.SetProcessInformation=fail
        try:win_power_throttling._set_process_power_throttling(123)
        except OSError:pass
        else:raise AssertionError("private setter must propagate Win32 API errors")
        win_power_throttling.disable_execution_speed_throttling=lambda:False
        win_power_throttling._start_keep_alive=lambda interval:starts.append(interval)
        assert win_power_throttling.ensure_high_performance(True,12.5) is False
        assert starts==[12.5]
        starts.clear()
        assert win_power_throttling.ensure_high_performance(False,9.0) is False
        assert starts==[]
        thread_calls=[];waits=[]
        class Stop:
            def clear(self):thread_calls.append("clear")
            def wait(self,interval):waits.append(interval);return True
        class FakeThread:
            def __init__(self,**kwargs):self.kwargs=kwargs;thread_calls.append(kwargs)
            def is_alive(self):return False
            def start(self):thread_calls.append("start");self.kwargs["target"]()
        win_power_throttling.Thread=FakeThread
        win_power_throttling._KEEP_ALIVE_STOP=Stop()
        win_power_throttling._KEEP_ALIVE_THREAD=None
        original_start(1)
        assert waits==[5.0]
        assert thread_calls[1]["name"]=="win-power-throttling-keepalive"
        assert thread_calls[1]["daemon"] is True
    finally:
        win_power_throttling.sys.platform=original_platform
        win_power_throttling.disable_execution_speed_throttling=original_disable
        win_power_throttling._start_keep_alive=original_start
        win_power_throttling.Thread=original_thread_class
        win_power_throttling._KEEP_ALIVE_STOP=original_stop
        win_power_throttling._KEEP_ALIVE_THREAD=original_thread
        if had_windll:win_power_throttling.ctypes.windll=original_windll
        else:del win_power_throttling.ctypes.windll
    assert inspect.signature(KsLive.main).parameters.keys()=={"live_url"}
    assert not inspect.signature(infer_api.main).parameters
    assert not inspect.signature(infer_api_save_frame.main).parameters

def verify_image_clone_resource_lifecycle():
    from recovered.image_clone_video_synthesizer import VideoSynthesizer
    from recovered.image_frame_synthesizer_runtime import FrameSynthesizer
    calls=[]
    class Executor:
        def shutdown(self,**kwargs):calls.append(("executor",kwargs))
    class Engine:
        def close(self):calls.append(("engine",None))
    synthesizer=VideoSynthesizer.__new__(VideoSynthesizer)
    synthesizer._closed=False;synthesizer.executor=Executor();synthesizer.engine=Engine()
    synthesizer.close(wait=False);synthesizer.close(wait=True);synthesizer.__del__()
    assert calls==[("executor",{"wait":False,"cancel_futures":True}),("engine",None)]
    assert synthesizer.executor is None and synthesizer.engine is None and synthesizer._closed
    class Session:
        def close(self):calls.append(("session",None))
    engine=FrameSynthesizer.__new__(FrameSynthesizer);engine.session=Session()
    engine.close();engine.close();engine.__del__()
    assert calls.count(("session",None))==1 and engine.session is None

def verify_auto_live_action_spacing_contract():
    from recovered import auto_live_action
    assert hashlib.sha256(auto_live_action.CONTROL_UI_HTML.encode("utf-8")).hexdigest()==(
        "e04ea27a1b22230879414a67fbfc1c36937bd06f3452c1704eed63f8081c4441")
    assert "function collectSettings()" in auto_live_action.CONTROL_UI_HTML
    assert "applyPackLabels(config.ui_labels)" in auto_live_action.CONTROL_UI_HTML
    api=auto_live_action.LiveControlAPI.__new__(auto_live_action.LiveControlAPI)
    assert api._add_random_spaces("短文本")=="短文本"
    original_sample=auto_live_action.random.sample
    original_choice=auto_live_action.random.choice
    calls=[]
    try:
        auto_live_action.random.sample=lambda population,count:(
            calls.append((list(population),count)) or [5,1,3,2,4])
        widths=iter((1,2,3,1,2))
        auto_live_action.random.choice=lambda values:(
            calls.append(tuple(values)) or next(widths))
        assert api._add_random_spaces("abcdef")=="a         bcdef"
        assert calls[0]==([1,2,3,4,5],5)
        assert calls[1:]==[(1,2,3)]*5
    finally:
        auto_live_action.random.sample=original_sample
        auto_live_action.random.choice=original_choice
    sent=[]
    class ActionQueue:
        def put(self,value):sent.append(value)
    api.action_queue=ActionQueue()
    api.is_danmu_running=True
    original_time=auto_live_action.time.time
    original_sleep=auto_live_action.time.sleep
    clock=iter((100.0,100.0,100.1,100.2))
    sleeps=[]
    try:
        auto_live_action.time.time=lambda:next(clock)
        def stop_after_two(value):
            sleeps.append(value)
            if len(sleeps)==2:api.is_danmu_running=False
        auto_live_action.time.sleep=stop_after_two
        assert api._danmu_thread(["一","二"],3,1,2,False,False) is None
        assert sent==[("send_danmu","一"),("send_danmu","二")] and sleeps==[3,3]
        assert api.is_danmu_running is False
    finally:
        auto_live_action.time.time=original_time
        auto_live_action.time.sleep=original_sleep
    class Capture:
        def rect(self):return (100,200,500,400)
    class OCR:
        def __init__(self,items):self.items=items
        def recognize_text(self,image):
            assert image=="shot"
            return self.items
    api.config={}
    api.control_running=False
    api.is_danmu_running=False
    api.is_positioning=False
    api.capture_cmd_queue=auto_live_action.queue.Queue()
    api.capture_res_queue=auto_live_action.queue.Queue()
    api.capture_cmd_queue.put("stale-command")
    api.capture_res_queue.put("stale-result")
    positioning_threads=[]
    class PositioningThread:
        def __init__(self,**kwargs):positioning_threads.append(("init",kwargs))
        def start(self):positioning_threads.append(("start",None))
    original_thread=auto_live_action.threading.Thread
    try:
        auto_live_action.threading.Thread=PositioningThread
        positioned=api.start_positioning()
        assert positioned["success"] is True
        assert positioned["message"]==(
            "请将红色方框拖动到直播间评论输入框/发送按钮位置")
        assert api.capture_cmd_queue.empty() and api.capture_res_queue.empty()
        assert positioning_threads[0][1]["target"]==api._capture_window_worker
        assert positioning_threads[0][1]["daemon"] is True
        assert api.start_positioning()["message"]=="正在定位中..."
    finally:auto_live_action.threading.Thread=original_thread
    capture_runs=[]
    class ConstructedCapture:
        def __init__(self,command_queue,result_queue):
            capture_runs.append(("init",command_queue,result_queue))
        def run(self):capture_runs.append(("run",None,None))
    original_capture=auto_live_action.CaptureWindow
    try:
        auto_live_action.CaptureWindow=ConstructedCapture
        assert api._capture_window_worker() is None
        assert capture_runs[0][1:]==(api.capture_cmd_queue,api.capture_res_queue)
        assert capture_runs[1][0]=="run"
    finally:auto_live_action.CaptureWindow=original_capture
    api.is_positioning=True
    api.capture_window=Capture()
    api.capture_window_thread=object()
    api.capture_cmd_queue=auto_live_action.queue.Queue()
    api.capture_res_queue=auto_live_action.queue.Queue()
    api.capture_res_queue.put("shot")
    api.ocr_processor=OCR([
        {"text":"Nói gì...","box":[[10,20],[110,20],[110,60],[10,60]]},
        {"text":"Gửi","box":[[300,20],[360,20],[360,60],[300,60]]},
    ])
    control_starts=[]
    api.start_control=lambda:control_starts.append(True)
    confirmed=api.confirm_position()
    assert confirmed["success"] is True
    assert set(confirmed)=={"success","message","config"}
    assert confirmed["message"]=="位置已确认，场控运行中"
    assert api.positions=={"input_hint":(160,240),"send_btn":(430,240),
                          "target":(160,240)}
    assert api.live_action.target_coords==(160,240)
    assert api.capture_cmd_queue.get_nowait()=="capture"
    assert api.capture_cmd_queue.get_nowait()=="stop"
    assert control_starts==[True] and api.is_positioning is False
    api.is_positioning=True
    api.capture_window_thread=object()
    api.capture_cmd_queue=auto_live_action.queue.Queue()
    api.capture_res_queue=auto_live_action.queue.Queue();api.capture_res_queue.put("shot")
    api.ocr_processor=OCR([])
    api.confirm_position()
    assert api.positions["input_hint"] is None
    assert api.positions["send_btn"]==(470,300)
    assert api.positions["target"]==(470,300)
    api.start_control=auto_live_action.LiveControlAPI.start_control.__get__(
        api,auto_live_action.LiveControlAPI)
    worker_events=[]
    class WorkerAction:
        def send_danmu(self,text):worker_events.append(("send_danmu",text))
        def close(self):worker_events.append(("close",None))
    api.action_queue=auto_live_action.queue.Queue()
    api.live_action=WorkerAction()
    api.control_running=True
    api.action_queue.put(("send_danmu","测试"))
    api.action_queue.put(("missing_method",123))
    api.action_queue.put("stop")
    assert api._control_worker() is None
    assert worker_events==[("send_danmu","测试"),("close",None)]
    assert api.control_running is False
    api.config={}
    api.is_danmu_running=False
    api.is_positioning=False
    api.control_running=True
    assert api.start_control()["message"]=="场控已在运行中"
    api.control_running=False
    api.live_action=None
    api.start_positioning=lambda:{"success":True,"marker":"positioning"}
    assert api.start_control()=={"success":True,"marker":"positioning"}
    thread_events=[]
    class ControlThread:
        def __init__(self,**kwargs):thread_events.append(("init",kwargs))
        def start(self):thread_events.append(("start",None))
        def is_alive(self):return True
        def join(self,**kwargs):thread_events.append(("join",kwargs))
    original_thread=auto_live_action.threading.Thread
    try:
        auto_live_action.threading.Thread=ControlThread
        api.live_action=WorkerAction()
        started=api.start_control()
        assert started["success"] is True and started["message"]=="位置已确认，场控运行中"
        assert thread_events[0][1]["target"]==api._control_worker
        assert thread_events[0][1]["daemon"] is True
        api.capture_cmd_queue=auto_live_action.queue.Queue()
        api.action_queue=auto_live_action.queue.Queue()
        api.is_positioning=True
        stopped=api.stop_control()
        assert stopped["success"] is True and stopped["message"]=="场控已停止。"
        assert api.capture_cmd_queue.get_nowait()=="stop"
        assert api.action_queue.get_nowait()=="stop"
        assert thread_events[-1]==("join",{"timeout":2})
        assert api.control_thread is None and api.control_running is False
        assert api.is_positioning is False
    finally:auto_live_action.threading.Thread=original_thread
    api.config=dict(auto_live_action.DEFAULT_CONFIG)
    api.is_positioning=False
    api.is_danmu_running=False
    api.control_running=False
    assert api.start_danmu({"danmu_list":["一"]})=={
        "success":False,"config":api.get_config()}
    danmu_threads=[]
    class DanmuStartThread:
        def __init__(self,**kwargs):danmu_threads.append(("init",kwargs))
        def start(self):danmu_threads.append(("start",None))
    original_thread=auto_live_action.threading.Thread
    api.control_running=True
    api.save_config=lambda:None
    try:
        auto_live_action.threading.Thread=DanmuStartThread
        empty=api.start_danmu({"danmu_list":[" ",""]})
        assert empty["success"] is False and set(empty)=={"success","config"}
        texts=[" 一 ","二"]
        started=api.start_danmu({"danmu_list":texts,"send_interval":"9",
            "work_minutes":"3","rest_minutes":"4","random_send":1,
            "random_space":0,"enable_text_reply":True})
        assert started["success"] is True and set(started)=={"success","config"}
        thread_kwargs=danmu_threads[0][1]
        assert thread_kwargs["target"]==api._danmu_thread
        assert thread_kwargs["args"]==(api.config["danmu_list"],9,3,4,True,False)
        assert thread_kwargs["args"][0] is api.config["danmu_list"]
        assert thread_kwargs["daemon"] is True and api.is_danmu_running is True
    finally:auto_live_action.threading.Thread=original_thread
    joins=[]
    class DanmuThread:
        def join(self,**kwargs):joins.append(kwargs)
    api.is_danmu_running=True
    api.danmu_thread=DanmuThread()
    api.control_running=False
    api.is_positioning=False
    api.config={}
    result=api.stop_danmu()
    assert joins==[{"timeout":1}]
    assert result["success"] is True and set(result)=={"success","config"}
    config=result["config"]
    assert config["send_interval"]==60 and config["work_minutes"]==10
    assert config["rest_minutes"]==2 and config["danmu_list"]==[]
    assert config["enable_text_reply"] is True
    original_pack=auto_live_action.IS_VIETNAM_PACK
    try:
        auto_live_action.IS_VIETNAM_PACK=True
        config=api.get_config()
        assert config["vietnam_pack"] is True
        assert config["ui_labels"] is auto_live_action.VIETNAM_UI_LABELS
        assert config["ui_labels"]["title"]=="Trợ lý điều khiển live"
        assert config["ui_labels"]["start_control_first"]==(
            "Hãy bật điều khiển và xác nhận vị trí trước")
        assert set(config)=={"danmu_list","random_send","random_space","rest_minutes",
            "send_interval","work_minutes","enable_text_reply","is_control_running",
            "is_danmu_running","is_positioning","vietnam_pack","ui_labels"}
    finally:auto_live_action.IS_VIETNAM_PACK=original_pack
    events=[]
    class Gui:
        def click(self,*args):events.append(("click",args))
        def hotkey(self,*args):events.append(("hotkey",args))
        def press(self,*args):events.append(("press",args))
    class Clipboard:
        def copy(self,value):events.append(("copy",value))
    original_gui=auto_live_action.pyautogui
    original_clipboard=auto_live_action.pyperclip
    original_sleep=auto_live_action.time.sleep
    try:
        auto_live_action.pyautogui=Gui()
        auto_live_action.pyperclip=Clipboard()
        auto_live_action.time.sleep=lambda value:events.append(("sleep",value))
        action=auto_live_action.VisualLiveAction((123,456))
        assert action.send_danmu("测试文本") is None
        assert events==[("click",(123,456)),("sleep",0.2),("copy","测试文本"),
            ("sleep",0.2),("hotkey",("ctrl","v")),("sleep",0.2),("press",("enter",))]
        events.clear();action.target_coords=None
        assert action.send_danmu("忽略") is None and events==[]
        action.target_coords=(1,2);auto_live_action.pyautogui=None
        assert action.send_danmu("忽略") is None and events==[]
    finally:
        auto_live_action.pyautogui=original_gui
        auto_live_action.pyperclip=original_clipboard
        auto_live_action.time.sleep=original_sleep
    original_config_path=auto_live_action.CONFIG_PATH
    with tempfile.TemporaryDirectory() as temp:
        try:
            auto_live_action.CONFIG_PATH=Path(temp)/"tools/auto_live_action/config/config.yaml"
            config_api=auto_live_action.LiveControlAPI.__new__(auto_live_action.LiveControlAPI)
            config_api.control_running=False
            config_api.is_danmu_running=False
            config_api.is_positioning=False
            assert config_api.load_config()==auto_live_action.DEFAULT_CONFIG
            config_api.config={**auto_live_action.DEFAULT_CONFIG,"send_interval":17,
                               "danmu_list":["一","二"]}
            assert config_api.save_config() is None
            assert auto_live_action.yaml.safe_load(
                auto_live_action.CONFIG_PATH.read_text(encoding="utf-8"))==config_api.config
            assert config_api.load_config()==config_api.config
            config_api.config["customer_extension"]="old"
            updated=config_api.update_config({"send_interval":23,
                "customer_extension":"new","not_present":"ignored"})
            assert config_api.config["send_interval"]==23
            assert config_api.config["customer_extension"]=="new"
            assert "not_present" not in config_api.config and updated["send_interval"]==23
            save_calls=[]
            original_save=config_api.save_config
            config_api.save_config=lambda:save_calls.append(dict(config_api.config))
            assert config_api._apply_settings({
                "danmu_list":["  一  ","","   ","二"],
                "send_interval":"0","work_minutes":"-4","rest_minutes":"7",
                "random_send":0,"random_space":1,"enable_text_reply":"",
            },persist=True) is None
            assert config_api.config["danmu_list"]==["一","二"]
            assert config_api.config["send_interval"]==1
            assert config_api.config["work_minutes"]==1
            assert config_api.config["rest_minutes"]==7
            assert config_api.config["random_send"] is False
            assert config_api.config["random_space"] is True
            assert config_api.config["enable_text_reply"] is False
            assert config_api.config["customer_extension"]=="new"
            assert len(save_calls)==1 and save_calls[0]==config_api.config
            config_api.save_config=original_save
            saved=config_api.save_all_settings({"work_minutes":8})
            assert saved["success"] is True and saved["message"]=="配置已保存"
            config_api.save_config=lambda:(_ for _ in ()).throw(OSError("只读目录"))
            failed=config_api.save_all_settings({"work_minutes":9})
            assert failed["success"] is False
            assert failed["message"]=="保存配置失败: 只读目录"
            config_api.save_config=original_save
        finally:auto_live_action.CONFIG_PATH=original_config_path

def verify_image_clone_save_frame_diagnostics():
    import cv2
    import numpy as np
    from recovered.bin.image_clone.tools.frame_synthesizer.infer_api_save_frame import VideoSynthesizer
    generated=np.zeros((20,20,3),np.uint8);generated[5:15,5:15]=120
    cropped=np.full((20,20,3),220,np.uint8)
    landmarks=np.asarray([[i,i] for i in range(20)],np.float32)
    class Engine:
        last_diagnostics=[{"generated_face":generated,"cropped_for_pasting":cropped,
                           "landmarks":landmarks}]
        def process_batch(self,*_args):return [np.full((30,30,3),64,np.uint8)]
    synthesizer=VideoSynthesizer.__new__(VideoSynthesizer);synthesizer.engine=Engine()
    with tempfile.TemporaryDirectory() as directory:
        previous=os.getcwd();os.chdir(directory)
        original_circle,original_put_text=cv2.circle,cv2.putText
        circle_calls=[];text_calls=[]
        cv2.circle=lambda image,point,radius,color,thickness:(circle_calls.append((point,radius,color,thickness)) or original_circle(image,point,radius,color,thickness))
        cv2.putText=lambda image,text,point,font,scale,color,thickness:(text_calls.append((text,point,font,scale,color,thickness)) or original_put_text(image,text,point,font,scale,color,thickness))
        try:
            frames=synthesizer._process_batch([generated],[{}],[np.zeros((2,2))],batch_start=7)
            landmark=Path("generated_face_with_landmarks_7.jpg")
            crop=Path("generated_face_cropped_7.jpg")
            assert len(frames)==1 and landmark.is_file() and crop.is_file()
            assert cv2.imread(str(landmark)).shape==(20,20,3)
            assert cv2.imread(str(crop)).mean()>200
            assert [call[0] for call in circle_calls]==[(i,i) for i in range(2,16)]
            assert all(call[1:]==(2,(0,255,0),-1) for call in circle_calls)
            assert [call[0] for call in text_calls]==[str(i) for i in range(2,16)]
            assert all(call[3:]==(0.4,(255,0,0),1) for call in text_calls)
        finally:
            cv2.circle,cv2.putText=original_circle,original_put_text
            os.chdir(previous)

def verify_image_clone_model_assets():
    import numpy as np
    from recovered.image_frame_synthesizer_runtime import FrameSynthesizer
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);data=root/"character";models=root/"models"
        data.mkdir();models.mkdir()
        (models/"unet_v2.onnx").write_bytes(b"preferred")
        (models/"unet_v2_fix.onnx").write_bytes(b"fallback")
        mask=np.linspace(0,1,256*256,dtype=np.float32).reshape(256,256)
        reverse=np.flipud(mask).copy()
        np.save(models/"input_mask.npy",mask);np.save(models/"input_mask_re.npy",reverse)
        original_loader=FrameSynthesizer._load_session
        try:
            FrameSynthesizer._load_session=lambda self:None
            synthesizer=FrameSynthesizer(data,models,device="cpu")
        finally:
            FrameSynthesizer._load_session=original_loader
        assert synthesizer.model_path==models/"unet_v2.onnx"
        assert np.allclose(synthesizer.input_mask,mask)
        assert np.allclose(synthesizer.input_mask_re,reverse)
        (models/"unet_v2.onnx").unlink()
        assert FrameSynthesizer._resolve_model_path(models)==models/"unet_v2_fix.onnx"

def verify_image_clone_generate_cleanup():
    import recovered.image_clone_api as clone
    events=[]
    class Synthesizer:
        def __init__(self,*args):events.append(("init",args))
        def process_single_file(self,*args):events.append(("process",args));return "output.mp4"
        def close(self):events.append(("close",))
    original=clone.VideoSynthesizer
    try:
        clone.VideoSynthesizer=Synthesizer
        result=clone.generate_video("data","audio.wav","output.mp4","conf","wenet","unet")
        assert result=="output.mp4" and events[-1]==("close",)
        class Failing(Synthesizer):
            def process_single_file(self,*args):raise RuntimeError("render failed")
        clone.VideoSynthesizer=Failing;events.clear()
        try:clone.generate_video("data","audio.wav","output.mp4","conf","wenet","unet")
        except RuntimeError as error:assert str(error)=="render failed"
        else:raise AssertionError("render failure must propagate")
        assert events[-1]==("close",)
    finally:clone.VideoSynthesizer=original

def verify_image_clone_video_preprocess():
    import cv2
    import numpy as np
    from recovered.image_video_preprocess import crop_to_portrait,extract_frames,process_frame
    landscape=np.zeros((100,200,3),np.uint8);landscape[:,50:150]=127
    cropped=crop_to_portrait(landscape)
    assert cropped.shape[:2]==(100,56)
    assert process_frame(landscape,72,128).shape==(128,72,3)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);video=root/"input.mp4";frames=root/"frames";frames.mkdir()
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"mp4v"),25,(64,48))
        assert writer.isOpened()
        writer.write(np.full((48,64,3),32,np.uint8));writer.write(np.full((48,64,3),224,np.uint8));writer.release()
        outputs=extract_frames(str(video),str(frames))
        assert outputs==[str(frames/"0.npy"),str(frames/"1.npy")]
        assert sorted(path.name for path in frames.glob("*.npy"))==["0.npy","1.npy"]
        first=np.load(frames/"0.npy");second=np.load(frames/"1.npy")
        assert first.shape==(1280,720,3) and second.shape==(1280,720,3)
        assert float(second.mean())>float(first.mean())

def verify_image_clone_video_normalize_contract():
    from recovered import image_clone_video_normalize as normalize
    import json

    original_check=normalize.subprocess.check_output;original_run=normalize.subprocess.run
    calls=[]
    probe_payload={"streams":[
        {"codec_type":"video","width":1080,"height":1920,"r_frame_rate":"25/1","tags":{"rotate":"90"}},
        {"codec_type":"audio","sample_rate":"44100","channels":2},
    ]}
    normalize.subprocess.check_output=lambda command:(calls.append(("probe",command)) or json.dumps(probe_payload).encode())
    normalize.subprocess.run=lambda command,**kwargs:(calls.append(("run",command,kwargs)) or types.SimpleNamespace())
    try:
        info=normalize.get_video_info("input.mp4")
        assert info=={"width":1920,"height":1080,"fps":25.0,"is_landscape":True,"rotation":90,"audio_sample_rate":44100,"audio_channels":2}
        output=normalize.normalize_video("input.mp4","720p")
    finally:
        normalize.subprocess.check_output=original_check;normalize.subprocess.run=original_run
    assert output.endswith("normalized_input.mp4")
    command=next(call[1] for call in calls if call[0]=="run")
    assert command[command.index("-vf")+1]=="scale=1280:720"
    assert command[command.index("-ar")+1:command.index("-ar")+4]==["44100","-ac","2"]
    assert next(call[2] for call in calls if call[0]=="run")=={"check":True}

def verify_pfld_ghostone_architecture():
    source=(HERE/"pfld_mobileone.py").read_text(encoding="utf-8")
    assert "nn.AvgPool2d(input_size//2)" in source and "nn.AvgPool2d(input_size//16)" in source
    assert "nn.Conv2d(c(512),landmark_number*2,1,1,0)" in source
    assert "self.localization=nn.Sequential" in source
    assert "torch.cat([x1,x2,x3,x4,x5],1)" in source
    assert "landmarks.view(landmarks.size(0),-1)" in source
    assert "self.avg_pool1(x).view" not in source
    assert "AdaptiveAvgPool2d" not in source and "F.pad" not in source
    blocks=(HERE/"mobileone_blocks.py").read_text(encoding="utf-8")
    assert "groups=group,bias=False" in blocks
    assert "new=init" in blocks and "[:,:self.out_channel,:,:]" in blocks
    ordinary=blocks[blocks.index("class GhostBottleneck"):blocks.index("class GhostOneModule")]
    assert "group=hidden_channel,is_linear=True" in ordinary
    ghostone=blocks[blocks.index("class GhostOneBottleneck"):blocks.index("class InvertedResidual")]
    assert "self.shortcut" not in ghostone and "return self.ghost_conv(x)" in ghostone
    assert "self.num_conv_branches=num_conv_branches" in blocks
    assert "self.inv_res=nn.Sequential" in blocks and "self.conv=nn.Sequential" not in blocks[blocks.index("class InvertedResidual"):]
    assert "nn.ReLU(inplace=True)" not in blocks

def verify_s3fd_architecture():
    nets=(HERE/"s3fd_nets.py").read_text(encoding="utf-8")
    extras=nets[nets.index("def _extras"):nets.index("class S3FDNet")]
    assert extras.count("nn.Conv2d(")==4
    assert "nn.MaxPool2d(3,1,1)" not in nets
    assert "self.softmax=nn.Softmax(dim=-1);self.detect=Detect()" in nets
    assert "self.priorbox=PriorBox(size,feature_maps)" in nets
    assert "return self.detect.forward" in nets
    main=(HERE/"s3fd_main.py").read_text(encoding="utf-8")
    assert "load_state_dict(state)" in main and "strict=False" not in main
    assert "output=self.net(tensor)[0,1]" in main
    boxes=(HERE/"s3fd_box_utils.py").read_text(encoding="utf-8")
    assert "areas=(x2-x1)*(y2-y1)" in boxes
    assert "scores.new_zeros" in boxes and ".cpu().numpy()" not in boxes

def verify_kuaishou_message_protocol():
    import asyncio,contextlib,io,json,sys,types
    from recovered.kuaishou_v2 import miniproto
    from recovered.kuaishou_v2.KsLive import KuaishouLiveClient
    from recovered.kuaishou_v2.protocol import decode_frame,iter_comments,iter_gifts,iter_likes,proto
    user=proto.SimpleUserInfo(principalId="u1",userName="小快",headUrl="https://avatar")
    feed=proto.SCWebFeedPush(displayWatchingCount="1.2万",displayLikeCount="345",
        commentFeeds=[proto.WebCommentFeed(user=user,content="你好")],
        likeFeeds=[proto.WebLikeFeed(user=user)],
        giftFeeds=[proto.WebGiftFeed(user=user,giftId=7,batchSize=2)])
    chat=next(iter_comments(feed));like=next(iter_likes(feed));gift=next(iter_gifts(feed))
    assert chat=={"type":"chat","user_name":"小快","user_id":"u1","avatar":"https://avatar","content":"你好"}
    assert like=={"type":"like","user_name":"小快","user_id":"u1","avatar":"https://avatar"}
    assert gift["gift_id"]==7 and gift["gift_count"]==2 and gift["user_name"]=="小快"
    # Exercise the dependency-free wire implementation even when real protobuf is installed.
    fallback_feed = miniproto.SCWebFeedPush.FromString(feed.SerializeToString())
    assert list(iter_comments(fallback_feed)) == list(iter_comments(feed))
    assert list(iter_gifts(fallback_feed)) == list(iter_gifts(feed))
    assert list(iter_likes(fallback_feed)) == list(iter_likes(feed))
    watch=proto.SCWebLiveWatchingUsers(displayWatchingCount="999")
    envelope=proto.SocketMessage(payloadType=proto.SC_LIVE_WATCHING_LIST,compressionType=proto.SocketMessage.NONE,payload=watch.SerializeToString()).SerializeToString()
    kind,decoded=decode_frame(envelope);assert kind==proto.SC_LIVE_WATCHING_LIST and decoded.displayWatchingCount=="999"
    sent=[]
    class Client(KuaishouLiveClient):
        async def _forward_message(self,value):sent.append(json.loads(value))
    client=Client("stream","token","wss://example")
    asyncio.run(client._handle_feed_push(feed));asyncio.run(client._handle_watching_list(watch))
    assert sent[0]["type"]=="chat" and sent[1]["type"]=="gift" and sent[2]["type"]=="like"
    assert sent[3]=={"type":"stats","status":"1.2万","like_count":"345"}
    assert sent[4]=={"type":"stats","status":"999"}
    base=KuaishouLiveClient("stream","token","wss://example")
    assert asyncio.run(base._forward_message('{"type":"chat"}')) is None
    lifecycle=[]
    base._reconnect=lambda:(lifecycle.append("reconnect") or asyncio.sleep(0))
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        asyncio.run(base._on_error(object(),RuntimeError("socket failed")))
    assert lifecycle==["reconnect"]
    assert output.getvalue().splitlines()==[
        "[错误] socket failed","[已关闭] WebSocket连接已关闭"
    ]
    import recovered.kuaishou_v2.KsLive as kslive_module
    kslive_module.gift_info_global.clear()
    class GiftResponse:
        status=200
        async def __aenter__(self):return self
        async def __aexit__(self,*_args):return False
        async def json(self):
            return {"data":[{"id":7,"name":"小花","unitPrice":3,"type":2,
                             "picUrl":[{"url":"https://gift/7.png"}]}]}
    class GiftSession:
        async def __aenter__(self):return self
        async def __aexit__(self,*_args):return False
        def get(self,url):
            assert url=="https://livev.m.chenzhongtech.com/rest/wd/live/gift/all"
            return GiftResponse()
    original_aiohttp=sys.modules.get("aiohttp")
    sys.modules["aiohttp"]=types.SimpleNamespace(ClientSession=GiftSession)
    output=io.StringIO()
    try:
        with contextlib.redirect_stdout(output):result=asyncio.run(kslive_module.fetch_gift_info_global())
    finally:
        if original_aiohttp is None:sys.modules.pop("aiohttp",None)
        else:sys.modules["aiohttp"]=original_aiohttp
    assert result is None
    assert output.getvalue().strip()=="[礼物] 全局获取到 1 个礼物信息"
    assert base.get_gift_info(7)=={"name":"小花","price":3,"type":2,"pic_url":"https://gift/7.png"}
    assert base.get_gift_info(99)=={"name":"未知礼物(99)","price":0,"type":0,"pic_url":""}
    import recovered.kuaishou_v2.hq as kuaishou_hq
    request_calls=[]
    class RoomResponse:
        def json(self):return {"data":{"liveStream":{"liveStreamId":"resolved-stream","id":"fallback-id"}}}
    fake_requests=types.SimpleNamespace(get=lambda url,**kwargs:(request_calls.append((url,kwargs)) or RoomResponse()))
    ocr_calls=[]
    class FakeOCR:
        def __init__(self,**kwargs):ocr_calls.append(kwargs)
    fake_ddddocr=types.SimpleNamespace(DdddOcr=FakeOCR)
    original_requests=sys.modules.get("requests");original_ddddocr=sys.modules.get("ddddocr")
    sys.modules["requests"]=fake_requests;sys.modules["ddddocr"]=fake_ddddocr
    try:
        room_tool=kuaishou_hq.Tool("https://live.kuaishou.com/u/demo/",cookie="cookie-value")
        resolved=room_tool.getLiveRoomId()
    finally:
        if original_requests is None:sys.modules.pop("requests",None)
        else:sys.modules["requests"]=original_requests
        if original_ddddocr is None:sys.modules.pop("ddddocr",None)
        else:sys.modules["ddddocr"]=original_ddddocr
    assert resolved=="resolved-stream" and len(request_calls)==1
    assert ocr_calls==[{"det":False,"ocr":False,"show_ad":False}]
    assert room_tool.verification_token is None and room_tool.cookie=="cookie-value"
    assert Path(room_tool.node_exe).parts[-2:] == ("js", "node.exe")
    assert Path(room_tool.sign_url_js).parts[-2:] == ("js", "sign_url.js")
    assert Path(room_tool.encrypt_js).parts[-2:] == ("js", "encrypt.js")
    original_generate_did=kuaishou_hq.generate_did;kuaishou_hq.generate_did=lambda:"fixed-did"
    try:auto_cookie_tool=kuaishou_hq.Tool("https://live.kuaishou.com/u/auto")
    finally:kuaishou_hq.generate_did=original_generate_did
    assert auto_cookie_tool.cookie=="did=fixed-did"
    original_choice=kuaishou_hq.random.choice;kuaishou_hq.random.choice=lambda alphabet:alphabet[-1]
    try:assert kuaishou_hq.generate_did()=="web_"+"f"*32
    finally:kuaishou_hq.random.choice=original_choice
    room_url,room_kwargs=request_calls[0]
    assert room_url=="https://live.kuaishou.com/live_api/liveroom/livedetail"
    assert room_kwargs["params"]=={"principalId":"demo"}
    assert room_kwargs["headers"]["Cookie"]=="cookie-value"
    assert room_kwargs["headers"]["Sec-Fetch-Mode"]=="cors"
    assert room_kwargs["headers"]["sec-ch-ua-mobile"]=="?0"
    process_tool=object.__new__(kuaishou_hq.Tool)
    process_tool.node_exe="C:/app/js/node.exe"
    process_tool.sign_url_js="C:/app/js/sign_url.js"
    process_tool.liveUrl="https://live.kuaishou.com/u/demo"
    process_tool.cookie="did=test"
    process_tool.verification_token=None
    sign_calls=[];process_requests=[]
    original_check_output=kuaishou_hq.subprocess.check_output
    kuaishou_hq.subprocess.check_output=lambda argv,**kwargs:(sign_calls.append((argv,kwargs)) or "/signed/path?x=1\n")
    class ProcessResponse:
        def __init__(self,payload):self.payload=payload
        def json(self):return self.payload
    process_payloads=[{"data":{"result":1,"token":"token-1"}}]
    fake_process_requests=types.SimpleNamespace(
        get=lambda url,**kwargs:(process_requests.append((url,kwargs)) or ProcessResponse(process_payloads.pop(0))))
    original_requests=sys.modules.get("requests");sys.modules["requests"]=fake_process_requests
    try:process_result=process_tool.processLiveId("stream-9")
    finally:
        kuaishou_hq.subprocess.check_output=original_check_output
        if original_requests is None:sys.modules.pop("requests",None)
        else:sys.modules["requests"]=original_requests
    assert process_result=={"data":{"result":1,"token":"token-1"}}
    assert sign_calls==[(["C:/app/js/node.exe","C:/app/js/sign_url.js",
                          "/live_api/liveroom/websocketinfo","/rest/k/live/websocket/info",
                          json.dumps({"liveStreamId":"stream-9"})],{"encoding":"utf-8"})]
    process_url,process_kwargs=process_requests[0]
    assert process_url=="https://live.kuaishou.com/signed/path?x=1&liveStreamId=stream-9"
    assert process_kwargs["headers"]["kww"].startswith("PnGU+")
    assert process_kwargs["headers"]["Host"]=="live.kuaishou.com"
    assert "identity-verification-token" not in process_kwargs["headers"]
    process_tool.verification_token=None;captcha_inputs=[];process_requests=[]
    process_payloads=[{"data":{"result":400002,"captcha":"needed"}},
                      {"data":{"result":1,"token":"after-captcha"}}]
    def solved_captcha(value):
        captcha_inputs.append(value);process_tool.verification_token="verified-token";return True
    process_tool.handle_captcha=solved_captcha
    original_check_output=kuaishou_hq.subprocess.check_output
    kuaishou_hq.subprocess.check_output=lambda *_args,**_kwargs:"/signed/retry?x=2"
    original_requests=sys.modules.get("requests");sys.modules["requests"]=fake_process_requests
    try:retry_result=process_tool.processLiveId("stream-retry")
    finally:
        kuaishou_hq.subprocess.check_output=original_check_output
        if original_requests is None:sys.modules.pop("requests",None)
        else:sys.modules["requests"]=original_requests
    assert retry_result=={"data":{"result":1,"token":"after-captcha"}}
    assert captcha_inputs==[{"result":400002,"captcha":"needed"}]
    assert len(process_requests)==2
    assert process_requests[1][1]["headers"]["identity-verification-token"]=="verified-token"
    assert process_requests[1][1]["headers"]["identity-verification-type"]=="1"
    empty_output=io.StringIO()
    with contextlib.redirect_stdout(empty_output):assert process_tool.processLiveId("") is None
    assert empty_output.getvalue().strip()=="未获取到直播间ID，无法生成签名URL。"
    captcha_tool=object.__new__(kuaishou_hq.Tool)
    captcha_tool.cookie="did=captcha"
    captcha_tool.node_exe="C:/app/js/node.exe"
    captcha_tool.encrypt_js="C:/app/js/encrypt.js"
    captcha_tool.verification_token=None
    class CaptchaDetector:
        def slide_match(self,target,background):
            assert target==b"cut-image" and background==b"background-image"
            return {"target":[200,10,240,50]}
    captcha_tool.det=CaptchaDetector()
    captcha_calls=[]
    class CaptchaResponse:
        def __init__(self,payload=None,content=b""):self.payload=payload;self.content=content
        def json(self):return self.payload
    def captcha_get(url,**kwargs):
        captcha_calls.append(("get",url,kwargs))
        if url.endswith("/sliding/config"):
            return CaptchaResponse({"result":1,"captchaSn":"sn-1","bgPicUrl":"https://img/bg",
                                    "cutPicUrl":"https://img/cut","disY":"20"})
        if url=="https://img/bg":return CaptchaResponse(content=b"background-image")
        if url=="https://img/cut":return CaptchaResponse(content=b"cut-image")
        raise AssertionError(url)
    def captcha_post(url,**kwargs):
        captcha_calls.append(("post",url,kwargs))
        return CaptchaResponse({"result":1,"captchaToken":"captcha-token"})
    fake_captcha_requests=types.SimpleNamespace(get=captcha_get,post=captcha_post)
    original_requests=sys.modules.get("requests");sys.modules["requests"]=fake_captcha_requests
    original_check_output=kuaishou_hq.subprocess.check_output
    original_browser_fp=kuaishou_hq.generate_browser_fingerprint
    original_gpu_info=kuaishou_hq.generate_gpu_info
    original_trajectory=kuaishou_hq.Generate_trajectory
    encrypt_calls=[];trajectory_calls=[]
    kuaishou_hq.subprocess.check_output=lambda argv,**kwargs:(encrypt_calls.append((argv,kwargs)) or "encrypted-param\n")
    kuaishou_hq.generate_browser_fingerprint=lambda:{"userAgent":"captcha-agent","fp":"browser"}
    kuaishou_hq.generate_gpu_info=lambda:{"gpu":"test"}
    class FakeTrajectory:
        def get_slide_track(self,distance):trajectory_calls.append(distance);return "track-data"
    kuaishou_hq.Generate_trajectory=FakeTrajectory
    captcha_output=io.StringIO()
    try:
        with contextlib.redirect_stdout(captcha_output):
            captcha_ok=captcha_tool.handle_captcha(
                {"data":{"captchaUrl":"https://captcha/?captchaSession=session-1&x=1"}})
    finally:
        kuaishou_hq.subprocess.check_output=original_check_output
        kuaishou_hq.generate_browser_fingerprint=original_browser_fp
        kuaishou_hq.generate_gpu_info=original_gpu_info
        kuaishou_hq.Generate_trajectory=original_trajectory
        if original_requests is None:sys.modules.pop("requests",None)
        else:sys.modules["requests"]=original_requests
    assert captcha_ok is True and captcha_tool.verification_token=="captcha-token"
    assert captcha_output.getvalue().strip()=="验证码验证成功!"
    assert trajectory_calls==[int(94*3.42)]
    assert encrypt_calls[0][0][:2]==["C:/app/js/node.exe","C:/app/js/encrypt.js"]
    encrypted_plain=encrypt_calls[0][0][2]
    assert "captchaSn=sn-1" in encrypted_plain and "relativeX=94" in encrypted_plain
    assert "relativeY=9" in encrypted_plain and "trajectory=track-data" in encrypted_plain
    assert "%27gpu%27%3A%20%27test%27" in encrypted_plain
    assert encrypt_calls[0][1]=={"encoding":"utf-8"}
    config_call=captcha_calls[0]
    assert config_call[1].endswith("/rest/zt/captcha/sliding/config")
    assert config_call[2]["params"]=={"captchaSession":"session-1"}
    assert config_call[2]["headers"]["Cookie"]=="did=captcha"
    verify_call=captcha_calls[-1]
    assert verify_call[0]=="post" and verify_call[1].endswith("/sliding/kSecretApiVerify")
    assert verify_call[2]["json"]=={"verifyParam":"encrypted-param"}
    assert verify_call[2]["headers"]["User-Agent"]=="captcha-agent"
    no_captcha_output=io.StringIO()
    original_requests=sys.modules.get("requests");sys.modules["requests"]=fake_captcha_requests
    try:
        with contextlib.redirect_stdout(no_captcha_output):
            assert captcha_tool.handle_captcha({"data":{}}) is False
    finally:
        if original_requests is None:sys.modules.pop("requests",None)
        else:sys.modules["requests"]=original_requests
    assert no_captcha_output.getvalue().strip()=="未找到验证码URL"
    original_randint=kuaishou_hq.random.randint
    original_uniform=kuaishou_hq.random.uniform
    randint_values=iter([10,20,20,10,0])
    randint_ranges=[];uniform_ranges=[]
    kuaishou_hq.random.randint=lambda low,high:(randint_ranges.append((low,high)) or next(randint_values))
    kuaishou_hq.random.uniform=lambda low,high:(uniform_ranges.append((low,high)) or 1.0)
    try:track=kuaishou_hq.Generate_trajectory.get_slide_track(10)
    finally:
        kuaishou_hq.random.randint=original_randint
        kuaishou_hq.random.uniform=original_uniform
    assert track=="10|20|0,10|20|10"
    assert randint_ranges==[(10,30),(10,30),(20,30),(10,50),(-3,3)]
    assert uniform_ranges==[(0.9,1.1)]
    for invalid_distance in (-1,1.2,"2"):
        try:kuaishou_hq.Generate_trajectory.get_slide_track(invalid_distance)
        except ValueError as error:
            assert str(error)==f"distance类型必须是大于等于0的整数: {invalid_distance}"
        else:raise AssertionError("invalid trajectory distance must raise ValueError")
    original_choice=kuaishou_hq.random.choice
    original_randint=kuaishou_hq.random.randint
    gpu_choices=iter(["Intel","UHD","12","Mozilla WebGL","Mozilla"])
    gpu_ints=iter([808,31,21,15000,9000])
    choice_pools=[];gpu_ranges=[]
    kuaishou_hq.random.choice=lambda values:(choice_pools.append(list(values)) or next(gpu_choices))
    kuaishou_hq.random.randint=lambda low,high:(gpu_ranges.append((low,high)) or next(gpu_ints))
    try:gpu_info=json.loads(kuaishou_hq.generate_gpu_info())
    finally:
        kuaishou_hq.random.choice=original_choice
        kuaishou_hq.random.randint=original_randint
    assert gpu_info=={
        "glRenderer":"Mozilla WebGL","glVendor":"Mozilla",
        "unmaskRenderer":"ANGLE (Intel, Intel(R) UHD Graphics 808 Direct3D12 vs_5_0 ps_5_0, D3D12-31.21.15000.9000)",
        "unmaskVendor":"Google Inc. (Intel)",
    }
    assert choice_pools==[
        ["Intel","NVIDIA","AMD"],["HD","UHD","Iris"],["11","12"],
        ["WebKit WebGL","Mozilla WebGL"],["WebKit","Mozilla"],
    ]
    assert gpu_ranges==[(500,999),(20,31),(0,21),(10000,15000),(1000,9000)]
    original_random=kuaishou_hq.random.random
    original_time=kuaishou_hq.time.time
    original_randint=kuaishou_hq.random.randint
    fingerprint_ranges=[]
    kuaishou_hq.random.random=lambda:0.125
    kuaishou_hq.time.time=lambda:1700000000.5
    kuaishou_hq.random.randint=lambda low,high:(fingerprint_ranges.append((low,high)) or 54321)
    try:fingerprint=kuaishou_hq.generate_fingerprint()
    finally:
        kuaishou_hq.random.random=original_random
        kuaishou_hq.time.time=original_time
        kuaishou_hq.random.randint=original_randint
    assert fingerprint==hashlib.md5(b"0.1251700000000.554321").hexdigest()
    assert fingerprint_ranges==[(10000,99999)]
    original_choice=kuaishou_hq.random.choice
    original_randint=kuaishou_hq.random.randint
    original_time=kuaishou_hq.time.time
    original_fingerprint=kuaishou_hq.generate_fingerprint
    original_did=kuaishou_hq.generate_did
    browser_choices=iter([1920,1050,"UTC+7","ja-JP",32,24])
    browser_ints=iter([137,12])
    browser_choice_pools=[];browser_ranges=[];fingerprint_calls=[]
    kuaishou_hq.random.choice=lambda values:(browser_choice_pools.append(list(values)) or next(browser_choices))
    kuaishou_hq.random.randint=lambda low,high:(browser_ranges.append((low,high)) or next(browser_ints))
    kuaishou_hq.time.time=lambda:1700000000.125
    kuaishou_hq.generate_fingerprint=lambda:(fingerprint_calls.append(True) or f"fp-{len(fingerprint_calls)}")
    kuaishou_hq.generate_did=lambda:"web_test_did"
    try:browser_fingerprint=kuaishou_hq.generate_browser_fingerprint()
    finally:
        kuaishou_hq.random.choice=original_choice
        kuaishou_hq.random.randint=original_randint
        kuaishou_hq.time.time=original_time
        kuaishou_hq.generate_fingerprint=original_fingerprint
        kuaishou_hq.generate_did=original_did
    expected_ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    assert browser_fingerprint=={
        "ua":expected_ua,"userAgent":expected_ua,"timeZone":"UTC+7","language":"ja-JP",
        "cpuCoreCnt":"12","platform":"Win64","resolution":"1920,1050",
        "pixelDepth":32,"colorDepth":24,"canvasGraph":"fp-1",
        "canvasGraphFingerPrint":"fp-2","webglGraph":"fp-3",
        "webglGraphFingerPrint":"fp-4","key1":"web_test_did",
        "key2":1700000000125,"key3":expected_ua,"key5":"ja-JP","key7":1920,"key8":1050,
    }
    assert browser_ranges==[(95,138),(4,16)]
    assert browser_choice_pools==[
        [1920,1680,1440,2560],[1080,1050,900,1440],
        ["UTC+8","UTC+7","UTC+9","UTC-5","UTC-4"],
        ["zh-CN","en-US","zh-TW","ja-JP"],[24,32],[24,32],
    ]
    assert len(fingerprint_calls)==4
    slide_events=[]
    class ExactSlideDetector:
        def slide_match(self,*args,**kwargs):
            slide_events.append((args,kwargs));return {"target":[77,8]}
    slide_tool=object.__new__(kuaishou_hq.Tool)
    slide_tool.det=ExactSlideDetector()
    assert slide_tool.slide_match(b"cut",b"background")=={"target":[77,8]}
    assert slide_events==[((b"cut",b"background"),{"simple_target":True})]
    tool_events=[]
    class RoomTool:
        def __init__(self,url):tool_events.append(("init",url))
        def getLiveRoomId(self):tool_events.append(("room",));return "fallback-room"
        def processLiveId(self,live_id):
            tool_events.append(("process",live_id))
            return {"data":{"result":1,"liveStreamId":"stream-1","token":"token-1",
                            "websocketUrls":["wss://one","wss://two"]}}
    original_tool=kuaishou_hq.Tool;kuaishou_hq.Tool=RoomTool
    try:
        info=asyncio.run(kslive_module.get_live_info_from_url("https://live.kuaishou.com/u/demo"))
    finally:kuaishou_hq.Tool=original_tool
    assert tool_events==[("init","https://live.kuaishou.com/u/demo"),("room",),("process","fallback-room")]
    assert info=={"live_stream_id":"stream-1","token":"token-1","ws_url":"wss://one"}
    class BrokenRoomTool(RoomTool):
        def getLiveRoomId(self):raise RuntimeError("room lookup failed")
    kuaishou_hq.Tool=BrokenRoomTool;output=io.StringIO()
    try:
        with contextlib.redirect_stdout(output):missing=asyncio.run(kslive_module.get_live_info_from_url("bad"))
    finally:kuaishou_hq.Tool=original_tool
    assert missing is None and output.getvalue().strip()=="获取直播间信息出错: room lookup failed"
    start_calls=[]
    async def start_connect():start_calls.append("connect")
    base._connect=start_connect
    assert asyncio.run(base.start()) is None and start_calls==["connect"]
    async def failed_start_connect():raise RuntimeError("connect failed")
    base._connect=failed_start_connect
    try:asyncio.run(base.start())
    except RuntimeError as error:assert str(error)=="connect failed"
    else:raise AssertionError("start must propagate _connect failures")
    assert len(base.page_id)>16 and len(base.sec_websocket_key)>0
    assert base._get_headers()["Sec-WebSocket-Key"]==base.sec_websocket_key
    encoded_bytes=bytes.fromhex(base.encoded_data)
    enter_kind,enter_payload=decode_frame(encoded_bytes)
    enter=proto.CSWebEnterRoom.FromString(enter_payload)
    assert enter_kind==proto.CS_ENTER_ROOM and enter.liveStreamId=="stream"
    assert enter.token=="token" and enter.pageId==base.page_id
    class Socket:
        def __init__(self):self.sent=[]
        async def send(self,value):self.sent.append(value)
    socket=Socket();output=io.StringIO()
    with contextlib.redirect_stdout(output):asyncio.run(base._send_initial_data(socket))
    assert socket.sent==[encoded_bytes]
    assert output.getvalue().strip()=="[数据][None] 初始数据已发送"
    task_events=[]
    async def heartbeat(ws):task_events.append(("heartbeat",ws))
    async def messages(ws):task_events.append(("messages",ws))
    base._send_heartbeat=heartbeat;base._on_message=messages
    socket=Socket();output=io.StringIO()
    with contextlib.redirect_stdout(output):asyncio.run(base._on_open(socket))
    assert task_events==[("heartbeat",socket),("messages",socket)]
    assert socket.sent==[encoded_bytes]
    assert output.getvalue().splitlines()==[
        "[已连接][None] WebSocket连接已建立","[数据][None] 初始数据已发送"]
    base._send_heartbeat=KuaishouLiveClient._send_heartbeat.__get__(base,KuaishouLiveClient)
    heartbeat_socket=Socket();heartbeat_waits=[]
    original_time,original_sleep=kslive_module.time,asyncio.sleep
    kslive_module.time=lambda:123.456
    async def stop_after_interval(delay):
        heartbeat_waits.append(delay);raise asyncio.CancelledError
    asyncio.sleep=stop_after_interval;output=io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            try:asyncio.run(base._send_heartbeat(heartbeat_socket))
            except asyncio.CancelledError:pass
    finally:
        kslive_module.time=original_time;asyncio.sleep=original_sleep
    heartbeat_kind,heartbeat_payload=decode_frame(heartbeat_socket.sent[0])
    heartbeat=proto.CSWebHeartbeat.FromString(heartbeat_payload)
    assert heartbeat_kind==proto.CS_HEARTBEAT and heartbeat.timestamp==123456
    assert heartbeat_waits==[20]
    assert output.getvalue().strip()=="[心跳][None] 心跳包已发送，时间: 123456"
    class Frames:
        def __init__(self,values):self.values=iter(values)
        def __aiter__(self):return self
        async def __anext__(self):
            try:return next(self.values)
            except StopIteration:raise StopAsyncIteration
    sent.clear()
    valid=proto.SocketMessage(payloadType=proto.SC_FEED_PUSH,
        compressionType=proto.SocketMessage.NONE,payload=feed.SerializeToString()).SerializeToString()
    output=io.StringIO()
    with contextlib.redirect_stdout(output):asyncio.run(client._on_message(Frames([b"bad",valid])))
    assert output.getvalue().startswith("[解析错误] ") and sent[-1]["type"]=="stats"
    reconnects=[]
    async def reconnect():reconnects.append("reconnect")
    base._reconnect=reconnect
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        asyncio.run(base._on_error(None,RuntimeError("断线")))
        asyncio.run(base._on_close(None))
    assert reconnects==["reconnect","reconnect"]
    assert output.getvalue().splitlines()==[
        "[错误] 断线",
        "[已关闭] WebSocket连接已关闭",
        "[已关闭] WebSocket连接已关闭",
    ]
    base._reconnect=KuaishouLiveClient._reconnect.__get__(base,KuaishouLiveClient)
    events=[];base.reconnect_attempts=2;base._calculate_reconnect_delay=lambda:1.25
    async def connect():events.append("connect")
    async def sleep(delay):events.append(("sleep",delay))
    base._connect=connect
    original_sleep=asyncio.sleep;asyncio.sleep=sleep;output=io.StringIO()
    try:
        with contextlib.redirect_stdout(output):result=asyncio.run(base._reconnect())
    finally:asyncio.sleep=original_sleep
    assert result is None and base.reconnect_attempts==3
    assert events==[("sleep",1.25),"connect"]
    assert output.getvalue().strip()=="[重连] 第3次尝试，等待 1.25 秒..."
    base.reconnect_attempts=10;events.clear();output=io.StringIO()
    with contextlib.redirect_stdout(output):result=asyncio.run(base._reconnect())
    assert result is None and not events
    assert output.getvalue().strip()=="[重连] 达到最大重连尝试次数 (10)，放弃连接"

def verify_text_special_variables():
    import recovered.text_processing as processing
    assert [processing._num_to_chinese(value) for value in (0,9,10,11,20,23,99,100,-1)] == [
        "零","九","十","十一","二十","二十三","九十九","100","-1"
    ]
    original_choice=processing.random.choice
    try:
        processing.random.choice=lambda values:values[-1]
        assert processing.process_script_options("欢迎{上午好|下午好}，{单项}")=="欢迎下午好，{单项}"
    finally:processing.random.choice=original_choice
    assert processing.parse_qa_info_from_text("问：价格\n答：九十九\n\n问：库存\n答：充足") == [
        {"question":"价格","answer":"九十九"},{"question":"库存","answer":"充足"}
    ]
    assert processing.parse_qa_info_from_text("前缀问：价格\n答：九十九") == []
    assert processing.parse_qa_info_from_text("问：价格\r\n答：九十九") == [
        {"question":"价格","answer":"九十九"}
    ]
    original=processing.datetime
    class AtFive:
        @classmethod
        def now(cls):return type("Moment",(),{"hour":13,"minute":5})()
    class OnHour:
        @classmethod
        def now(cls):return type("Moment",(),{"hour":23,"minute":0})()
    try:
        processing.datetime=AtFive
        assert processing.process_special_variables("现在{time}，{min_left}分钟后到{next_h}")=="现在十三点五分，五十五分钟后到十四点"
        processing.datetime=OnHour
        assert processing.process_special_variables("{time}|{min_left}|{next_h}")=="二十三点|零|零点"
    finally:processing.datetime=original
    assert processing.strip_prohibited_words("哎呀嘿哎哟哦喔正常词敏感词",["敏感词",""])=="正常词"
    assert processing.strip_prohibited_words("正常话术",None)=="正常话术"
    qa=processing.parse_qa_info([{"question":"价格 多少钱","answer":"九十九元 今天优惠"}])
    assert qa=={"价格":["九十九元","今天优惠"],"多少钱":["九十九元","今天优惠"]}
    assert qa["价格"] is qa["多少钱"]
    assert processing.match_keywords("这个多少钱",qa) in {"九十九元","今天优惠"}
    assert processing.match_keywords("任意内容", {"": ["空键命中"]}) == "空键命中"
    assert processing.match_keywords("任意内容", {"": []}) is None
    overwritten=processing.parse_qa_info([{"question":"价格","answer":"旧"},{"question":"价格","answer":"新"}])
    assert overwritten=={"价格":["新"]}
    try: processing.parse_qa_info([{"keywords":["兼容键"],"answers":["不应接受"]}])
    except AttributeError: raise AssertionError("dict.get should not fail")
    else: assert "兼容键" not in processing.parse_qa_info([{"keywords":["兼容键"],"answers":["不应接受"]}])
    try: processing.parse_qa_info(["不是字典"])
    except AttributeError: pass
    else: raise AssertionError("binary parse_qa_info requires dict items")
    assert processing.contains_blocked("这是敏感内容", ["", "敏感"])
    assert not processing.contains_blocked("普通内容", ["", "敏感"])
    assert processing.is_user_blocked("黑名单用户123", ["", "用户12"])
    assert not processing.is_user_blocked("正常用户", ["", "黑名单"])

def verify_funasr_sentence_contract():
    from recovered import funasr_sentences as fs
    assert fs.TERMINAL_PUNCT=="。！？!?" and fs.SOFT_PUNCT=="，,；;、"
    assert fs.TARGET_SENTENCE_CHARS==50 and fs.HARD_MAX_SENTENCE_CHARS==80
    assert fs._split_text_by_terminal("第一句；仍是同句。第二句！")== ["第一句；仍是同句。","第二句！"]
    source=[{"start":0,"end":1000,"text":"甲"*29+"，"},
            {"start":1000,"end":2000,"text":"乙"*24+"；"},
            {"start":2000,"end":3000,"text":"丙"*9+"。"}]
    merged=fs.merge_timed_sentences(source)
    assert len(merged)==2 and len(merged[0]["text"])==55 and merged[0]["end"]==2000
    assert merged[1]["text"]=="丙"*9+"。"
    assert fs._normalize_text("  hello\n world  !  ")=="hello world!"
    assert fs._normalize_text("你 好 ， hello  world ！")=="你好， hello world！"
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);audio=root/"input.mp3";video=root/"input.mp4"
        audio.write_bytes(b"audio");video.write_bytes(b"video")
        events=[];original_load=fs.load_funasr_model;original_transcribe=fs.transcribe_with_funasr
        original_extract=fs._extract_audio_wav;original_cleanup=fs.cleanup_funasr_model
        model=object()
        fs.load_funasr_model=lambda _path:(events.append(("load",)) or model)
        fs.transcribe_with_funasr=lambda used,path:(events.append(("transcribe",Path(path).suffix)) or [{"sentence_info":[{"start":0,"end":100,"text":"测试。"}]}])
        def extract(source,target):
            events.append(("extract",Path(source).suffix));Path(target).write_bytes(b"wav");return target
        fs._extract_audio_wav=extract;fs.cleanup_funasr_model=lambda used:events.append(("cleanup",used is model))
        try:
            assert fs.recognize_media_sentences(str(audio),"weights")[0]["text"]=="测试。"
            assert events==[("load",),("transcribe",".mp3"),("cleanup",True)]
            events.clear();fs.recognize_media_sentences(str(video),"weights")
            assert events==[("load",),("extract",".mp4"),("transcribe",".wav"),("cleanup",True)]
            events.clear();fs._extract_audio_wav=lambda *_args:(_ for _ in ()).throw(RuntimeError("extract failed"))
            try:fs.recognize_media_sentences(str(video),"weights")
            except RuntimeError as error:assert str(error)=="extract failed"
            else:raise AssertionError("extract failure must propagate")
            assert events==[("load",),("cleanup",True)]
        finally:
            fs.load_funasr_model=original_load;fs.transcribe_with_funasr=original_transcribe
            fs._extract_audio_wav=original_extract;fs.cleanup_funasr_model=original_cleanup

def verify_get_srt_lifecycle():
    import recovered.get_srt as srt
    assert srt.normalize_subtitle_text("你 好 , 世界 . hello  world")=="你好,世界. hello world"
    rows=srt._build_subtitles_from_timestamps(
        {"text":"你好，世界！","timestamps":[[0,300],[300,700],[700,1000],[1000,1400]]},2000)
    assert rows==[(0,700,"你好，"),(700,1400,"世界！")]
    rows=srt._build_subtitles_from_timestamps(
        {"text":"甲，乙丙","timestamp":[[100,800],[800,1200]]},2000)
    assert rows==[(100,800,"甲，"),(800,1300,"乙丙")]
    text="甲"*25;pairs=[[index*100,(index+1)*100] for index in range(25)]
    rows=srt._build_subtitles_from_timestamps({"text":text,"timestamps":pairs},4000)
    assert [len(row[2]) for row in rows]==[24,1] and rows[0][1]==2400
    rows=srt._normalize_subtitle_timeline(
        [(0,1000,"甲"),(800,1400,"乙"),(900,1500,"丙"),(1400,1900,"丁")],2000)
    assert rows==[(0,1000,"甲"),(1000,1400,"乙"),(1400,1900,"丁")]
    rows=srt._build_subtitles_from_sentence_info(
        {"sentence_info":[{"start":"100.9","end":"700.8","text":"你 好"},
                          {"start":"bad","end":900,"text":"忽略"},
                          {"start":800,"text":"世界"}]},2000)
    assert rows==[(100,700,"你好")]
    original_text=srt.whisper_result_to_text
    srt.whisper_result_to_text=lambda _result:"甲，乙乙乙！丙丙"
    try:
        rows=srt._build_subtitles_from_plain_text({},6000)
        assert rows==[(0,1500,"甲，"),(1500,4500,"乙乙乙！"),(4500,6000,"丙丙")]
    finally:srt.whisper_result_to_text=original_text
    original_which=srt.shutil.which;original_run=srt.subprocess.run
    extracted=[]
    def extract_ok(command,**_kwargs):
        extracted.append(Path(command[-1]));Path(command[-1]).write_bytes(b"wav")
        return types.SimpleNamespace(returncode=0)
    try:
        srt.shutil.which=lambda _name:"ffmpeg";srt.subprocess.run=extract_ok
        first=srt._extract_audio_for_asr("same.mp4");second=srt._extract_audio_for_asr("same.mp4")
        assert first!=second and Path(first).is_file() and Path(second).is_file()
        Path(first).unlink();Path(second).unlink()
        def extract_fail(command,**_kwargs):
            extracted.append(Path(command[-1]));raise subprocess.CalledProcessError(1,command)
        srt.subprocess.run=extract_fail
        try:srt._extract_audio_for_asr("bad.mp4")
        except subprocess.CalledProcessError:pass
        else:raise AssertionError("subtitle audio extraction failure must propagate")
        assert not extracted[-1].exists()
    finally:
        srt.shutil.which=original_which;srt.subprocess.run=original_run
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);video=root/"input.mp4";video.write_bytes(b"video")
        audio=root/"temp.wav";events=[]
        originals=(srt._extract_audio_for_asr,srt.load_model,srt.transcribe_video,
                   srt.get_media_duration_ms,srt.save_srt,srt.save_debug_json,srt.cleanup_model)
        model=object()
        def extract(_path):audio.write_bytes(b"audio");events.append("extract");return str(audio)
        srt._extract_audio_for_asr=extract;srt.load_model=lambda _path:(events.append("load") or model)
        srt.transcribe_video=lambda _model,_path:{"text":"测试。","segments":[]}
        srt.get_media_duration_ms=lambda _path:1000
        srt.save_srt=lambda *_args:"output.srt";srt.save_debug_json=lambda *_args:"debug.json"
        srt.cleanup_model=lambda used:events.append(("cleanup",used is model))
        try:
            result=srt.generate_srt_for_video(str(video),"weights")
            assert result=={"srt_path":"output.srt","debug_json_path":"debug.json"}
            assert not audio.exists() and events[-1]==("cleanup",True)
            events.clear();srt.transcribe_video=lambda *_args:(_ for _ in ()).throw(RuntimeError("asr failed"))
            try:srt.generate_srt_for_video(str(video),"weights")
            except RuntimeError as error:assert str(error)=="asr failed"
            else:raise AssertionError("ASR failure must propagate")
            assert not audio.exists() and events[-1]==("cleanup",True)
        finally:
            (srt._extract_audio_for_asr,srt.load_model,srt.transcribe_video,
             srt.get_media_duration_ms,srt.save_srt,srt.save_debug_json,srt.cleanup_model)=originals

def verify_ip_agent_post_process_helpers():
    from PIL import Image,ImageDraw,ImageFont
    from recovered.tools.ip_agent import post_process
    assert post_process._hex_to_rgb("#20C997")==(32,201,151)
    assert post_process._template("missing")["id"]=="impact_yellow"
    image=Image.new("RGB",(1600,900),"white")
    canvas=post_process._cover_canvas(image)
    assert canvas.size==(1080,1440)
    draw=ImageDraw.Draw(canvas);font=ImageFont.load_default()
    assert post_process._text_width(draw,"abc",font)>0
    lines=post_process._wrap_title(draw,"a long title for wrapping",font,30,2)
    assert 1<=len(lines)<=2 and post_process._text_width(draw,lines[0],font)<=30
    with tempfile.TemporaryDirectory() as directory:
        source=Path(directory)/"source.bin";target=Path(directory)/"target.bin"
        source.write_bytes(b"asset")
        post_process._download_url_to_path(source.as_uri(),target)
        assert target.read_bytes()==b"asset"

def verify_origin_video_ffmpeg_reader():
    import contextlib
    import io
    import queue
    import numpy as np
    from recovered.origin_video_face_reader import VideoFaceReader
    reader=VideoFaceReader.__new__(VideoFaceReader)
    reader.width=2;reader.height=2;reader.stop_event=threading.Event()
    expected=np.arange(12,dtype=np.uint8).reshape(2,2,3)
    reader.capture=io.BytesIO(expected.tobytes())
    reader.raw_frames_queue=queue.Queue(maxsize=2)
    reader._capture_thread()
    assert np.array_equal(reader.raw_frames_queue.get_nowait(),expected)
    assert reader.raw_frames_queue.get_nowait() is None
    class Process:
        stderr=io.BytesIO(b"warning one\nwarning two\n")
    reader.ffmpeg_process=Process();reader.stop_event.clear();output=io.StringIO()
    with contextlib.redirect_stdout(output):reader._drain_stderr()
    assert "ffmpeg-warn: warning one" in output.getvalue()
    import shutil
    ffmpeg=shutil.which("ffmpeg")
    if ffmpeg:
        with tempfile.TemporaryDirectory() as directory:
            video=Path(directory)/"input.mp4"
            subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",
                            "testsrc=size=64x48:rate=25","-t","0.4","-pix_fmt","yuv420p",str(video)],check=True)
            class Pipeline:
                def detect_batch(self,frames):return [[] for _ in frames]
            live=VideoFaceReader.__new__(VideoFaceReader);live.device="cpu";live.detect_max_faces=1
            live.face_pipeline=Pipeline();live.batch_size=4;live.queue_buffer_size=32
            live.raw_frames_queue=queue.Queue(32);live.processed_frames_queue=queue.Queue(32)
            live.capture=live.ffmpeg_process=live.stderr_thread=live.capture_thread=live.preprocess_thread=None
            live.stop_event=threading.Event();live.video_path="";live.start_ms=0
            live.width=live.height=0;live.fps=25.;live.frame_count=0;live.internal_buffer=[]
            try:
                live.start_capture(str(video))
                frames,detections=live.read_ahead(12)
                assert len(frames)==len(detections)==12 and frames[0].shape==(48,64,3)
                assert np.array_equal(frames[0],frames[10])
                assert np.array_equal(frames[1],frames[11])
                original_process=live.ffmpeg_process
                try:
                    live.seek("invalid")
                except ValueError:
                    assert live.ffmpeg_process is original_process and original_process.poll() is None
                    continued,_=live.read_ahead(1)
                    assert np.array_equal(continued[0],frames[2])
                else:
                    raise AssertionError("Invalid seek accepted")
                assert live.seek(120) and original_process.poll() is not None
                sought,_=live.read_ahead(1)
                assert np.array_equal(sought[0],frames[3])
                assert live.rewind()
                rewound,_=live.read_ahead(1)
                assert np.array_equal(rewound[0],frames[0])
                threads=(live.capture_thread,live.preprocess_thread,live.stderr_thread)
                process=live.ffmpeg_process
            finally:
                live.stop_capture()
            assert process.poll() is not None and all(not thread.is_alive() for thread in threads)
            class SlowPreprocessor:
                def is_alive(self): return True
                def join(self, timeout): assert timeout == 2
            slow=SlowPreprocessor()
            live.preprocess_thread=slow
            try:
                live.start_capture(str(video))
            except RuntimeError as error:
                assert "上一段视频仍在停止" in str(error)
                assert live.stop_event.is_set() and live.preprocess_thread is slow
                assert live.ffmpeg_process is None
            else:
                raise AssertionError("Restart accepted before the prior preprocessor stopped")
            finally:
                live.preprocess_thread=None

def verify_barrage_port_cleanup():
    from recovered.ws_capture import BarrageCapture
    class Process:
        def __init__(self):self.actions=[]
        def poll(self):return None
        def terminate(self):self.actions.append("terminate")
        def wait(self,timeout):self.actions.append(("wait",timeout));return 0
    capture=BarrageCapture("other");process=Process();capture.process=process
    capture._clean_port(0)
    assert process.actions==["terminate",("wait",3)] and capture.process is None

def verify_product_image_pipeline():
    import contextlib
    import io
    import numpy as np
    from recovered.product_cutout import (_largest_components,_boxes_to_mask,_nms_boxes,
                                          _select_subject_boxes,_extract_subject,_compose_centered_bgr,
                                          ProductCutoutEngine)
    from recovered.product_image_popup import (_fit_frame,apply_product_image_jitter,
                                                clamp_product_image_jitter_level)
    mask=np.zeros((120,160),np.uint8);mask[20:100,40:120]=255;mask[2:5,2:5]=255
    largest=_largest_components(mask);assert largest[50,80]==255 and largest[3,3]==0
    boxes=_nms_boxes([[40,20,120,100],[42,22,118,98],[0,0,20,20]],[.9,.8,.4])
    assert len(boxes)==2
    selected=_select_subject_boxes(boxes,[.9,.4],(120,160));assert selected
    boxed=_boxes_to_mask((120,160),selected);assert boxed.shape==(120,160) and boxed.max()==255
    soft=np.zeros((120,160),np.float32);soft[20:100,40:120]=1
    subject=_extract_subject(soft,selected,[.9]);assert subject.max()==255
    rgb=np.zeros((120,160,3),np.uint8);rgb[20:100,40:120]=(255,0,0)
    composed=_compose_centered_bgr(rgb,subject);assert composed.shape==(768,768,3)
    assert np.array_equal(composed[0,0],(255,255,255)) and composed[384,384,2]>200
    fitted=_fit_frame(np.full((100,200,3),127,np.uint8));assert fitted.shape==(640,640,3)
    assert np.array_equal(fitted[0,0],(0,255,0))
    jittered=apply_product_image_jitter(fitted,1.25,640,640,level=10)
    assert jittered.shape==(640,640,3) and clamp_product_image_jitter_level(99)==10
    engine=ProductCutoutEngine();root=Path("/tmp/recovered-product-models")
    marker=object();engine._ready=True;engine._model_root=root
    engine._biref=engine._biref_transform=engine._dino=engine._dino_processor=marker
    output=io.StringIO()
    with contextlib.redirect_stdout(output):engine.unload()
    assert not engine.ready() and engine._model_root==root
    assert all(getattr(engine,name) is None for name in
               ("_biref","_biref_transform","_dino","_dino_processor"))
    assert output.getvalue().strip()=="[product.cutout] models unloaded"
    assert engine.cutout_bgr(None) is None and engine.cutout_bgr(np.zeros((2,2),np.uint8)) is None

def verify_environment_manifests():
    metadata={}
    site=ORIGINAL/"env"/"Lib"/"site-packages"
    for path in site.glob("*.dist-info/METADATA"):
        name=version=None
        for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
            if line.startswith("Name: "):name=line[6:].strip()
            elif line.startswith("Version: "):version=line[9:].strip()
            if name and version:break
        if name and version:metadata[re.sub(r"[-_.]+","-",name).lower()]=version
    for filename in ("requirements-core.txt","requirements-ai-cu118.txt","requirements-windows.txt"):
        for raw in (HERE/filename).read_text(encoding="utf-8").splitlines():
            value=raw.strip()
            if not value or value.startswith("#"):continue
            name,version=value.split("==",1);key=re.sub(r"[-_.]+","-",name).lower()
            assert metadata.get(key)==version,f"{filename}: {name}=={version}, packaged={metadata.get(key)}"

def verify_ip_agent_real_media_pipeline():
    import shutil
    ffmpeg,ffprobe=shutil.which("ffmpeg"),shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:return
    from recovered.ip_agent_post_process import (generate_cover,_generate_fallback_music,
                                                   mix_bgm,_probe_json,_has_audio,_video_duration)
    from recovered.add_subtitles_to_video import add_subtitles_to_video
    from recovered.face_hand_vad_split import clip_face_hand_video_group
    from recovered.face_hand_video_group import validate_face_hand_video_group,load_face_hand_video_group
    from recovered.record_live_manager import (_extract_real_shot_audio,_mix_real_shot_audio,
                                                _mux_real_shot_video,RecordLiveManager)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);video=root/"input.mp4";cover=root/"cover.jpg"
        bgm=root/"bgm.mp3";mixed=root/"mixed.mp4"
        subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",
                        "testsrc=size=320x240:rate=25","-f","lavfi","-i",
                        "sine=frequency=440:sample_rate=44100","-t","1.2","-c:v","libx264",
                        "-pix_fmt","yuv420p","-c:a","aac","-shortest",str(video)],check=True)
        assert _has_audio(video) and 1.1<=_video_duration(video)<=1.3
        assert Path(generate_cover(str(video),str(cover),title="Recovered Video")).stat().st_size>1000
        assert Path(_generate_fallback_music(bgm,"seed")).stat().st_size>1000
        assert Path(mix_bgm(str(video),str(bgm),str(mixed))).stat().st_size>1000
        streams=_probe_json(mixed)["streams"]
        assert {item.get("codec_type") for item in streams}>={"video","audio"}
        subtitle=root/"test.srt";subtitle.write_text(
            "1\n00:00:00,100 --> 00:00:01,000\nRecovered subtitle test\n",encoding="utf-8")
        for name,options in (("plain",{}),("styled",{"highlight_words":["subtitle"],"animation":"fade"})):
            rendered=root/f"{name}.mp4"
            assert Path(add_subtitles_to_video(video,subtitle,output_path=rendered,**options)).stat().st_size>1000
            assert {item.get("codec_type") for item in _probe_json(rendered)["streams"]}>={"video","audio"}
        group=root/"face_hand_group"
        clipped=clip_face_hand_video_group(str(video),str(video),output_dir=group,min_clip_ms=400,
                                           max_clip_ms=800,face_keep_min_ms=200,rms_silence_thres=.001)
        assert clipped["face_count"]==clipped["hand_count"]==2
        assert validate_face_hand_video_group(group)[0]
        loaded=load_face_hand_video_group(group)
        for path in loaded["face"]+loaded["hand"]:
            stream=next(item for item in _probe_json(path)["streams"] if item.get("codec_type")=="video")
            assert (stream["width"],stream["height"],stream["r_frame_rate"])==(1080,1920,"25/1")
        try:
            from pydub import AudioSegment
        except ImportError:
            sys.path.append(str(ORIGINAL/"env"/"Lib"/"site-packages"))
            from pydub import AudioSegment
        narration=root/"narration.wav";original=root/"original.wav";mixed_audio=root/"mixed.wav";announcement=root/"announcement.mp4"
        subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",
                        "sine=frequency=880:sample_rate=44100","-t","0.6","-ac","1",str(narration)],check=True)
        _extract_real_shot_audio(str(video),str(original));source_audio=AudioSegment.from_wav(original)
        narration_audio=AudioSegment.from_wav(narration);mixed_segment=_mix_real_shot_audio(source_audio,narration_audio,.2,.8)
        with mixed_segment.export(mixed_audio,format="wav"):pass
        _mux_real_shot_video(str(video),str(mixed_audio),str(announcement))
        assert abs(len(mixed_segment)-len(source_audio))<5
        assert {item.get("codec_type") for item in _probe_json(announcement)["streams"]}>={"video","audio"}
        class InsertPlayer:
            def __init__(self):self._insert_worker=None;self.inserted=[]
            def insert_video(self,path):
                self.inserted.append(path);self._insert_worker=object()
                threading.Timer(.1,lambda:setattr(self,"_insert_worker",None)).start()
        manager=RecordLiveManager({});manager.video_player=InsertPlayer();manager.is_broadcasting=True
        manager.announcement_session={"is_active":True,"temp_files":[],"worker_thread":object()}
        manager._synthesize_local_audio=lambda **_kwargs:str(narration)
        manager._process_real_shot_task(str(video),.2,.8,{"voice_id":"test","audio_text":"test"})
        assert len(manager.video_player.inserted)==1
        inserted_path=Path(manager.video_player.inserted[0])
        assert inserted_path.exists()
        assert manager.announcement_session["is_active"] is False and manager.announcement_session["temp_files"]==[]
        inserted_path.unlink()

def verify_ip_agent_project_schema_contract():
    from recovered.main import Api
    from recovered import add_subtitles_to_video as subtitle_module
    from recovered import ip_agent_post_process as post_process
    api=Api.__new__(Api)
    assert api._get_ip_agent_base_dir()==str(HERE/"assets"/"ip_agent_projects")
    assert api._get_ip_agent_project_dir("project-1")==str(HERE/"assets"/"ip_agent_projects"/"project-1")
    assert Path(api._get_ip_agent_project_info_path("project-1")).parts[-2:] == ("project-1", "project_info.yaml")
    info=api._default_ip_agent_project_info("project-1","演示项目")
    assert len(info)==51
    assert list(info)[:10]==["id","name","create_time","update_time","benchmark_url",
                            "benchmark_video_path","benchmark_transcript_path","original_script",
                            "rewrite_prompt","rewritten_script"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",info["create_time"])
    assert info["update_time"]==info["create_time"] and info["selected_language"]=="zh-CN"
    assert info["voice_speed"]==1.0 and info["bgm_volume"]==0.16
    assert info["subtitle_style_preset"]=="classic_white"
    assert info["subtitle_highlight_enabled"] is True and info["subtitle_animation"]=="fade"
    assert info["publish_platforms"]==["douyin"] and info["publish_accounts"]=={}
    assert "created_at" not in info and "status" not in info
    result_dir=Path(api._get_ip_agent_project_dir("project-1"))/"result"
    assert info["audio_path"]==info["preview_audio_path"]==str(result_dir/"口播音频.wav")
    assert info["video_path"]==info["result_video_path"]==str(result_dir/"数字人口播.mp4")
    assert info["subtitle_path"]==info["subtitle_srt_path"]==str(result_dir/"口播字幕.srt")
    assert info["subtitle_video_path"]==info["subtitled_video_path"]==str(result_dir/"字幕成片.mp4")
    assert info["final_video_path"]==str(result_dir/"最终成片.mp4")
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);project=root/"project-1";sample=project/"result"/"sample.jpg"
        api._get_ip_agent_project_dir=lambda _project_id:str(project)
        api._encode_preview_image=lambda path:"preview:"+str(path)
        summary=api._build_ip_agent_project_summary("project-1",{
            "name":"","create_time":"2026-01-01 01:02:03","cover_path":"missing.jpg",
        })
        assert summary=={
            "id":"project-1","name":"IP项目-project-1",
            "create_time":"2026-01-01 01:02:03","update_time":"2026-01-01 01:02:03",
            "preview_url":"preview:"+str(sample),"path":os.path.abspath(project),
        }
        sample.parent.mkdir(parents=True);sample.write_bytes(b"jpg")
        summary=api._build_ip_agent_project_summary("project-1",{
            "name":"项目","create_time":"c","update_time":"u","cover_path":str(sample),
        })
        assert summary["preview_url"]=="preview:"+str(sample) and summary["update_time"]=="u"
    originals=(post_process.list_music_library,post_process.list_font_options,
               post_process.list_cover_templates,subtitle_module.SUBTITLE_STYLE_PRESETS)
    calls=[]
    try:
        post_process.list_music_library=lambda **kwargs:(calls.append(kwargs) or ["music"])
        post_process.list_font_options=lambda:["font"]
        post_process.list_cover_templates=lambda:["cover"]
        subtitle_module.SUBTITLE_STYLE_PRESETS={
            "plain":{"highlight_color":"#123456"},
            "named":{"font_name":"Custom Font"},
        }
        assets=api.get_ip_agent_creation_assets()
        assert assets=={"status":"success","music":["music"],"fonts":["font"],
                       "cover_templates":["cover"],"subtitle_styles":[
                           {"value":"plain","font_name":"Microsoft YaHei","highlight_color":"#123456"},
                           {"value":"named","font_name":"Custom Font","highlight_color":""},
                       ]}
        assert calls==[{"limit":80}]
        post_process.list_music_library=lambda **_kwargs:(_ for _ in ()).throw(RuntimeError("资源损坏"))
        assert api.get_ip_agent_creation_assets()=={"error":"获取IP智能体资源失败: 资源损坏"}
    finally:
        (post_process.list_music_library,post_process.list_font_options,
         post_process.list_cover_templates,subtitle_module.SUBTITLE_STYLE_PRESETS)=originals
    with tempfile.TemporaryDirectory() as directory:
        project=Path(directory)/"saved-project"
        storage_api=Api.__new__(Api)
        storage_api._get_ip_agent_project_dir=lambda _project_id:str(project)
        storage_api._get_ip_agent_project_info_path=lambda _project_id:str(project/"project_info.yaml")
        assert storage_api._load_ip_agent_project("saved-project") is None
        try:
            storage_api._save_ip_agent_project("saved-project",{})
        except FileNotFoundError as error:
            assert str(error)=="IP项目不存在"
        else:
            raise AssertionError("saving a missing IP project must fail")
        project.mkdir()
        storage_api._write_yaml_file(project/"project_info.yaml",{
            "id":"stale-id","name":"已有名称","create_time":"",
            "voice_speed":1.25,"subtitle_debug_json_path":"debug.json",
            "cover_path":"missing.jpg","result_video_path":"result.mp4",
            "result_video_preview_path":"preview.mp4",
        })
        storage_api._encode_preview_image=lambda path:"preview:"+str(path)
        preview_calls=[]
        storage_api._resolve_browser_preview_path=lambda video,preview:(
            preview_calls.append((video,preview)) or "resolved:"+video
        )
        loaded=storage_api._load_ip_agent_project("saved-project")
        assert loaded["id"]=="saved-project" and loaded["path"]==os.path.abspath(project)
        assert loaded["preview_url"]=="preview:"+str(project/"result"/"sample.jpg")
        assert loaded["result_video_preview_path"]=="resolved:result.mp4"
        assert preview_calls==[("result.mp4","preview.mp4")]
        saved=storage_api._save_ip_agent_project("saved-project",{
            "id":"attempted-id","name":"新名称","create_time":"",
            "voice_speed":1.5,"subtitle_debug_json_path":"remove-me",
        })
        assert saved["id"]=="saved-project" and saved["name"]=="新名称"
        assert saved["voice_speed"]==1.5 and saved["bgm_volume"]==0.16
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",saved["create_time"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",saved["update_time"])
        persisted=storage_api._read_yaml_file(project/"project_info.yaml")
        assert "subtitle_debug_json_path" not in persisted and "path" not in persisted
        assert persisted["id"]=="saved-project" and len(persisted)>=47
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)/"projects"
        project_api=Api.__new__(Api)
        project_api._get_ip_agent_base_dir=lambda:str(root)
        assert project_api.create_ip_agent_project("")=={"error":"请输入项目名称"}
        assert project_api.create_ip_agent_project("   ")=={"error":"请输入项目名称"}
        created=project_api.create_ip_agent_project("  第一个项目  ")
        assert created["status"]=="success" and created["project"]["name"]=="第一个项目"
        first_id=created["project"]["id"]
        assert re.fullmatch(r"[0-9a-f]{32}",first_id)
        assert (root/first_id/"project_info.yaml").is_file()
        second_id="second-project";second_dir=root/second_id;second_dir.mkdir()
        second=project_api._default_ip_agent_project_info(second_id,"第二个项目")
        second["create_time"]="2025-01-01 00:00:00"
        second["update_time"]="2099-01-01 00:00:00"
        project_api._write_yaml_file(second_dir/"project_info.yaml",second)
        (root/"ordinary-file.txt").write_text("ignored")
        listed=project_api.get_all_ip_agent_projects()
        assert listed["status"]=="success"
        assert [item["id"] for item in listed["projects"]][:2]==[second_id,first_id]
        assert set(listed["projects"][0])=={
            "id","name","create_time","update_time","preview_url","path",
        }
        failing_api=Api.__new__(Api)
        failing_api._get_ip_agent_base_dir=lambda:str(Path(directory)/"failed")
        failing_api._save_ip_agent_project=lambda *_args:(_ for _ in ()).throw(OSError("写入失败"))
        assert failing_api.create_ip_agent_project("项目")=={
            "error":"创建IP项目失败: 写入失败",
        }
        file_base=Path(directory)/"not-a-directory";file_base.write_text("x")
        failing_api._get_ip_agent_base_dir=lambda:str(file_base)
        list_error=failing_api.get_all_ip_agent_projects()
        assert set(list_error)=={"error"}
        assert list_error["error"].startswith("获取IP项目列表失败: ")
        media=Path(directory)/"sample.mp4";media.write_bytes(b"video")
        encoder=Api.__new__(Api)
        assert encoder._INLINE_MEDIA_MAX_BYTES==64*1024*1024
        assert encoder._encode_media_data("")==""
        assert encoder._encode_media_data(str(Path(directory)/"absent.bin"))==""
        assert encoder._encode_media_data(str(media))=="data:video/mp4;base64,dmlkZW8="
        unknown=Path(directory)/"payload.unknown-extension";unknown.write_bytes(b"x")
        assert encoder._encode_media_data(str(unknown))=="data:application/octet-stream;base64,eA=="
        encoder._INLINE_MEDIA_MAX_BYTES=4
        assert encoder._encode_media_data(str(media))==""
        assert encoder._encode_media_data(str(root))==""
        media_api=Api.__new__(Api);encoded=[]
        media_api._encode_media_data=lambda path:(encoded.append(path) or "data:video/mp4;base64,dmideo=")
        assert media_api.get_ip_agent_media_data(str(media))=={
            "status":"success","file_path":os.path.abspath(media),
            "data_url":"data:video/mp4;base64,dmideo=",
        }
        assert encoded==[os.path.abspath(media)]
        assert media_api.get_ip_agent_media_data(str(Path(directory)/"missing.mp4"))=={
            "error":"媒体文件不存在",
        }
        media_api._encode_media_data=lambda _path:""
        assert media_api.get_ip_agent_media_data(str(media))=={
            "error":"媒体文件过大或读取失败",
        }
        media_api._encode_media_data=lambda _path:(_ for _ in ()).throw(OSError("读取断开"))
        assert media_api.get_ip_agent_media_data(str(media))=={
            "error":"读取媒体失败: 读取断开",
        }
    api._load_ip_agent_project=lambda project_id:{"id":project_id,"name":"原始项目"}
    assert api.get_ip_agent_project("p1")=={
        "status":"success","project":{"id":"p1","name":"原始项目"},
    }
    api._load_ip_agent_project=lambda _project_id:{}
    assert api.get_ip_agent_project("missing")=={"error":"IP项目不存在"}
    api._load_ip_agent_project=lambda _project_id:(_ for _ in ()).throw(OSError("读取失败"))
    assert api.get_ip_agent_project("bad")=={"error":"获取IP项目失败: 读取失败"}
    saved=[]
    api._save_ip_agent_project=lambda project_id,data:(saved.append((project_id,data)) or data)
    assert api.update_ip_agent_project("p2",None)=={"status":"success","project":{}}
    assert api.update_ip_agent_project("p2",{"id":"changed","publish_tags":["#原样"]})=={
        "status":"success","project":{"id":"changed","publish_tags":["#原样"]},
    }
    assert saved==[("p2",{}),("p2",{"id":"changed","publish_tags":["#原样"]})]
    api._save_ip_agent_project=lambda *_args:(_ for _ in ()).throw(OSError("写入失败"))
    assert api.update_ip_agent_project("p2",{})=={"error":"保存IP项目失败: 写入失败"}
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);target=root/"delete-me";api._get_ip_agent_project_dir=lambda _project_id:str(target)
        assert api.delete_ip_agent_project("missing")=={"error":"IP项目不存在"}
        target.mkdir();(target/"data.txt").write_text("x")
        assert api.delete_ip_agent_project("delete-me")=={"status":"success","message":"删除成功"}
        assert not target.exists()

def verify_ip_agent_rewrite_contract():
    from recovered.main import Api
    from recovered import llm_base_chat, ip_agent_post_process

    api=Api.__new__(Api);api.config={"llm_config":{"provider":"native-config"}}
    calls=[];saved=[]
    original_chat=llm_base_chat.base_chat
    original_infer=ip_agent_post_process.infer_keywords_from_text
    try:
        llm_base_chat.base_chat=lambda *args,**kwargs:(
            calls.append((args,kwargs)) or json.dumps({
                "analysis":{"hook":"钩子弱","structure":["痛点","方案"]},
                "versions":[
                    {"name":"强钩子版","text":"三秒告诉你省钱方法"},
                    {"text":"先讲真实体验"},
                    "一句话快速版本",
                    {"name":"空版本","text":""},
                ],
                "keywords":"省钱，方法 省钱",
            },ensure_ascii=False)
        )
        ip_agent_post_process.infer_keywords_from_text=lambda text:["推断",text[:2]]
        api._get_ip_agent_project_dir=lambda project_id:"/missing/"+project_id
        result=api.rewrite_ip_script({"text":"  原始文案  ","prompt":"  更可信  ",
                                      "llm_config":{"provider":"request-config"}})
        assert result=={
            "status":"success","rewritten_text":"三秒告诉你省钱方法",
            "analysis":{"hook":"钩子弱","structure":["痛点","方案"]},
            "versions":[
                {"name":"强钩子版","text":"三秒告诉你省钱方法"},
                {"name":"改写版本2","text":"先讲真实体验"},
                {"name":"改写版本3","text":"一句话快速版本"},
            ],
            "keywords":["省钱","方法"],
        }
        args,kwargs=calls.pop()
        assert args[1].startswith("你是一名擅长短视频口播IP的爆款编导和文案医生。")
        assert "【用户要求】\n更可信" in args[0] and "【原始文案】\n原始文案" in args[0]
        assert '"name": "强钩子版"' in args[0] and "不要写分镜说明" in args[0]
        assert kwargs=={
            "model_type":"script","raise_on_failure":True,
            "llm_config":{"provider":"native-config"},
        }
        assert api.rewrite_ip_script({"script":"旧兼容字段"})=={
            "error":"请输入需要改写的文案",
        }
        llm_base_chat.base_chat=lambda *_args,**_kwargs:'{"versions": [], "rewritten_text": "直接成片稿"}'
        fallback=api.rewrite_ip_script({"text":"原文"})
        assert fallback["versions"]==[{"name":"成片稿","text":"直接成片稿"}]
        assert fallback["keywords"]==["推断","直接"]
        llm_base_chat.base_chat=lambda *_args,**_kwargs:'{"versions": []}'
        assert api.rewrite_ip_script({"text":"原文"})=={
            "error":"改写失败，未获得有效内容",
        }
        llm_base_chat.base_chat=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError("服务中断"))
        assert api.rewrite_ip_script({"text":"原文"})=={
            "error":"改写文案失败: 服务中断",
        }
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)/"p1";project.mkdir()
            api._get_ip_agent_project_dir=lambda _project_id:str(project)
            api._save_ip_agent_project=lambda project_id,data:(saved.append((project_id,data)) or {"id":project_id,**data})
            llm_base_chat.base_chat=lambda *_args,**_kwargs:json.dumps({
                "analysis":{"hook":"好"},"versions":[{"name":"成片","text":"最终稿"}],
                "keywords":[],
            },ensure_ascii=False)
            stored=api.rewrite_ip_script({"text":"输入稿","prompt":"","project_id":"p1"})
            assert stored["project"]["id"]=="p1"
            project_id,data=saved.pop()
            assert project_id=="p1"
            assert data=={
                "original_script":"输入稿",
                "rewrite_prompt":"保留原意，强化开头钩子、信息密度、口语节奏和行动引导，避免夸张虚假和空洞套话。",
                "rewritten_script":"最终稿","script_analysis":{"hook":"好"},
                "rewrite_versions":[{"name":"成片","text":"最终稿"}],
                "highlight_keywords":["推断","最终"],
            }
    finally:
        llm_base_chat.base_chat=original_chat
        ip_agent_post_process.infer_keywords_from_text=original_infer


def verify_generate_script_contract():
    from recovered.main import Api
    from recovered import generate_structured_speech as speech_module

    api=Api.__new__(Api);calls=[]
    original=speech_module.generate_structured_speech
    try:
        def fake_generate(content,instructions):
            calls.append((content,instructions))
            if content=="空结果":return "  "
            if content=="异常":raise RuntimeError("模型断开")
            return "话术-"+content
        speech_module.generate_structured_speech=fake_generate
        result=api.generate_script({
            "goods-a":{"content":"苹果"},
            2:{"content":"空结果"},
            "goods-c":{"title":"缺少内容"},
            "goods-d":{"content":"异常"},
            "goods-e":{"content":"香蕉"},
        },"口语化")
        assert calls==[("苹果","口语化"),("空结果","口语化"),("异常","口语化"),("香蕉","口语化")]
        assert result=={
            "script":"话术-苹果\n\n\n\n\n\n话术-香蕉",
            "failed_products":["2","goods-d"],
        }
        speech_module.generate_structured_speech=lambda *_args:""
        assert api.generate_script({"a":{"content":"x"},"b":{"content":"y"}})=={
            "script":"","failed_products":["a","b"],"error":"没有成功生成任何话术",
        }
        assert api.generate_script({"ignored":{"name":"无 content"}})=={
            "script":"","failed_products":[],
        }
        assert api.generate_script({})=={"script":"","failed_products":[]}
        try:api.generate_script([{"content":"x"}])
        except TypeError as error:assert str(error)=="product_info must be a dict"
        else:raise AssertionError("generate_script accepted a list")
        try:api.generate_script({},None)
        except TypeError as error:assert str(error)=="special_instructions must be a str"
        else:raise AssertionError("generate_script accepted a non-string instruction")
        class BrokenDict(dict):
            def items(self):raise RuntimeError("字典损坏")
        assert api.generate_script(BrokenDict({"x":1}))=={
            "script":"","failed_products":[],"error":"生成脚本时发生错误：字典损坏",
        }
    finally:
        speech_module.generate_structured_speech=original


def verify_ip_agent_publish_meta_contract():
    from recovered.main import Api
    from recovered import generate_title

    api=Api.__new__(Api);calls=[];saved=[]
    projects={
        "missing":None,
        "empty":{"rewritten_script":"","original_script":""},
        "fallback":{"rewritten_script":"  改写稿  ","original_script":"原稿",
                    "benchmark_url":"https://benchmark.example/video"},
        "original":{"rewritten_script":"","original_script":"  原始稿  ",
                    "benchmark_url":"https://benchmark.example/original"},
    }
    api._load_ip_agent_project=lambda project_id:projects.get(project_id)
    api._save_ip_agent_project=lambda project_id,data:(saved.append((project_id,data)) or {
        "id":project_id,**data,
    })
    original_generate=generate_title.generate_title_and_tags
    try:
        generate_title.generate_title_and_tags=lambda script,video_url:(
            calls.append((script,video_url)) or
            {"title":"  生产标题  ","tags":["#标签A","标签A"," 标签B "]}
        )
        assert api.generate_ip_agent_publish_meta("missing",{})=={"error":"IP项目不存在"}
        assert api.generate_ip_agent_publish_meta("empty",{})=={"error":"请先准备文案内容"}
        result=api.generate_ip_agent_publish_meta("fallback",{})
        assert calls.pop()==("改写稿","https://benchmark.example/video")
        assert saved.pop()==("fallback",{
            "publish_title":"生产标题","publish_tags_text":"#标签A #标签B",
        })
        assert result=={
            "status":"success","title":"生产标题","tags":["标签A","标签B"],
            "project":{"id":"fallback","publish_title":"生产标题",
                       "publish_tags_text":"#标签A #标签B"},
        }
        api.generate_ip_agent_publish_meta("original",{
            "script":"  请求文案  ","video_url":"https://request.example/video",
            "title":"不得覆盖","tags":["不得覆盖"],
        })
        assert calls.pop()==("请求文案","https://request.example/video")
        generate_title.generate_title_and_tags=lambda *_args,**_kwargs:(
            (_ for _ in ()).throw(RuntimeError("标题服务中断"))
        )
        assert api.generate_ip_agent_publish_meta("fallback",{})=={
            "error":"生成发布标题和标签失败: 标题服务中断",
        }
    finally:
        generate_title.generate_title_and_tags=original_generate


def verify_main_system_identity_contract():
    from recovered.main import Api

    api=Api.__new__(Api);api.config={"token":"  token-with-space  "}
    saved=[];updates=[]
    api._save_user_config=lambda value:saved.append(value)
    api._update_managers_config=lambda:updates.append(True)
    assert api.get_token()=={"status":"success","token":"  token-with-space  "}
    assert api.save_token("  replacement  ")=={"status":"success","message":"Token已保存"}
    assert saved.pop()=={"token":"  replacement  "}
    assert api.config["token"]=="  replacement  " and updates.pop() is True
    assert api.clear_token()=={"status":"success","message":"Token已清除"}
    assert saved.pop()=={"token":""} and api.config["token"]=="" and updates.pop() is True
    try:api.save_token(None)
    except TypeError as error:assert str(error)=="token must be a str"
    else:raise AssertionError("save_token accepted a non-string token")

    failing=Api.__new__(Api);failing.config={}
    failing._save_user_config=lambda _value:(_ for _ in ()).throw(OSError("配置只读"))
    failing._update_managers_config=lambda:None
    assert failing.save_token("x")=={"error":"配置只读"}
    assert failing.clear_token()=={"error":"配置只读"}
    class BrokenConfig:
        def get(self,*_args):raise RuntimeError("配置损坏")
    failing.config=BrokenConfig()
    assert failing.get_token()=={"error":"配置损坏"}

    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);web=root/"assets"/"web";web.mkdir(parents=True)
        api.base_dir=str(root)
        api._find_asset=lambda relative:root/relative
        assert api.get_admin_id()=={"status":"success","admin_id":None}
        (web/"id.txt").write_text(" 021 \n",encoding="utf-8")
        assert api.get_admin_id()=={"status":"success","admin_id":21}
        (web/"id.txt").write_text("admin-21",encoding="utf-8")
        assert api.get_admin_id()=={"status":"success","admin_id":None}

        assert api.get_oem_config()=={"status":"success","config":{}}
        (web/"oem_config.json").write_text(
            json.dumps({"window_name":"生产品牌","feature_flags":{"live":True}},ensure_ascii=False),
            encoding="utf-8",
        )
        assert api.get_oem_config()=={
            "status":"success","config":{"window_name":"生产品牌","feature_flags":{"live":True}},
        }
        (web/"oem_config.json").write_text("[]",encoding="utf-8")
        assert api.get_oem_config()=={"status":"success","config":{}}
        (web/"oem_config.json").write_text("{broken",encoding="utf-8")
        broken_oem=api.get_oem_config()
        assert broken_oem["status"]=="error" and broken_oem["config"]=={}
        assert broken_oem["message"].startswith("读取贴牌配置失败: ")

        assert api.get_background_image()=={"error":"背景图片不存在"}
        (web/"bg.png").write_bytes(b"\x89PNG\r\n")
        assert api.get_background_image()=={
            "status":"success","image_data":"data:image/png;base64,iVBORw0K",
        }

        assert api.get_local_version()=={"status":"success","version":"v000"}
        config_dir=root/"config";config_dir.mkdir()
        (config_dir/"config.yaml").write_text("version: '  v122-prod  '\n",encoding="utf-8")
        assert api.get_local_version()=={"status":"success","version":"v122-prod"}
        (config_dir/"config.yaml").write_text("version: '   '\n",encoding="utf-8")
        assert api.get_local_version()=={"status":"success","version":"v000"}
        (config_dir/"config.yaml").write_text("version: [broken\n",encoding="utf-8")
        assert api.get_local_version()["error"].startswith("获取本地版本号失败: ")


def verify_main_local_resources_contract():
    from recovered.main import Api

    calls=[]
    class CloneManagerStub:
        def get_local_models(self):
            calls.append(("get_local_models",))
            return ([{"model_name":"形象一","sample_data":"data:image/jpeg;base64,eA=="}],
                    [{"voice_name":"音色一","ref_audio_path":"/voices/v1/ref_audio.wav"}])
        def delete_model(self,name):
            calls.append(("delete_model",name))
        def delete_voice(self,name):
            calls.append(("delete_voice",name))

    api=Api.__new__(Api);api._clone_manager=CloneManagerStub()
    assert api.get_local_resources()=={
        "models":[{"model_name":"形象一","sample_data":"data:image/jpeg;base64,eA=="}],
        "voices":[{"voice_name":"音色一","ref_audio_path":"/voices/v1/ref_audio.wav"}],
        "status":"success",
    }
    assert calls.pop()==("get_local_models",)
    assert api.delete_model(" model-id ")=={"status":"success"}
    assert calls.pop()==("delete_model"," model-id ")
    assert api.delete_voice("voice-id")=={"status":"success"}
    assert calls.pop()==("delete_voice","voice-id")

    class FailingCloneManager:
        def get_local_models(self):raise RuntimeError("资源索引损坏")
        def delete_model(self,_name):raise FileNotFoundError("模型不存在")
        def delete_voice(self,_name):raise PermissionError("音色被占用")
    api._clone_manager=FailingCloneManager()
    assert api.get_local_resources()=={"error":"资源索引损坏"}
    assert api.delete_model("missing")=={"error":"删除模型失败: 模型不存在"}
    assert api.delete_voice("busy")=={"error":"删除音色失败: 音色被占用"}
    for method,value,message in (
        (api.delete_model,None,"model_name must be a str"),
        (api.delete_voice,1,"voice_name must be a str"),
    ):
        try:method(value)
        except TypeError as error:assert str(error)==message
        else:raise AssertionError("native unicode wrapper contract was not enforced")


def verify_main_file_dialog_contract():
    from recovered.main import Api
    from recovered import main as main_module

    api=Api.__new__(Api);calls=[]
    class Window:
        def create_file_dialog(self,dialog_type):
            calls.append(dialog_type)
            return dialog_results.pop(0)
    fake_webview=types.SimpleNamespace(
        OPEN_DIALOG="open-kind",FOLDER_DIALOG="folder-kind",windows=[Window()],
    )
    previous_webview=sys.modules.get("webview");dialog_results=[("/tmp/a.txt","/tmp/b.txt"),[],None]
    try:
        sys.modules["webview"]=fake_webview
        assert api.open_file_dialog()=={
            "status":"success","files":("/tmp/a.txt","/tmp/b.txt"),
        }
        assert calls.pop()=="open-kind"
        assert api.open_file_dialog(1)=={"status":"cancelled","files":[]}
        assert calls.pop()=="folder-kind"
        assert api.open_file_dialog("truthy")=={"status":"cancelled","files":[]}
        assert calls.pop()=="folder-kind"
        fake_webview.windows=[]
        assert api.open_file_dialog()=={"error":"list index out of range"}
    finally:
        if previous_webview is None:sys.modules.pop("webview",None)
        else:sys.modules["webview"]=previous_webview

    original_exists=main_module.os.path.exists
    original_popen=main_module.subprocess.Popen
    original_platform=main_module.sys.platform
    had_startfile=hasattr(main_module.os,"startfile")
    original_startfile=getattr(main_module.os,"startfile",None)
    launched=[]
    try:
        main_module.os.path.exists=lambda path:path!="missing"
        main_module.subprocess.Popen=lambda command:launched.append(("popen",command))
        main_module.os.startfile=lambda path:launched.append(("startfile",path))

        assert api.open_directory("missing")=={"error":"目录不存在"}
        main_module.sys.platform="win32"
        assert api.open_directory("C:\\数字人\\素材")=={"status":"success"}
        assert launched.pop()==("startfile","C:\\数字人\\素材")
        main_module.sys.platform="darwin"
        assert api.open_directory("/tmp/中文")=={"status":"success"}
        assert launched.pop()==("popen",["open","/tmp/中文"])
        main_module.sys.platform="linux"
        assert api.open_directory("relative-file.txt")=={"status":"success"}
        assert launched.pop()==("popen",["xdg-open","relative-file.txt"])
        main_module.subprocess.Popen=lambda _command:(_ for _ in ()).throw(OSError("启动失败"))
        assert api.open_directory("existing")=={"error":"启动失败"}
        try:api.open_directory(Path("not-unicode"))
        except TypeError as error:assert str(error)=="path must be a str"
        else:raise AssertionError("open_directory accepted a non-string path")
    finally:
        main_module.os.path.exists=original_exists
        main_module.subprocess.Popen=original_popen
        main_module.sys.platform=original_platform
        if had_startfile:main_module.os.startfile=original_startfile
        else:delattr(main_module.os,"startfile")


def verify_main_live_sticker_project_contract():
    from recovered.main import Api

    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);api=Api.__new__(Api);api.runtime_dir=root
        assert api._get_live_sticker_base_dir()==str(root/"assets"/"live_sticker_projects")
        project_a=Path(api._get_live_sticker_project_dir("project-a"))
        assert api._get_live_sticker_output_paths("project-a")=={
            "bg":str(project_a/"背景.png"),
            "fg_white":str(project_a/"前景贴片_绿底.png"),
            "fg_alpha":str(project_a/"前景贴片_透明.png"),
            "cover_raw":str(project_a/"直播间封面_原始.png"),
            "cover":str(project_a/"直播间封面.png"),
        }
        assert api.create_live_sticker_project("   ")=={"error":"请输入项目名称"}
        created=api.create_live_sticker_project("  生产贴片  ")
        assert created["status"]=="success"
        project=created["project"];project_id=project["id"]
        assert len(project_id)==36 and project["name"]=="生产贴片"
        assert project["status"]=="draft" and project["room_titles"]==[]
        assert project["fg_white_preview_url"]==""
        assert project["path"]==os.path.abspath(api._get_live_sticker_project_dir(project_id))
        expected_fields={
            "id","name","create_time","update_time","product_name","product_price",
            "product_selling_points","product_content","product_item_id","product_pic",
            "background_prompt","foreground_prompt","cover_prompt","bg_path","fg_white_path",
            "fg_alpha_path","cover_path","cover_raw_path","bg_size","fg_size","cover_size",
            "room_title","room_titles","title_model","last_error","status",
        }
        stored=api._read_yaml_file(api._get_live_sticker_project_info_path(project_id))
        assert set(stored)==expected_fields

        outputs=api._get_live_sticker_output_paths(project_id)
        Path(outputs["bg"]).write_bytes(b"bg-preview")
        Path(outputs["fg_white"]).write_bytes(b"green-preview")
        updated=api.update_live_sticker_project(project_id,{
            "name":"改名项目","bg_path":outputs["bg"],"fg_white_path":outputs["fg_white"],
            "room_titles":"标题一， 标题二", "id":"must-not-replace",
        })
        assert updated["status"]=="success"
        project=updated["project"]
        assert project["id"]==project_id and project["name"]=="改名项目"
        assert project["room_titles"]==["标题一","标题二"] and project["room_title"]=="标题一"
        assert project["fg_white_preview_url"]=="data:image/png;base64,Z3JlZW4tcHJldmlldw=="

        second_dir=Path(api._get_live_sticker_project_dir("legacy"));second_dir.mkdir(parents=True)
        legacy_green=second_dir/"前景贴片_绿底.png";legacy_green.write_bytes(b"legacy")
        api._write_yaml_file(second_dir/"project_info.yaml",{
            "name":"", "create_time":"2025-01-01 00:00:00",
            "room_title":"旧标题", "room_titles":None,
        })
        legacy=api.get_live_sticker_project("legacy")
        assert legacy["status"]=="success"
        assert legacy["project"]["name"]==""
        assert legacy["project"]["fg_white_path"]==str(legacy_green)
        assert legacy["project"]["room_titles"]==["旧标题"]

        projects=api.get_all_live_sticker_projects()
        assert projects["status"]=="success" and len(projects["projects"])==2
        summaries={item["id"]:item for item in projects["projects"]}
        assert summaries[project_id]["preview_url"]=="data:image/png;base64,YmctcHJldmlldw=="
        assert summaries["legacy"]["name"]=="贴片项目-legacy"
        assert summaries["legacy"]["status"]=="draft"

        Path(outputs["fg_alpha"]).write_bytes(b"alpha")
        Path(outputs["cover"]).write_bytes(b"cover")
        project.update({"fg_alpha_path":outputs["fg_alpha"],"cover_path":outputs["cover"]})
        api._archive_live_sticker_outputs(project_id,project)
        history=Path(api._get_live_sticker_history_dir(project_id))
        snapshots=list(history.iterdir())
        assert len(snapshots)==1
        assert {item.name for item in snapshots[0].iterdir()}=={
            "背景.png","前景贴片_绿底.png","前景贴片_透明.png","直播间封面.png",
        }

        assert api.get_live_sticker_project("missing")=={"error":"贴片项目不存在"}
        assert api.delete_live_sticker_project("missing")=={"error":"贴片项目不存在"}
        assert api.delete_live_sticker_project(project_id)=={
            "status":"success","message":"删除成功",
        }
        assert not Path(api._get_live_sticker_project_dir(project_id)).exists()
        for method,args,message in (
            (api.create_live_sticker_project,(None,),"name must be a str"),
            (api.get_live_sticker_project,(None,),"project_id must be a str"),
            (api.update_live_sticker_project,("legacy",None),"data must be a dict"),
            (api.delete_live_sticker_project,(1,),"project_id must be a str"),
        ):
            try:method(*args)
            except TypeError as error:assert str(error)==message
            else:raise AssertionError("live sticker native wrapper type contract was not enforced")


def verify_clone_manager_local_resources_contract():
    from recovered.clone_manager import CloneManager
    from recovered.product_kt_overlay import KT_BOARD_CACHE_NAME

    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);images=root/"images";voices=root/"voices"
        images.mkdir();voices.mkdir()
        manager=CloneManager({"runtime_dir":str(root),"image_base_dir":str(images),
                              "voice_base_dir":str(voices)})
        original_strftime=time.strftime
        try:
            time_value="2026-11-07 10:42:00"
            import recovered.clone_manager as clone_module
            clone_module.time.strftime=lambda _format:time_value
            model_dir=images/"model-a";voice_dir=voices/"voice-a"
            manager._create_model_info(model_dir,"形象 A","model-a",["v2","v1","v2"],
                                       "720p",720,1280,True,7)
            manager._create_voice_info(voice_dir,"音色 A","voice-a",["v3","v1","v3"])
        finally:
            clone_module.time.strftime=original_strftime

        model_info=yaml.safe_load((model_dir/"model_info.yaml").read_text(encoding="utf-8"))
        assert model_info=={"name":"形象 A","id":"model-a","create_time":time_value,
                           "provider":"image","supported_versions":["v1","v2"],
                           "resolution":"720p","width":720,"height":1280,
                           "kt_board":True,"kt_board_hit":7}
        voice_info=yaml.safe_load((voice_dir/"model_info.yaml").read_text(encoding="utf-8"))
        assert voice_info=={"name":"音色 A","id":"voice-a","create_time":time_value,
                           "provider":"voice","supported_versions":["v1","v3"]}
        assert not (voice_dir/"voice_info.yaml").exists()

        (model_dir/"sample.jpg").write_bytes(b"model-preview")
        (model_dir/KT_BOARD_CACHE_NAME).write_bytes(b"cache")
        (voice_dir/"ref_audio.wav").write_bytes(b"voice-preview")
        models,local_voices=manager.get_local_models()
        assert models==[{
            "id":"model-a","name":"形象 A","create_time":time_value,
            "sample_data":"data:image/jpeg;base64,bW9kZWwtcHJldmlldw==",
            "supported_versions":["v1","v2"],"resolution":"720p",
            "width":720,"height":1280,"kt_board":True,"kt_board_hit":7,
        }]
        assert local_voices==[{
            "id":"voice-a","name":"音色 A","create_time":time_value,
            "sample_data":"data:audio/wav;base64,dm9pY2UtcHJldmlldw==",
            "provider":"voice","supported_versions":["v1","v3"],
        }]

        from PIL import Image
        preview_source=root/"large-preview.png"
        Image.new("RGBA",(640,1200),(20,40,60,128)).save(preview_source)
        preview=manager._build_model_preview(preview_source)
        assert preview.startswith("data:image/jpeg;base64,")
        preview_bytes=base64.b64decode(preview.split(",",1)[1])
        with Image.open(BytesIO(preview_bytes)) as rendered:
            assert rendered.format=="JPEG" and rendered.mode=="RGB"
            assert rendered.size==(303,568)
        assert manager._build_model_preview(preview_source)==preview

        manager.delete_model("model-a");manager.delete_voice("voice-a")
        assert not model_dir.exists() and not voice_dir.exists()
        for method,bad in ((manager.delete_model,"../escape"),(manager.delete_voice,"nested/id")):
            try:method(bad)
            except ValueError as error:assert str(error)=="资源 ID 无效"
            else:raise AssertionError("resource traversal was accepted")


def verify_main_translate_text_contract():
    from recovered.main import Api
    from recovered import llm_reply

    api=Api.__new__(Api);calls=[]
    original=llm_reply.translate_text_llm
    try:
        llm_reply.translate_text_llm=lambda *args,**kwargs:(
            calls.append((args,kwargs)) or "translated"
        )
        assert api.translate_text("  保留空白  ","EN_us")=="translated"
        assert calls.pop()==(("  保留空白  ","en-US"),{"raise_on_failure":True})
        assert api.translate_text("","")=="translated"
        assert calls.pop()==(("","zh-CN"),{"raise_on_failure":True})
        long_text="x"*1200
        assert api.translate_text(long_text,"vi-VN")=="translated"
        assert calls.pop()==((long_text,"vi-VN"),{"raise_on_failure":True})
        llm_reply.translate_text_llm=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError("翻译服务断开"))
        assert api.translate_text("文本","en-US")=={"error":"翻译服务断开"}
        try:api.translate_text(None,"en-US")
        except TypeError as error:assert str(error)=="text must be a str"
        else:raise AssertionError("translate_text accepted non-string text")
        try:api.translate_text("文本",None)
        except TypeError as error:assert str(error)=="target_language must be a str"
        else:raise AssertionError("translate_text accepted non-string target language")
    finally:
        llm_reply.translate_text_llm=original


def verify_main_llm_config_contract():
    from recovered.main import Api
    from recovered import llm_base_chat

    api=Api.__new__(Api);api.config={};saved=[];updates=[]
    api._save_user_config=lambda value:saved.append(value)
    api._update_managers_config=lambda:updates.append(True)
    config={"vendor":"SiliconFlow","endpoint":" https://api.example ",
            "api_key":" key ","model":" model ","custom":"preserved"}
    result=api.save_llm_config(config)
    assert result=={"status":"success","message":"配置已保存到本地"}
    assert saved==[{"llm_config":config}] and api.config["llm_config"] is config
    assert updates==[True]
    failing=Api.__new__(Api);failing.config={}
    failing._save_user_config=lambda _value:(_ for _ in ()).throw(OSError("只读"))
    failing._update_managers_config=lambda:None
    assert failing.save_llm_config({"vendor":"x"})=={"error":"只读"}
    try:api.save_llm_config(None)
    except TypeError as error:assert str(error)=="llm_config_data must be a dict"
    else:raise AssertionError("save_llm_config accepted non-dict data")

    original_chat=llm_base_chat.base_chat;calls=[]
    full={"vendor":"OpenAI","model":"gpt","endpoint":"https://api","api_key":"secret"}
    try:
        llm_base_chat.base_chat=lambda **kwargs:(calls.append(kwargs) or " 好 ")
        assert api.test_llm_availability(full)=={
            "status":"success","message":"大模型服务正常","is_available":True,
            "is_recommended_provider":True,"provider":"openai",
        }
        assert calls.pop()=={
            "question":"回复一个字：好","sys_prompt":"你是一个助手",
            "chat_history":[],"llm_config":full,
        }
        missing=api.test_llm_availability({"vendor":"SiliconFlow","model":"","endpoint":"e","api_key":"k"})
        assert missing=={
            "status":"error",
            "message":"未检测到可用的大模型配置，请先在设置中配置硅基流动 API Key。",
            "is_available":False,"is_recommended_provider":False,"provider":"siliconflow",
        }
        llm_base_chat.base_chat=lambda **_kwargs:""
        assert api.test_llm_availability(full)=={
            "status":"error",
            "message":"当前大模型配置不可用，请检查设置中的模型参数，或改为配置硅基流动 API Key。",
            "is_available":False,"is_recommended_provider":False,"provider":"openai",
        }
        llm_base_chat.base_chat=lambda **_kwargs:(_ for _ in ()).throw(RuntimeError("连接超时"))
        assert api.test_llm_availability(full)=={
            "status":"error","message":"测试大模型服务时出错: 连接超时",
            "is_available":False,"is_recommended_provider":False,"provider":"openai",
        }
        assert api.test_llm_availability({"vendor":123,"model":"m","endpoint":"e","api_key":"k"})=={
            "status":"error","message":"测试大模型服务时出错: 'int' object has no attribute 'lower'",
            "is_available":False,"is_recommended_provider":False,"provider":"unknown",
        }
        try:api.test_llm_availability(None)
        except TypeError as error:assert str(error)=="llm_config must be a dict"
        else:raise AssertionError("test_llm_availability accepted non-dict data")
    finally:
        llm_base_chat.base_chat=original_chat


def verify_record_live_start_lifecycle():
    import contextlib
    import io
    import recovered.record_live_manager as record_module
    import recovered.video_player as player_module
    import recovered.deduplication_processor as dedup_module
    created=[];processor_configs=[]
    class FakeProcessor:
        def __init__(self,config):
            self.config=dict(config);processor_configs.append(self.config)
    class FakePlayer:
        fail=False
        def __init__(self,**kwargs):
            self.kwargs=kwargs;self.started=[];self.stopped=False;created.append(self)
        def start(self,*args,**kwargs):
            self.started.append((args,kwargs))
            if self.fail:raise RuntimeError("decoder failed")
        def stop(self):self.stopped=True
    original_player,original_processor=player_module.Player,dedup_module.DeduplicationFrameProcessor
    player_module.Player,dedup_module.DeduplicationFrameProcessor=FakePlayer,FakeProcessor
    try:
        missing=record_module.RecordLiveManager({})
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            assert missing.start_live("/definitely/missing/video.mp4") is False
        assert missing.last_error=="本地视频文件不存在: /definitely/missing/video.mp4"
        assert created==[] and output.getvalue().splitlines()==[
            "收到本地视频开播请求: /definitely/missing/video.mp4",
            "错误: 本地视频文件不存在: /definitely/missing/video.mp4",
        ]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"clip.mp4";source.write_bytes(b"video")
            manager=record_module.RecordLiveManager({})
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                assert manager.start_live(str(source),width=640,height=360,output_mode="vcam",
                                          deduplication_config={"enabled":False}) is True
            player=created[-1]
            assert player.kwargs=={"width":640,"height":360,"output_mode":"vcam","frame_processor":None}
            assert player.started==[((os.path.abspath(source),),{"loop":True})]
            assert manager.video_player is player and manager.is_broadcasting is True
            assert output.getvalue().splitlines()[-3:]==[
                "创建新的播放器实例。","正在启动播放器...","录播直播已成功启动。"
            ]
            enabled=record_module.RecordLiveManager({})
            with contextlib.redirect_stdout(io.StringIO()):
                assert enabled.start_live(str(source),deduplication_config={"enabled":True,"mirror":{}})
            assert processor_configs==[{"enabled":True,"mirror":{}}]
            assert isinstance(created[-1].kwargs["frame_processor"],FakeProcessor)
            FakePlayer.fail=True
            failed=record_module.RecordLiveManager({})
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                assert failed.start_live(str(source)) is False
            assert failed.last_error=="录播直播启动失败: decoder failed"
            assert created[-1].stopped and failed.video_player is None and not failed.is_broadcasting
            FakePlayer.fail=False
    finally:
        player_module.Player,dedup_module.DeduplicationFrameProcessor=original_player,original_processor

def verify_shopee_action_dispatch():
    import recovered.shopee_live_control as shopee_module
    from recovered.shopee_live_control import ShopeeLiveControl
    resource=ShopeeLiveControl();browser=object();resource._browser=browser
    resource._page=object();resource._context=object();resource._connected=True
    resource._session_id="sid";resource._initializing=True;disconnected=[]
    old_disconnect=shopee_module._disconnect_cdp
    try:
        shopee_module._disconnect_cdp=lambda value:disconnected.append(value)
        assert resource._safe_close_browser() is None
    finally:shopee_module._disconnect_cdp=old_disconnect
    assert disconnected==[browser] and resource._browser is None and resource._page is None and resource._context is None
    assert resource._connected is False and resource._session_id=="" and resource._initializing is False
    class Page:
        url="https://live.shopee.com.my/pc/live?session=session-1"
        class Locator:
            def count(self):return 0
        def __init__(self,context):self.context=context
        def is_closed(self):return False
        def locator(self,_selector):return self.Locator()
        def evaluate(self,script):
            if script==shopee_module._LIVE_WORKSPACE_JS:return True
            return ""
    class Context:
        def cookies(self):return [{"name":"SPC_EC","value":"token"}]
    context=Context();page=Page(context);browser=object();connected=[]
    lifecycle=ShopeeLiveControl();lifecycle._playwright=object();lifecycle._save_storage_state=lambda **kw:connected.append(("save",kw))
    originals=(shopee_module._is_cdp_ready,shopee_module._connect_cdp,shopee_module._cdp_context_and_page)
    try:
        shopee_module._is_cdp_ready=lambda *_args,**_kwargs:True
        shopee_module._connect_cdp=lambda playwright,**kw:connected.append(("connect",playwright,kw)) or browser
        shopee_module._cdp_context_and_page=lambda value,**kw:(context,page)
        assert lifecycle._do_connect(headless=True) is True
    finally:
        shopee_module._is_cdp_ready,shopee_module._connect_cdp,shopee_module._cdp_context_and_page=originals
    assert lifecycle._browser is browser and lifecycle._context is context and lifecycle._page is page
    assert lifecycle._session_id=="session-1" and lifecycle._connected is True and lifecycle._initializing is False
    assert connected==[("connect",lifecycle._playwright,{"headless":True}),
                       ("save",{"shop_name":None,"session_id":"session-1"})]
    failed=ShopeeLiveControl();failed._playwright=object()
    originals=(shopee_module._is_cdp_ready,shopee_module._connect_cdp)
    try:
        shopee_module._is_cdp_ready=lambda *_args,**_kwargs:True
        shopee_module._connect_cdp=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError("cdp failed"))
        assert failed._do_connect() is False
    finally:shopee_module._is_cdp_ready,shopee_module._connect_cdp=originals
    assert failed._connected is False and failed._initializing is False and failed._browser is None
    control=ShopeeLiveControl()
    control._connected=True;control._page=object()
    assert control._handle_action("set_active_goods",{"goods_id":"321","interval_sec":1}) is True
    assert control._active_goods_id==321 and control._popup_interval_sec==5.0 and control._popup_pending is True
    calls=[];control._do_popup=lambda goods_id:calls.append(goods_id)
    assert control._pump_active_popup() is None and calls==[321] and control._popup_pending is False
    control._last_popup_at=time.monotonic();assert control._pump_active_popup() is None and calls==[321]
    def closed(_goods_id):raise RuntimeError("Target page, context or browser has been closed")
    control._do_popup=closed;control._popup_pending=True
    closed_browser=[];control._safe_close_browser=lambda:closed_browser.append(True)
    control._pump_active_popup()
    assert control._active_goods_id is None and control._popup_pending is False and closed_browser==[True]
    control._active_goods_id=9;control._popup_pending=True;control._connected=True
    assert control._handle_action("clear_active_goods",{}) is True
    assert control._active_goods_id is None and control._popup_pending is False and control._connected is True
    control._active_goods_id=10;control._popup_pending=True
    assert control._handle_action("disconnect",{}) is True
    assert control._active_goods_id is None and control._popup_pending is False and control._connected is False
    assert closed_browser==[True,True]

def verify_shopee_page_states():
    import recovered.shopee_live_control as module
    class Locator:
        def __init__(self,count=0,visible=True):self._count=count;self._visible=visible;self.first=self
        def count(self):return self._count
        def is_visible(self):return self._visible
    class Context:
        def __init__(self,cookies=None):self._cookies=cookies or []
        def cookies(self):return self._cookies
    class Page:
        def __init__(self,url,selectors=None,results=None,cookies=None):
            self.url=url;self.selectors=selectors or {};self.results=results or {};self.context=Context(cookies)
        def locator(self,selector):return Locator(self.selectors.get(selector,0))
        def evaluate(self,script):return self.results.get(script,False)
    login=Page("https://accounts.shopee.com.my/seller/login")
    assert module._page_is_login_surface(login) and not module._page_looks_logged_in(login)
    seller_selector=".account-info .subaccount-name, .account-info .account-avatar"
    seller=Page("https://seller.shopee.com.my",{seller_selector:1})
    assert module._page_has_seller_centre(seller) and module._page_looks_logged_in(seller)
    live=Page("https://live.shopee.com.my/pc/live?session=abc",results={module._LIVE_WORKSPACE_JS:True,module._LIVING_JS:True})
    assert module._page_is_live_control(live) and module._page_looks_living(live)
    challenge=Page("https://live.shopee.com.my/pc/live?session=abc",results={module._LOGIN_CHALLENGE_JS:True,module._LIVE_WORKSPACE_JS:True})
    assert module._page_is_login_surface(challenge) and not module._page_is_live_control(challenge)
    cookie=Page("https://seller.shopee.com.my",cookies=[{"name":"SPC_EC","value":"x"}])
    assert module._page_looks_logged_in(cookie)
    class RestorePage(Page):
        def __init__(self,url,**kwargs):super().__init__(url,**kwargs);self.visits=[]
        def goto(self,url,**kwargs):self.url=url;self.visits.append((url,kwargs))
    login_restore=RestorePage("https://accounts.shopee.com.my/seller/login")
    assert module._restore_connected_page(login_restore)==("","") and login_restore.visits==[]
    seller_restore=RestorePage("https://seller.shopee.com.my",selectors={seller_selector:1},
        results={module._SCRAPE_SHOP_NAME_JS:"恢复店铺"})
    old_sid=module._read_session_id_from_storage;old_wait_live=module._wait_until_live_control
    try:
        module._read_session_id_from_storage=lambda:""
        assert module._restore_connected_page(seller_restore)==("恢复店铺","")
        assert seller_restore.visits[-1][0]==module.LIVE_CONTROL_URL
        stored_restore=RestorePage("https://seller.shopee.com.my",selectors={seller_selector:1},
            results={module._SCRAPE_SHOP_NAME_JS:"恢复店铺"})
        module._read_session_id_from_storage=lambda:"stored-session"
        waited=[];module._wait_until_live_control=lambda page,timeout_sec:waited.append((page.url,timeout_sec)) or True
        assert module._restore_connected_page(stored_restore)==("恢复店铺","stored-session")
        assert stored_restore.visits[-1][0]==module._live_url("stored-session")
        assert waited and waited[-1][0]==module._live_url("stored-session")
    finally:
        module._read_session_id_from_storage=old_sid;module._wait_until_live_control=old_wait_live
    class StorageContext:
        def __init__(self,cookies=None):self.values=list(cookies or []);self.added=[]
        def cookies(self):return self.values
        def add_cookies(self,items):self.added.extend(items);self.values.extend(items)
        def storage_state(self):return {"cookies":self.values,"origins":[]}
    with tempfile.TemporaryDirectory() as directory:
        storage=Path(directory)/"shopee_storage.json";old_path=module.get_storage_path
        module.get_storage_path=lambda:storage
        try:
            legacy={"storage_state":{"cookies":[{"name":"SPC_EC","value":"token"}],"origins":[]}}
            storage.write_text(json.dumps(legacy),encoding="utf-8")
            context=StorageContext();module._maybe_hydrate_cookies_from_storage(context)
            assert context.added==legacy["storage_state"]["cookies"]
            module._merge_storage_meta(context,shop_name="店铺",page_url="https://seller.shopee.com.my",session_id="sid")
            saved=json.loads(storage.read_text(encoding="utf-8"))
            assert saved["shop_name"]=="店铺" and saved["session_id"]=="sid" and saved["site"]=="my"
            named=Page("https://seller.shopee.com.my",results={module._SCRAPE_SHOP_NAME_JS:"店铺"})
            assert module._scrape_shop_name(named)=="店铺" and module._resolve_shop_name(named)=="店铺"
        finally:module.get_storage_path=old_path
    class Keyboard:
        def press(self,_key):return None
    class ProductPage:
        def __init__(self):self.keyboard=Keyboard();self.opened=False
        def evaluate(self,script,*args):
            if script==module._READ_PRODUCTS_STORAGE_JS:return [{"id":1,"name":"A","price":"2"}]
            if script==module._SCRAPE_PRODUCTS_JS:return [{"id":1,"name":"A DOM"},{"id":2,"name":"B"}]
            if script==module._PRODUCTS_PANEL_READY_JS:return self.opened
            if script==module._OPEN_PRODUCTS_PANEL_JS:self.opened=True;return {"ok":True,"via":"text"}
            return None
        def wait_for_timeout(self,_ms):return None
    products_page=ProductPage();products=module._collect_session_products(products_page,"sid")
    assert [item["itemId"] for item in products]==["1","2"] and [item["goodsIndex"] for item in products]==[1,2]
    assert not module._products_panel_ready(products_page)
    assert module._open_products_panel(products_page) and module._products_panel_ready(products_page)
    assert module._wait_until_products(products_page,sid="sid",timeout_sec=0)==products
    class Process:
        def __init__(self):self.returncode=None;self.terminated=False
        def poll(self):return self.returncode
        def terminate(self):self.terminated=True;self.returncode=0
        def wait(self,timeout=None):return self.returncode
        def kill(self):self.returncode=-9
    process=Process();old_ready=module._is_cdp_ready;old_wait=module._wait_cdp_ready;old_spawn=module._spawn_chrome_debug;old_proc=module._chrome_proc
    try:
        module._chrome_proc=None;module._is_cdp_ready=lambda port=9223:False
        module._wait_cdp_ready=lambda port=9223:True;module._spawn_chrome_debug=lambda port=9223:process
        assert module._ensure_chrome_running() is None and module._chrome_proc is process
        assert module._stop_chrome_debug() is None and module._chrome_proc is None and process.terminated
    finally:
        module._is_cdp_ready=old_ready;module._wait_cdp_ready=old_wait;module._spawn_chrome_debug=old_spawn;module._chrome_proc=old_proc

def verify_controller_workers():
    from recovered.taobao_live_control import TaobaoLiveControl
    from recovered.shopee_live_control import ShopeeLiveControl
    for controller_class in (TaobaoLiveControl,ShopeeLiveControl):
        controller=controller_class(); calls=[]
        def handle(self,action,payload):
            calls.append((action,threading.get_ident()))
            if action=="verify_error": raise ValueError("worker-error")
            return payload.get("value")
        controller._handle_action=types.MethodType(handle,controller)
        assert controller._call("verify",value=42)==42
        assert calls[-1][1]==controller._thread.ident!=threading.get_ident()
        try: controller._call("verify_error")
        except ValueError as error: assert str(error)=="worker-error"
        else: raise AssertionError("controller worker swallowed exception")
        controller.shutdown(); assert controller._thread is None

def verify_v2_fade_curves():
    import numpy as np
    from recovered.image_infer_v2_manager import VideoStreamManager
    manager=VideoStreamManager.__new__(VideoStreamManager)
    manager._fade_in_total=manager._fade_out_total=0
    manager.idle_fade_in_frames=manager.idle_fade_out_frames=4
    assert np.allclose(manager._fade_in_gain_curve(0,5),[0,.0625,.125,.1875,.25])
    assert np.allclose(manager._fade_out_gain_curve(0,5),[1,.9375,.875,.8125,.75])

def verify_v2_queue_selection():
    from queue import Queue
    from recovered.image_infer_audio import AudioBatch
    from recovered.image_infer_v2_manager import VideoStreamManager
    import numpy as np
    def batch(path, name):
        samples=np.zeros(1,np.float32)
        return AudioBatch(samples,samples,path,0,name)
    manager=VideoStreamManager.__new__(VideoStreamManager)
    manager.queue_priority=["danmu","normal"]
    manager.audio_queues={"normal":Queue(),"danmu":Queue()}
    manager.audio_queues["normal"].put(batch("<stable_silence>","normal"))
    manager.audio_queues["danmu"].put(batch("reply.wav","danmu"))
    assert manager._peek_preferred_queue("<stable_silence>",False)=="normal"
    assert manager._peek_preferred_queue("<stable_silence>",True)=="danmu"
    assert manager._peek_preferred_queue("speech.wav",False)=="danmu"

def verify_keyword_contract_behaviors():
    from recovered.main import Api
    api=Api.__new__(Api);api.config={};seen={}
    def pick(self,project_id,kind,extensions):
        seen.update(project_id=project_id,kind=kind);return {"status":"success"}
    api._pick_cloud_dh_file=types.MethodType(pick,api)
    assert api.pick_cloud_dh_audio({"project_id":"cloud-1"})["status"]=="success"
    assert seen=={"project_id":"cloud-1","kind":"audio"}

    import recovered.main as main_module
    manager_originals=(main_module.LiveManager,main_module.RecordLiveManager,
                       main_module.FaceHandLiveManager,main_module.CloneManager,
                       main_module._start_srs)
    manager_calls=[]
    class InitManager:
        def __init__(self,*args,**kwargs):manager_calls.append((type(self).__name__,args,kwargs))
    class InitClone(InitManager):pass
    try:
        main_module.LiveManager=InitManager
        main_module.RecordLiveManager=InitManager
        main_module.FaceHandLiveManager=InitManager
        main_module.CloneManager=InitClone
        main_module._start_srs=lambda runtime_dir:"srs-process"
        with tempfile.TemporaryDirectory() as directory:
            initialized=Api.__new__(Api)
            initialized._initialize(Path(directory),{"token":"value"})
        assert initialized._clone_manager.__class__ is InitClone
        assert initialized._live_action_assistant_process is None
        assert initialized.srs_process=="srs-process"
        assert initialized._live_lifecycle_lock.acquire(blocking=False)
        assert initialized._live_lifecycle_lock.acquire(blocking=False)
        initialized._live_lifecycle_lock.release();initialized._live_lifecycle_lock.release()
    finally:
        (main_module.LiveManager,main_module.RecordLiveManager,
         main_module.FaceHandLiveManager,main_module.CloneManager,
         main_module._start_srs)=manager_originals
    assert [call[0] for call in manager_calls]==["InitManager","InitManager","InitManager","InitClone"]

    dispatch_api=Api.__new__(Api);dispatch_calls=[]
    dispatch_api._start_local_media_live=lambda config:dispatch_calls.append(("local",config)) or {"status":"local"}
    dispatch_api._start_face_hand_live=lambda data,config:dispatch_calls.append(("face",data,config)) or {"status":"face"}
    dispatch_api._start_digital_live=lambda config:dispatch_calls.append(("digital",config)) or {"status":"digital"}
    assert dispatch_api._start_live_locked({"config":{"live_type":"local_media"}})["status"]=="local"
    assert dispatch_api._start_live_locked({"config":{"live_type":"face_hand_live"}})["status"]=="face"
    assert dispatch_api._start_live_locked({"config":{"live_type":"future_mode"}})["status"]=="digital"
    assert [call[0] for call in dispatch_calls]==["local","face","digital"]

    validation_api=Api.__new__(Api)
    validation_api._running_live_error=lambda:None
    minimax_error=validation_api._start_digital_live({
        "voice_infer_version":"minimax",
        "minimax_voice_config":{"api_key":"key","api_host":"https://api.minimax.io"},
    })
    assert minimax_error=={
        "status":"error","message":"Minimax 声音配置不完整，请先在配置页填写后再开播"
    }
    cosyvoice_error=validation_api._start_digital_live({
        "voice_infer_version":"cosyvoice","cosyvoice_voice_config":{"api_key":"   "},
    })
    assert cosyvoice_error=={
        "status":"error","message":"阿里云语音合成配置不完整，请先在配置页填写 API Key 后再开播"
    }
    cache_calls=[]
    class CacheManager:
        def prepare_multilingual_audio_cache(self,**kwargs):cache_calls.append(kwargs);return False
    validation_api._digital_live_manager=CacheManager()
    cache_error=validation_api._start_digital_live({
        "voice_infer_version":"v2","script_input_mode":"text",
        "scripts":"你好{朋友|家人}","voice_id":"voice-main",
        "assistant_voice_id":"voice-assistant","shift_schedule":[{"at":"10:00"}],
        "multi_product_configs":[{"product_index":1}],"language":"vi-VN","voice_speed":1.25,
    })
    assert cache_error=={"status":"error","message":"多语种话术音频缓存准备失败"}
    assert cache_calls==[{
        "scripts":"你好{朋友|家人}","voice_id":"voice-main",
        "assistant_voice_id":"voice-assistant","shift_schedule":[{"at":"10:00"}],
        "multi_product_configs":[{"product_index":1}],"language":"vi-VN",
        "voice_speed":1.25,"voice_infer_version":"v2",
    }]
    class SuccessfulDigitalManager:
        current_session_id="session-7";is_capturing=True;last_error=None
        def start_live(self,**kwargs):self.kwargs=kwargs;return True
    validation_api._digital_live_manager=SuccessfulDigitalManager()
    original_build_local_params=main_module.build_local_params
    main_module.build_local_params=lambda config:{"built":config["voice_id"]}
    try:
        digital_success=validation_api._start_digital_live({
            "voice_id":"voice-7","voice_infer_version":"v1",
            "llm_config":{"model":"test"},
        })
    finally:main_module.build_local_params=original_build_local_params
    assert digital_success=={
        "status":"success","session_id":"session-7","danmu_capturing":True
    }
    assert validation_api._digital_live_manager.kwargs["local_params"]=={"built":"voice-7"}

    import recovered.voice_infer_malai_local as malai
    with tempfile.TemporaryDirectory() as directory:
        reference=Path(directory)/"reference.wav";reference.write_bytes(b"RIFF")
        synth=malai.VoiceSynthesizer(str(reference),api_config={"temp_dir":directory})
        captured={}
        class Response:
            headers={"Content-Type":"audio/wav"};content=b"wave"
            def raise_for_status(self):return None
        original=malai.requests.post
        def post(url,**kwargs):captured.update(kwargs);return Response()
        malai.requests.post=post
        try:synth._post_once("http://tts","hello",1.2,"ms-MY",str(reference),"rujukan")
        finally:malai.requests.post=original
        assert captured["data"]["language"]=="ms-MY"
        assert captured["data"]["reference_text"]=="rujukan"
        assert captured["files"]["ref_audio"][0]=="reference.wav"

def verify_voice_clone_lifecycle():
    import recovered.voice_clone_infer_api as clone_api
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);source=root/"sample.mp3";source.write_bytes(b"mp3")
        recognized=root/"recognized.wav";recognized.write_bytes(b"RIFF-recognized")
        calls=[]
        original_run=clone_api.subprocess.run
        original_resolve=clone_api._resolve_ffmpeg_executable
        original_process=clone_api.process_audio_batch
        def fake_run(command,**kwargs):
            calls.append((command,kwargs));Path(command[-1]).write_bytes(b"RIFF-normalized")
            return types.SimpleNamespace(returncode=0,stderr=b"")
        clone_api.subprocess.run=fake_run
        clone_api._resolve_ffmpeg_executable=lambda:"ffmpeg"
        clone_api.process_audio_batch=lambda weight,paths,lang:[
            (str(recognized)," short "),(str(paths[0])," the longest text ")
        ]
        try:
            result=Path(clone_api.clone_voice_local(
                str(source),"voice-a",str(root/"voices"),"asr.bin","zh"
            ))
        finally:
            clone_api.subprocess.run=original_run
            clone_api._resolve_ffmpeg_executable=original_resolve
            clone_api.process_audio_batch=original_process
        manifest=json.loads((result/"slice_manifest.json").read_text(encoding="utf-8"))
        assert manifest==[
            {"audio_path":str(recognized),"text":"short"},
            {"audio_path":str(result/"normalized_input.wav"),"text":"the longest text"},
        ]
        assert (result/"ref_text.txt").read_text(encoding="utf-8")=="the longest text"
        assert (result/"ref_audio.wav").read_bytes()==b"RIFF-normalized"
        assert calls and calls[0][0][0]=="ffmpeg"
        invalid=root/"sample.flac";invalid.write_bytes(b"flac")
        try:clone_api.clone_voice_local(str(invalid),"voice-b",str(root),"asr.bin")
        except ValueError as error:assert "wav/mp3" in str(error)
        else:raise AssertionError("voice clone accepted a non-native audio extension")

def verify_whisper_runtime_contract():
    import recovered.whisper_runtime as whisper_runtime
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        preferred=whisper_runtime.resolve_whisper_model_path(str(root))
        assert preferred==root/"whisper"/"large-v3.pt" and preferred.parent.is_dir()
        legacy=root/"large-v3.pt";legacy.write_bytes(b"model")
        assert whisper_runtime.resolve_whisper_model_path(str(root))==legacy
        preferred.write_bytes(b"preferred")
        assert whisper_runtime.resolve_whisper_model_path(str(root))==preferred
        calls=[]
        original_whisper=sys.modules.get("whisper");original_torch=sys.modules.get("torch")
        sys.modules["whisper"]=types.SimpleNamespace(
            load_model=lambda *args,**kwargs:calls.append((args,kwargs)) or "model")
        sys.modules["torch"]=types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda:False))
        try:
            assert whisper_runtime.load_whisper_model(str(root))=="model"
            assert calls.pop()==((str(preferred),),{"device":"cpu"})
            preferred.unlink();legacy.unlink()
            assert whisper_runtime.load_whisper_model(str(root))=="model"
            assert calls.pop()==(("large-v3",),{
                "device":"cpu","download_root":str(root/"whisper")})
        finally:
            if original_whisper is None:sys.modules.pop("whisper",None)
            else:sys.modules["whisper"]=original_whisper
            if original_torch is None:sys.modules.pop("torch",None)
            else:sys.modules["torch"]=original_torch
        audio=root/"audio.wav";audio.write_bytes(b"RIFF")
        captured={}
        class Model:
            def transcribe(self,path,**kwargs):captured.update(path=path,**kwargs);return {"text":"ok"}
        original_torch=sys.modules.get("torch")
        sys.modules["torch"]=types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda:True)
        )
        try:result=whisper_runtime.transcribe_with_whisper(Model(),str(audio),word_timestamps=False)
        finally:
            if original_torch is None:sys.modules.pop("torch",None)
            else:sys.modules["torch"]=original_torch
        assert result=={"text":"ok"}
        assert captured=={
            "path":str(audio),"task":"transcribe","fp16":True,"verbose":False,
            "word_timestamps":False,"initial_prompt":whisper_runtime.WHISPER_PUNCTUATION_PROMPT,
        }
        captured.clear()
        missing=root/"missing.wav"
        whisper_runtime.transcribe_with_whisper(Model(),str(missing))
        assert captured["path"]==str(missing) and captured["word_timestamps"] is True
        assert whisper_runtime.WHISPER_PUNCTUATION_PROMPT.startswith("请准确识别语音内容，")
        assert whisper_runtime.clean_whisper_text(" 你  好  world  ！ ")=="你好 world！"
        assert whisper_runtime._segments_to_punctuated_text({"segments":[
            {"text":"你好"},{"text":"世界"},{"text":"hello"},{"text":"world!"}
        ]})=="你好。 世界。 hello. world!"
        assert whisper_runtime.whisper_result_to_text({
            "text":"顶层已完整！","segments":[{"text":"不应覆盖"}]})=="顶层已完整！"
        assert whisper_runtime.whisper_result_to_text({
            "text":"hello world","segments":[{"text":"hello"},{"text":"world"}]})=="hello. world."
        assert whisper_runtime.whisper_result_to_text({"text":"没有分段"})=="没有分段。"
        info=whisper_runtime.whisper_result_to_sentence_info({"segments":[
            {"start":-0.1,"end":0.6,"words":[
                {"word":" 你 ","start":-0.1,"end":0.2},
                {"word":"好！","start":0.2,"end":0.5999}]},
            {"start":1.0,"end":1.5,"text":"next"},
            {"start":10.0,"end":10.25,"text":"gap"},
        ]})
        assert info==[
            {"start":0,"end":599,"text":"你好！"},
            {"start":1000,"end":1500,"text":"next"},
            {"start":10000,"end":10250,"text":"gap"},
        ]
        long_text="a"*80
        assert whisper_runtime.whisper_result_to_sentence_info({"segments":[
            {"start":2,"end":3,"text":long_text}]})==[
                {"start":2000,"end":3000,"text":long_text}]

def verify_online_voice_runtime_contract():
    import recovered.online_voice_generate as online_voice
    assert online_voice._minimax_headers("",None)=={"Authorization":"Bearer "}
    assert online_voice._minimax_headers("key","application/json")=={
        "Authorization":"Bearer key","Content-Type":"application/json"
    }
    mainland=online_voice.resolve_aliyun_voice_runtime({})
    assert mainland=={
        "base_http_api_url":"https://dashscope.aliyuncs.com/api/v1",
        "base_websocket_api_url":"wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        "http_url":"https://dashscope.aliyuncs.com/api/v1",
        "websocket_url":"wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    }
    international=online_voice.resolve_aliyun_voice_runtime({"region":"intl"})
    assert international=={
        "region":"intl",
        "base_http_api_url":"https://dashscope-intl.aliyuncs.com/api/v1",
        "base_websocket_api_url":"wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        "http_url":"https://dashscope-intl.aliyuncs.com/api/v1",
        "websocket_url":"wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
    }
    original=sys.modules.get("dashscope")
    fake=types.SimpleNamespace();sys.modules["dashscope"]=fake
    try:applied=online_voice.apply_dashscope_endpoint({"region":"international"})
    finally:
        if original is None:sys.modules.pop("dashscope",None)
        else:sys.modules["dashscope"]=original
    assert applied["region"]=="international"
    assert applied["http_url"]==international["http_url"]
    assert applied["websocket_url"]==international["websocket_url"]
    assert fake.base_http_api_url==applied["http_url"]
    assert fake.base_websocket_api_url==applied["websocket_url"]
    assert online_voice.cosyvoice_language_hint("EN_us")=="en-us"
    assert online_voice.cosyvoice_language_hint("bahasa-melayu")=="bahasa-melayu"
    assert online_voice.cosyvoice_language_hint("unknown")=="zh-cn"
    assert online_voice.aliyun_voice_supports_language("de-DE",{"region":"intl"})
    assert not online_voice.aliyun_voice_supports_language("de-DE",{"region":"china"})
    assert online_voice.aliyun_voice_supports_language("ms",{"region":"china"})
    for region in ("china", "intl"):
        for language in ("ms-MY", "vi-VN"):
            assert online_voice.cosyvoice_language_hint(language) == language.lower()
            assert online_voice.aliyun_voice_supports_language(language, {"region": region})
    assert online_voice.aliyun_voice_supports_language("tl-PH",{"region":"china"})

def verify_core_method_coverage():
    cases = [
        ("Player", ORIGINAL/"bin/video_player/infer_api.cp310-win_amd64.pyd", [HERE/"video_player.py"], {"_get_active_worker","_finish_insert","_stream_prebuffer_packets"}),
        ("KuaishouLiveClient", ORIGINAL/"tools/danmu_capture/kuaishou_v2/KsLive.cp310-win_amd64.pyd", [HERE/"kuaishou_v2/KsLive.py"], set()),
        ("CloneManager", ORIGINAL/"live/clone_manager.cp310-win_amd64.pyd", [HERE/"clone_manager.py"], set()),
        ("FaceHandLiveManager", ORIGINAL/"live/face_hand_live_manager.cp310-win_amd64.pyd", [HERE/"face_hand_live_manager.py"], {"_run_local_synth_with_timeout"}),
        ("TaobaoLiveControl", ORIGINAL/"tools/taobao_live_control.cp310-win_amd64.pyd", [HERE/"taobao_live_control.py"], set()),
        ("ShopeeLiveControl", ORIGINAL/"tools/shopee_live_control.cp310-win_amd64.pyd", [HERE/"shopee_live_control.py"], set()),
        ("VideoFaceReader", ORIGINAL/"bin/image_infer_origin_frame/tools/video_face_reader/video_face_reader.cp310-win_amd64.pyd", [HERE/"origin_video_face_reader.py"], set()),
        ("VideoFaceReader", ORIGINAL/"bin/image_infer_v2/tools/video_face_reader/video_face_reader.cp310-win_amd64.pyd", [HERE/"image_v2_video_face_reader.py", HERE/"origin_video_face_reader.py"], set()),
        ("RealtimeFaceReader", ORIGINAL/"bin/image_infer_v2/tools/realtime_face_reader/realtime_face_reader.cp310-win_amd64.pyd", [HERE/"image_realtime_face_reader.py", HERE/"origin_video_face_reader.py"], set()),
        ("RtmpFaceReader", ORIGINAL/"bin/image_infer_v2/tools/rtmp_face_reader/rtmp_face_reader.cp310-win_amd64.pyd", [HERE/"image_rtmp_face_reader.py", HERE/"origin_video_face_reader.py"], set()),
    ]
    for class_name,binary,sources,aliases in cases:
        methods=set()
        for source in sources:
            tree=ast.parse(source.read_text(encoding="utf-8"))
            methods.update(item.name for node in tree.body if isinstance(node,ast.ClassDef) for item in node.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)))
        strings=binary_strings(binary)
        expected=set(re.findall(rf"^{class_name}\.([A-Za-z_]\w*)$",strings,re.MULTILINE))
        missing=expected-methods-aliases
        assert not missing, f"{class_name} missing binary methods: {sorted(missing)}"

def verify_all_binary_class_methods():
    gaps={}
    for binary in first_party_extensions():
        relative=binary.relative_to(ORIGINAL)
        stem=relative.name.split(".cp310-win_amd64",1)[0]
        if stem.endswith(".pyd"): stem=stem[:-4]
        module_name=".".join(("recovered",*relative.parent.parts,stem))
        module=importlib.import_module(module_name)
        strings=binary_strings(binary)
        missing=[]
        for class_name,method_name in set(re.findall(r"^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$",strings,re.MULTILINE)):
            cls=getattr(module,class_name,None)
            if inspect.isclass(cls) and not hasattr(cls,method_name):
                missing.append(f"{class_name}.{method_name}")
        if missing:gaps[str(relative)]=sorted(missing)
    assert not gaps, f"binary class method inventory gaps: {gaps}"

def _binary_signature_parts(line):
    opening=line.find("(")
    if opening<0:return None
    depth=0
    for index in range(opening,len(line)):
        if line[index]=="(":depth+=1
        elif line[index]==")":
            depth-=1
            if depth==0:return line[:opening],line[opening+1:index]
    return None

def _split_signature_arguments(value):
    output=[];depth=0;start=0
    for index,character in enumerate(value+","):
        if character in "([{":depth+=1
        elif character in ")]}":depth-=1
        elif character=="," and depth==0:
            item=value[start:index].strip();start=index+1
            if item and item!="*":output.append(item)
    return output

def _binary_argument_contract(value):
    left,separator,default=value.partition("=")
    name=left.split(":",1)[0].split()[-1].lstrip("*")
    return name,not bool(separator)

def verify_binary_class_signature_arity():
    gaps={}
    for binary in first_party_extensions():
        relative=binary.relative_to(ORIGINAL)
        stem=relative.name.split(".cp310-win_amd64",1)[0]
        if stem.endswith(".pyd"):stem=stem[:-4]
        module=importlib.import_module(".".join(("recovered",*relative.parent.parts,stem)))
        strings=binary_strings(binary)
        missing=[]
        for line in strings.splitlines():
            parts=_binary_signature_parts(line)
            if parts is None or not re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*",parts[0]):continue
            class_name,method_name=parts[0].split(".",1);cls=getattr(module,class_name,None)
            if not inspect.isclass(cls) or not hasattr(cls,method_name):continue
            raw=inspect.getattr_static(cls,method_name)
            function=raw.__func__ if isinstance(raw,(staticmethod,classmethod)) else raw
            try:parameters=list(inspect.signature(function).parameters.values())
            except (TypeError,ValueError):continue
            original=_split_signature_arguments(parts[1])
            fixed=[item for item in parameters if item.kind not in (item.VAR_POSITIONAL,item.VAR_KEYWORD)]
            original_kwargs=any(item.startswith("**") for item in original)
            recovered_kwargs=any(item.kind==item.VAR_KEYWORD for item in parameters)
            expected=len(fixed)+(1 if recovered_kwargs else 0)
            if len(original)!=expected or original_kwargs!=recovered_kwargs:
                missing.append(f"{parts[0]}: binary={len(original)}, recovered={inspect.signature(function)}")
                continue
            recovered=[item for item in parameters if item.kind!=item.VAR_POSITIONAL]
            for binary_item,recovered_item in zip(original,recovered):
                binary_name,binary_required=_binary_argument_contract(binary_item)
                recovered_required=recovered_item.default is recovered_item.empty
                if binary_name!=recovered_item.name or binary_required!=recovered_required:
                    missing.append(
                        f"{parts[0]}: binary={parts[1]}, recovered={inspect.signature(function)}"
                    )
                    break
        if missing:gaps[str(relative)]=missing
    assert not gaps,f"binary class signature arity gaps: {gaps}"

def verify_binary_module_signature_arity():
    gaps={}
    for binary in first_party_extensions():
        relative=binary.relative_to(ORIGINAL)
        stem=relative.name.split(".cp310-win_amd64",1)[0]
        if stem.endswith(".pyd"):stem=stem[:-4]
        module=importlib.import_module(".".join(("recovered",*relative.parent.parts,stem)))
        strings=binary_strings(binary)
        missing=[];seen=set()
        for line in strings.splitlines():
            parts=_binary_signature_parts(line.strip())
            if parts is None or not re.fullmatch(r"[A-Za-z_]\w*",parts[0]) or parts[0] in seen:continue
            function=getattr(module,parts[0],None)
            if not callable(function) or inspect.isclass(function):continue
            seen.add(parts[0])
            try:parameters=list(inspect.signature(function).parameters.values())
            except (TypeError,ValueError):continue
            original=_split_signature_arguments(parts[1])
            if any(item.kind==item.VAR_POSITIONAL for item in parameters):continue
            recovered=[item for item in parameters if item.kind!=item.VAR_POSITIONAL]
            if len(original)!=len(recovered):
                missing.append(f"{parts[0]}: binary={parts[1]}, recovered={inspect.signature(function)}");continue
            for binary_item,recovered_item in zip(original,recovered):
                binary_name,binary_required=_binary_argument_contract(binary_item)
                if binary_name!=recovered_item.name or binary_required!=(recovered_item.default is recovered_item.empty):
                    missing.append(f"{parts[0]}: binary={parts[1]}, recovered={inspect.signature(function)}");break
        if missing:gaps[str(relative)]=missing
    assert not gaps,f"binary module signature arity gaps: {gaps}"

def verify_public_name_inventory():
    def exports(source,seen=None):
        seen=set() if seen is None else seen
        if source in seen or not source.is_file(): return set()
        seen.add(source)
        try: tree=ast.parse(source.read_text(encoding="utf-8"))
        except (SyntaxError,UnicodeError): return set()
        names={node.name for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not node.name.startswith("_")}
        for node in ast.walk(tree):
            if not isinstance(node,ast.ImportFrom): continue
            targets=[]
            if node.module=="recovered": targets.extend(HERE/f"{alias.name}.py" for alias in node.names)
            elif node.level:
                base=source.parent
                for _ in range(node.level-1): base=base.parent
                if node.module: base=base.joinpath(*node.module.split("."))
                targets.extend((base.with_suffix(".py"),base/"__init__.py"))
            elif node.module and (HERE/f"{node.module}.py").is_file(): targets.append(HERE/f"{node.module}.py")
            elif node.module and node.module.startswith("recovered."):
                base=HERE.joinpath(*node.module.split(".")[1:]); targets.extend((base.with_suffix(".py"),base/"__init__.py"))
            if any(alias.name=="*" for alias in node.names) or node.module=="recovered":
                for target in targets: names.update(exports(target,seen))
            else: names.update(alias.asname or alias.name for alias in node.names if not (alias.asname or alias.name).startswith("_"))
        return names
    noise={"send","throw","close","connect","NAN","nan","truncated","PROGRAMFILES","Intel","updateCaptureButton","main","forward","lambda","generator","genexpr","coroutines","cython_function_or_method","abc","dll","exe","path","group","infer_api","json","yaml","txt","wav","mp3","mp4","jpg","png","ndarray","Module","Response","Popen","CompletedProcess","Event","Tensor","Sequential","Image","ImageDraw","ImageFont","VideoCapture","PyAudio"}
    gaps={}
    for binary in first_party_extensions():
        strings=binary_strings(binary)
        names={match.group(1) for line in strings.splitlines() if (match:=re.match(r"^([A-Za-z][A-Za-z0-9_]*)\([^)]*\)(?:\s*->.*)?$",line.strip()))}
        missing=sorted(names-exports(recovered_path(binary))-noise)
        if missing: gaps[str(binary.relative_to(ORIGINAL))]=missing
    assert not gaps, f"public callable inventory gaps: {gaps}"


def verify_binary_qualified_module_names():
    """Require every business-level qualified function embedded in a pyd."""
    gaps={}
    for binary in first_party_extensions():
        relative=binary.relative_to(ORIGINAL)
        stem=relative.name.split(".cp310-win_amd64",1)[0]
        if stem.endswith(".pyd"):stem=stem[:-4]
        qualified=".".join((*relative.parent.parts,stem))
        module=importlib.import_module("recovered."+qualified)
        strings=binary_strings(binary)
        names=set()
        prefix=qualified+"."
        for line in strings.splitlines():
            if not line.startswith(prefix):continue
            name=line[len(prefix):].strip()
            if re.fullmatch(r"(?:_[A-Za-z]\w*|main)",name) and not name.startswith("__") and name!="py":
                names.add(name)
        missing=sorted(name for name in names if not hasattr(module,name))
        if missing:gaps[str(relative)]=missing
    assert not gaps,f"binary qualified module-name gaps: {gaps}"


def verify_capture_window_change_contract():
    from recovered import auto_live_action_capture as capture
    import queue

    window=capture.CaptureWindow()
    class Root:
        def update_idletasks(self):pass
        def winfo_x(self):return 10
        def winfo_y(self):return 20
        def winfo_width(self):return 2
        def winfo_height(self):return 2
    window.root=Root()
    original_grab=capture.ImageGrab.grab
    frames=[capture.np.zeros((2,2,3),dtype=capture.np.uint8),capture.np.zeros((2,2,3),dtype=capture.np.uint8),capture.np.ones((2,2,3),dtype=capture.np.uint8)]
    boxes=[]
    def grab(*,bbox):
        boxes.append(bbox)
        return frames.pop(0)
    capture.ImageGrab.grab=grab
    try:
        first=window.capture_screen(.9)
        same=window.capture_screen(.9)
        changed=window.capture_screen(.9)
    finally:
        capture.ImageGrab.grab=original_grab
    assert boxes==[(10,20,12,22)]*3
    assert first["changed"] is True and first["image"].shape==(2,2,3)
    assert not bool(same["changed"]) and same["image"].shape==(2,2,3)
    assert bool(changed["changed"]) and capture.np.all(changed["image"]==1)
    window.running=False
    assert window.capture_screen()=={"image":None,"changed":False}

    class GeometryRoot(Root):
        def __init__(self):self.calls=[];self.scheduled=[]
        def geometry(self,value):self.calls.append(value)
        def after(self,delay,callback):self.scheduled.append((delay,callback))
    root=GeometryRoot(); commands=queue.Queue(); results=queue.Queue()
    queued=capture.CaptureWindow(commands,results);queued.root=root
    queued.x,queued.y,queued.width,queued.height=10,20,12,22
    queued.capture_screen=lambda threshold=None:{"image":"frame","changed":True}
    commands.put("capture");queued._check_queue()
    assert results.get_nowait()=={"image":"frame","pos":(10,20,12,22)}
    assert root.scheduled and root.scheduled[-1][0]==100

    event=types.SimpleNamespace(x_root=110,y_root=220)
    queued.start_move(types.SimpleNamespace(x_root=100,y_root=200))
    queued.do_move(event)
    assert root.calls[-1]=="+20+40"
    queued.start_resize(types.SimpleNamespace(x_root=100,y_root=200),"top_left_corner")
    queued.do_resize(types.SimpleNamespace(x_root=900,y_root=900),"top_left_corner")
    assert root.calls[-1]=="20x20+810+720"


def verify_auto_live_ocr_result_contract():
    from recovered.auto_live_action_ocr import OCRProcessor

    processor=OCRProcessor.__new__(OCRProcessor)
    assert OCRProcessor.recognize_text(processor,None)==[]
    modern=types.SimpleNamespace(
        boxes=[[[1,2],[3,4]]],txts=["文本"],scores=[0.875],
    )
    processor.ocr=lambda image:modern
    assert processor.recognize_text("frame")==[
        {"box":[[1,2],[3,4]],"text":"文本","score":0.875}
    ]
    processor.ocr=lambda image:([[[[5,6],[7,8]],"legacy",0.5]],None)
    assert processor.recognize_text("frame")==[
        {"box":[[5,6],[7,8]],"text":"legacy","score":0.5}
    ]
    processor.ocr=lambda image:[[[[9,10],[11,12]],"no-score"]]
    assert processor.recognize_text("frame")==[
        {"box":[[9,10],[11,12]],"text":"no-score","score":None}
    ]


def verify_position_compat_contract():
    from recovered.image_position_compat import crop_lm_to_frame_landmarks, resolve_frame_landmarks
    import numpy as np

    crop=np.asarray([[0,0],[266,266]],dtype=np.float32)
    converted=crop_lm_to_frame_landmarks(crop,[10,110,20,220])
    assert converted.dtype==np.int32
    assert converted.tolist()==[[20,10],[220,110]]
    direct=resolve_frame_landmarks({"landmarks":[[1.9,2.1]]})
    assert direct.dtype==np.int32 and direct.tolist()==[[1,2]]
    assert resolve_frame_landmarks({"crop_lm":crop,"bounding_box":[10,110,20,220]}).tolist()==converted.tolist()
    assert resolve_frame_landmarks({"positions":crop,"bbox":[10,110,20,220]}) is None
    try:crop_lm_to_frame_landmarks(crop,[10,10,20,220])
    except ValueError as error:assert str(error)=="无效 bounding_box，无法转换 crop_lm"
    else:raise AssertionError("invalid bounding_box accepted")


def verify_image_clone_face_detector_contract():
    from recovered.image_clone_lip_detect import ScrfdFaceDetector
    import numpy as np

    class Detector:
        def __init__(self):self.calls=[];self.results=[]
        def get_bboxes(self,image,**kwargs):
            self.calls.append((image,kwargs));return self.results.pop(0)
    backend=Detector();detector=ScrfdFaceDetector.__new__(ScrfdFaceDetector)
    detector.conf_threshold=.6;detector.last_detection=None;detector.detector=backend
    backend.results=[
        (np.asarray([[10,20,40,70,.9]],dtype=np.float64),["landmarks"]),
        (np.empty((0,5),dtype=np.float32),[]),
    ]
    result=detector.detect(["first","second"])
    assert backend.calls==[("first",{"thresh":.6}),("second",{"thresh":.6})]
    assert result[0][0].dtype==np.float32 and result[0][0].tolist()==[[10.,20.,30.,50.]]
    assert result[0][1]==[0] and result[1] is result[0]
    detector.last_detection=None;backend.results=[(None,[])]
    empty=detector.detect(["empty"])[0]
    assert empty[0].shape==(0,) and empty[1]==[]
    detector.release();assert detector.detector is None


def verify_hubert_extractor_contract():
    from recovered.hubert_extractor import HubertExtractor

    calls=[]
    class Tensor:
        def __init__(self, rows):self.rows=list(rows)
        @property
        def shape(self):return (len(self.rows), 2)
        def __getitem__(self,key):
            if key==0:return self
            return Tensor(self.rows[key])
        def to(self,device):calls.append(("input.to",device));return self
        def detach(self):calls.append("detach");return self
        def cpu(self):calls.append("cpu");return self
        def numpy(self):calls.append("numpy");return self.rows
    class Processor:
        def __call__(self,speech,**kwargs):
            calls.append(("processor",speech,kwargs))
            return types.SimpleNamespace(input_values=Tensor([1]))
    class ProcessorType:
        @classmethod
        def from_pretrained(cls,path,**kwargs):
            calls.append(("processor.load",path,kwargs));return Processor()
    class Model:
        def to(self,device):calls.append(("model.to",device));return self
        def __call__(self,values):
            calls.append(("model",values));return types.SimpleNamespace(last_hidden_state=Tensor([1,2,3]))
    class ModelType:
        @classmethod
        def from_pretrained(cls,path,**kwargs):
            calls.append(("model.load",path,kwargs));return Model()

    previous=sys.modules.get("transformers")
    sys.modules["transformers"]=types.SimpleNamespace(
        HubertModel=ModelType,Wav2Vec2Processor=ProcessorType,
    )
    try:
        extractor=HubertExtractor("model-dir",device="cuda:7")
        assert extractor.extract("raw-speech")==[1,2]
    finally:
        if previous is None:sys.modules.pop("transformers",None)
        else:sys.modules["transformers"]=previous
    assert calls[:3]==[
        ("processor.load","model-dir",{"local_files_only":True}),
        ("model.load","model-dir",{"local_files_only":True}),
        ("model.to","cuda:7"),
    ]
    assert calls[3][0:2]==("processor","raw-speech")
    assert calls[3][2]=={"sampling_rate":16000,"return_tensors":"pt"}
    assert calls[4]==("input.to","cuda:7")
    assert calls[-3:]==["detach","cpu","numpy"]


def verify_image_clone_landmark_geometry():
    from recovered.image_clone_lip_detect import face_det
    import numpy as np

    class Detector:
        def detect(self,image):
            # xywh, one selected index, and eye keypoints.
            return (
                np.asarray([[10,20,40,20]],dtype=np.float32),
                np.asarray([[0]],dtype=np.int32),
                np.asarray([[[15,25],[35,25],[0,0],[0,0],[0,0]]],dtype=np.float32),
            )
    image=np.zeros((80,100,3),dtype=np.uint8)
    crops,boxes,centers,angles=face_det(image,Detector())
    # max(40,20)*1.05 = 42, centered at (30,30).
    assert boxes==[[9,9,51,51]]
    assert centers==[(21,21)] and angles==[0.0]
    assert crops[0].shape==(42,42,3)

    class EdgeDetector:
        def detect(self,image):
            return (
                np.asarray([[0,0,40,20]],dtype=np.float32),[0],
                np.asarray([[[2,2],[8,2],[0,0],[0,0],[0,0]]],dtype=np.float32),
            )
    crops,boxes,_,_=face_det(image,EdgeDetector())
    assert boxes==[[-1,-11,41,31]] and crops[0].shape==(42,42,3)


def verify_lip_detector_batch_crop_contract():
    from recovered.image_clone_lip_detect import LipDetector
    import numpy as np

    detector=LipDetector.__new__(LipDetector)
    class FaceDetector:
        def detect(self,images):
            assert len(images)==2
            return [
                (np.asarray([[10,20,40,20]],dtype=np.float32),[0]),
                (np.empty((0,4),dtype=np.float32),[]),
            ]
    detector.face_detector=FaceDetector()
    images=[np.zeros((80,100,3),dtype=np.uint8),np.zeros((20,20,3),dtype=np.uint8)]
    crops,offsets=detector._face_det(images)
    assert crops[0][0].shape==(42,42,3) and offsets==[[(9,9)],[]]
    assert crops[1]==[]


def verify_generate_face_landmark_contract():
    from recovered.image_face_detect import FaceDetect,convert98to68,pfpld
    import numpy as np

    raw=np.arange(196,dtype=np.float32)[None]
    converted=convert98to68(raw)
    assert converted.shape==(136,)
    assert converted[:6].tolist()==[0.,1.,4.,5.,8.,9.]
    # Eye interpolation: midpoint of source points 60 and 62.
    assert converted[74:76].tolist()==[122.,123.]

    calls=[]
    class Session:
        def run(self,names,inputs):
            calls.append((names,inputs));return [None,raw]
    model=pfpld.__new__(pfpld);model.ort_session=Session();model.input_name="input"
    image=np.full((20,40,3),255,dtype=np.uint8)
    result=model.forward(image)
    assert result.shape==(1,68,2)
    tensor=calls[0][1]["input"]
    assert tensor.shape==(1,3,112,112) and tensor.dtype==np.float32
    assert float(tensor.min())==1.0 and float(tensor.max())==1.0

    class Detector:
        def __init__(self):self.calls=[]
        def detect(self,image,**kwargs):
            self.calls.append((image,kwargs));return "boxes","keypoints"
    facade=FaceDetect.__new__(FaceDetect);facade.det_model=Detector()
    bgr=np.full((8,9,3),[10,30,90],dtype=np.uint8)
    assert facade.get_bboxes(bgr,.7,3)==("boxes","keypoints")
    forwarded,kwargs=facade.det_model.calls[0]
    # Corrected against V04 native input trace, not the former pass-through assumption.
    assert np.array_equal(forwarded,bgr[:,:,::-1])
    assert np.array_equal(bgr[0,0],[10,30,90])
    assert kwargs=={"thresh":.7,"max_num":3,"metric":"default"}


def verify_generate_scrfd_contract():
    from recovered import image_scrfd as module
    import numpy as np

    values=np.asarray([[1.,2.],[3.,4.]])
    expected=np.exp(values-np.max(values,axis=1)[:,None])
    expected=expected/expected.sum(axis=1)[:,None]
    assert np.allclose(module.softmax(values),expected)

    class Value:
        def __init__(self,name,shape=None):self.name=name;self.shape=shape or [1,1]
    class Session:
        def __init__(self,shape=(1,3,640,640),outputs=9):
            self.input=Value("input",list(shape));self.outputs=[Value(str(i)) for i in range(outputs)]
            self.providers=[]
        def get_inputs(self):return [self.input]
        def get_outputs(self):return self.outputs
        def set_providers(self,value):self.providers.append(value)
    fixed=module.SCRFD(session=Session())
    assert fixed.taskname=="detection" and fixed.batched is False
    assert fixed.input_size==(640,640) and fixed.fmc==3
    assert fixed._num_anchors==2 and fixed.use_kps is True
    assert fixed.prepare(-1,input_size=(320,320),nms_thresh=.25) is None
    assert fixed.input_size==(640,640) and fixed.nms_thresh==.25
    assert fixed.session.providers==[["CPUExecutionProvider"]]
    dynamic=module.SCRFD(session=Session(shape=(1,3,"height","width"),outputs=10))
    dynamic.prepare(0,input_size=(320,320))
    assert dynamic.input_size==(320,320) and dynamic.fmc==5
    assert dynamic._feat_stride_fpn==[8,16,32,64,128]

    original=module.get_scrfd
    calls=[]
    try:
        module.get_scrfd=lambda name,**kwargs:calls.append((name,kwargs)) or "detector"
        assert module.scrfd_2p5gkps(cpu=True)=="detector"
    finally:module.get_scrfd=original
    assert calls==[("2p5gkps",{"download":True,"cpu":True})]


def verify_generate_infer_data_contract():
    from recovered import image_clone_generate_data as module
    from recovered.image_clone_generate_data import read_video_frames,save_frame_data
    import cv2
    import numpy as np

    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);positions=root/"positions";positions.mkdir()
        result=save_frame_data(3,positions,{"fps":25.0,"width":64,"height":48},{
            "bounding_box":np.asarray([1,2,3,4],dtype=np.int32),
            "landmarks":np.asarray([[1.5,2.5]],dtype=np.float32),
        },False)
        assert result is None
        lines=(positions/"000003.txt").read_text(encoding="utf-8").splitlines()
        assert lines[:5]==[
            "fps: 25.0","width: 64","height: 48","is_no_face: False",
            "bounding_box: [1, 2, 3, 4]",
        ]
        assert lines[5].startswith("landmarks: [[1.5, 2.5]]")

        video=root/"input.mp4"
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"mp4v"),20,(32,24))
        assert writer.isOpened()
        writer.write(np.zeros((24,32,3),dtype=np.uint8))
        writer.write(np.full((24,32,3),255,dtype=np.uint8));writer.release()
        info=read_video_frames(video,root/"data")
        assert set(info)=={"fps","width","height","total_frames"}
        assert info["width"]==32 and info["height"]==24 and info["total_frames"]==2
        assert sorted(path.name for path in (root/"data"/"frames").glob("*.jpg"))==[
            "000000.jpg","000001.jpg",
        ]

        frames=root/"mock_frames";frames.mkdir()
        cv2.imwrite(str(frames/"000000.jpg"),np.zeros((100,120,3),dtype=np.uint8))
        calls=[]
        class Detector:
            def __init__(self,**kwargs):pass
            def get_bboxes(self,frame):return np.asarray([[10,20,70,90,.9]]),None
        class Landmarks:
            def __init__(self,**kwargs):pass
            def forward(self,face):
                return np.asarray([[[10,10],[50,10],[50,50],[10,50]]],dtype=np.float32)
        originals=module.FaceDetect,module.pfpld,module.save_frame_data
        try:
            module.FaceDetect=Detector;module.pfpld=Landmarks
            module.save_frame_data=lambda *args:calls.append(args)
            result=module.process_face_frames(frames,1,root/"mock_output",{
                "fps":25.0,"width":120,"height":100,"total_frames":1,
            },cpu=True)
        finally:module.FaceDetect,module.pfpld,module.save_frame_data=originals
        assert result is None and len(calls)==1
        assert calls[0][0]==0 and calls[0][4] is False
        # Native preprocessing expands detector context before landmark inference.
        assert calls[0][3]["bounding_box"].tolist()==[23,85,3,65]
        assert calls[0][3]["landmarks"].tolist()==[[14,30],[54,30],[54,70],[14,70]]


def verify_image_infer_v2_clear_queues_contract():
    from queue import Queue
    from recovered.image_infer_v2_manager import VideoStreamManager

    manager=VideoStreamManager.__new__(VideoStreamManager)
    manager.audio_queues={"normal":Queue(),"danmu":Queue()}
    manager.audio_queues["normal"].put("normal-audio")
    manager.audio_queues["danmu"].put("danmu-audio")
    frame_queue=Queue();frame_queue.put("frame")
    manager.player=types.SimpleNamespace(frame_queue=frame_queue)
    manager._speech_av_mode="fading_out";manager._last_real_queue="danmu"
    manager._pending_fade_in=True;manager._current_audio_path="audio.wav"
    manager._fade_out_remaining=3;manager._fade_out_total=4
    manager._fade_in_remaining=5;manager._fade_in_total=6
    result=manager.clear_audio_queues()
    assert result is None
    assert all(queue.empty() for queue in manager.audio_queues.values())
    assert frame_queue.empty()
    assert manager._speech_av_mode=="normal" and manager._last_real_queue=="silence"
    assert manager._pending_fade_in is False and manager._current_audio_path is None
    assert (manager._fade_out_remaining,manager._fade_out_total,
            manager._fade_in_remaining,manager._fade_in_total)==(0,0,0,0)


def verify_image_infer_v2_switch_model_contract():
    from queue import Queue
    from recovered import image_infer_v2_manager as module

    unsupported=module.VideoStreamManager.__new__(module.VideoStreamManager)
    unsupported.input_mode="camera"
    assert unsupported.switch_image_model("unused") is None

    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/"frames").mkdir();(root/"positions").mkdir()
        for name in ("000000.jpg","000001.jpg","ignore.txt"):(root/"frames"/name).touch()
        class OldEvent:
            def __init__(self):self.set_calls=0
            def set(self):self.set_calls+=1
        class OldThread:
            def __init__(self):self.joins=[]
            def is_alive(self):return True
            def join(self,timeout=None):self.joins.append(timeout)
        class NewEvent:pass
        class NewThread:
            def __init__(self,**kwargs):self.kwargs=kwargs;self.started=False
            def start(self):self.started=True
        manager=module.VideoStreamManager.__new__(module.VideoStreamManager)
        manager.input_mode="file";manager.preload_stop_event=OldEvent();manager.preload_thread=OldThread()
        manager.preloaded_frame_queue=Queue();manager.preloaded_frame_queue.put("old-frame")
        manager.current_frame_position=8;manager.sequence_frame_position=9;manager.current_direction=-1
        manager._preload_frames_worker=lambda:None
        original_threading=module.threading
        try:
            module.threading=types.SimpleNamespace(Event=NewEvent,Thread=NewThread)
            result=manager.switch_image_model(str(root))
        finally:module.threading=original_threading
        assert result is None and manager.preload_stop_event.__class__ is NewEvent
        assert manager.preload_thread.started and manager.preload_thread.kwargs=={
            "target":manager._preload_frames_worker,"daemon":True,
        }
        assert manager.frames_dir==str(root/"frames") and manager.positions_dir==str(root/"positions")
        assert manager.total_frames==2 and manager.preloaded_frame_queue.empty()
        assert (manager.current_frame_position,manager.sequence_frame_position,manager.current_direction)==(0,0,None)


def verify_image_infer_v2_special_video_contract():
    import numpy as np
    from recovered import image_infer_v2_manager as module

    class Player:
        running=True
        def __init__(self):self.uploaded=[]
        def get_last_queue_item(self):return {"index":7}
        def upload_frame(self,item):self.uploaded.append(item)
    class Synthesizer:
        batch_size=2
        def __init__(self):self.calls=[]
        def synthesize_batch(self,features,frames,metadata):
            self.calls.append((features,frames,metadata));return [frame+1 for frame in frames]
    class Reader:
        created=[]
        def __init__(self,**kwargs):self.kwargs=kwargs;self.started=[];self.internal_buffer=[];Reader.created.append(self)
        def start_capture(self,path):self.started.append(path);self.batches=iter([(
            [np.zeros((2,2,3),np.uint8),np.ones((2,2,3),np.uint8)],
            [[{"bounding_box":[0,2,0,2]}],[{"bounding_box":[0,2,0,2]}]],
        )]);return self
        def __iter__(self):return self
        def __next__(self):return next(self.batches)
        def rewind(self):return False
    manager=module.VideoStreamManager.__new__(module.VideoStreamManager)
    manager.player=Player();manager.synthesizer=Synthesizer();manager.processing_lock=threading.Lock()
    manager.device="cpu";manager.enable_occluder=False;manager.occluder_model_path="mask.onnx";manager.face_model_dir="faces"
    manager.output_sample_rate=100;manager.output_samples_per_frame=4;manager._live_frame_physical_index=0
    manager.special_video_face_reader=None
    manager.extract_audio_features=lambda path:[np.zeros((20,256),np.float32),np.ones((20,256),np.float32)]
    original_reader=module.VideoFaceReader;previous_librosa=sys.modules.get("librosa")
    try:
        module.VideoFaceReader=Reader
        sys.modules["librosa"]=types.SimpleNamespace(load=lambda *args,**kwargs:(np.arange(8,dtype=np.float32),100))
        result=manager.drive_with_special_video("special.mp4","speech.wav",True)
    finally:
        module.VideoFaceReader=original_reader
        if previous_librosa is None:sys.modules.pop("librosa",None)
        else:sys.modules["librosa"]=previous_librosa
    assert result is None and len(Reader.created)==1 and Reader.created[0].started==["special.mp4"]
    assert len(manager.player.uploaded)==2 and [item["index"] for item in manager.player.uploaded]==[8,9]
    assert [item["physical_index"] for item in manager.player.uploaded]==[0,1]
    assert all(data=={"is_no_face":True} for data in manager.synthesizer.calls[0][2])
    assert manager.player.uploaded[0]["audio"].tolist()==[0.0,1.0,2.0,3.0]


def verify_image_infer_v2_single_file_contract():
    import numpy as np
    from recovered import image_infer_v2_manager as module

    class Synthesizer:
        batch_size=2
        def __init__(self):self.calls=[]
        def synthesize_batch(self,**kwargs):
            self.calls.append(kwargs)
            return [image+10 for image in kwargs["batch_images"]]
    class Item:
        def __init__(self,value):
            self.image=np.full((3,4,3),value,np.uint8);self.metadata={"index":value}
    manager=module.VideoStreamManager.__new__(module.VideoStreamManager)
    manager.synthesizer=Synthesizer();manager.fps=25
    manager.extract_audio_features=lambda _path:["a","b","c"]
    manager._generate_frame_sequence=lambda count:list(range(count))
    manager._load_batch_frame_data=lambda indices:[Item(index) for index in indices]
    frames=manager.process_single_file("speech.wav")
    assert len(frames)==3 and [int(frame[0,0,0]) for frame in frames]==[10,11,10]
    assert [call["batch_audio_features"] for call in manager.synthesizer.calls]==[["a","b"],["c"]]
    assert manager.synthesizer.calls[0]["batch_frame_data"]==[{"index":0},{"index":1}]

    events=[]
    class Writer:
        def __init__(self,*args):events.append(("writer",args));self.frames=[]
        def isOpened(self):return True
        def write(self,frame):self.frames.append(frame);events.append(("write",int(frame[0,0,0])))
        def release(self):events.append(("release",))
    original_cv2,original_run,original_remove=module.cv2, module.subprocess.run, module.os.remove
    try:
        module.cv2=types.SimpleNamespace(
            VideoWriter_fourcc=lambda *chars:(events.append(("fourcc",chars)) or 1234),
            VideoWriter=Writer,
        )
        module.subprocess.run=lambda command,**kwargs:(events.append(("ffmpeg",command,kwargs)) or types.SimpleNamespace())
        module.os.remove=lambda path:events.append(("remove",path))
        manager.synthesizer.calls.clear()
        result=manager.process_single_file("speech.wav","render.mp4",batch_size=2)
    finally:
        module.cv2,module.subprocess.run,module.os.remove=original_cv2,original_run,original_remove
    assert result=="render.mp4"
    writer_args=next(event[1] for event in events if event[0]=="writer")
    assert writer_args==(os.path.splitext("render.mp4")[0]+"_temp.mp4",1234,25,(4,3))
    ffmpeg=next(event for event in events if event[0]=="ffmpeg")
    assert ffmpeg[1]==["ffmpeg","-y","-i","render_temp.mp4","-i","speech.wav",
                       "-c:v","copy","-c:a","aac","-strict","experimental",
                       "-map","0:v:0","-map","1:a:0","render.mp4"]
    assert ffmpeg[2]=={"check":True} and events[-1]==("remove","render_temp.mp4")


def main():
    global ORIGINAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=os.environ.get("YUNCHUANG_RUNTIME_ROOT"),
                        help="Original v122 distribution root or _internal directory; "
                             "also accepts YUNCHUANG_RUNTIME_ROOT")
    args = parser.parse_args()
    try:
        ORIGINAL = resolve_runtime_internal(args.runtime_root or ORIGINAL)
    except ValueError as error:
        parser.error(str(error))
    print(f"Original runtime: {ORIGINAL}", flush=True)
    sys.path.insert(0, str(WORKSPACE)); sys.path.insert(0, str(HERE))
    assert compileall.compile_dir(HERE, quiet=1), "compileall failed"
    verify_capture_window_change_contract()
    verify_auto_live_ocr_result_contract()
    verify_position_compat_contract()
    verify_image_clone_face_detector_contract()
    verify_hubert_extractor_contract()
    verify_image_clone_landmark_geometry()
    verify_lip_detector_batch_crop_contract()
    verify_generate_face_landmark_contract()
    verify_generate_scrfd_contract()
    verify_generate_infer_data_contract()
    verify_image_infer_v2_clear_queues_contract()
    verify_image_infer_v2_switch_model_contract()
    verify_image_infer_v2_special_video_contract()
    verify_image_infer_v2_single_file_contract()
    verify_image_clone_video_normalize_contract()
    verify_voice_clone_lifecycle()
    verify_whisper_runtime_contract()
    verify_online_voice_runtime_contract()
    verify_output_resolution_contract()
    verify_customer_pack_contract()
    verify_forbidden_word_replacement_contract()
    verify_audio_cache_contract()
    verify_audio_devices_contract()
    verify_audio_player_scan_contract()
    verify_live_sticker_prompt_contract()
    verify_mapping(); verify_all_modules_importable(); verify_environment_manifests(); verify_voice_helpers(); verify_asr_temp_audio_lifecycle(); verify_audio_duration_fallbacks(); verify_title_fallback_parser(); verify_sentence_generalization_contract(); verify_short_video_language_routing(); verify_short_video_render_parameters(); verify_short_video_metadata_lifecycle(); verify_voice_v2_lifecycle(); verify_voice_v3_lifecycle(); verify_zipvoice_lifecycle(); verify_taobao_explain_cycle(); verify_taobao_action_dispatch(); verify_taobao_control_recovery(); verify_live_brain(); verify_face_hand_manager(); verify_face_hand_player_av_queue(); verify_language_and_live_helpers(); verify_video_player_stream_helpers(); verify_edit_audio_contract(); verify_cloud_avatar_prompt_contract(); verify_live_sticker_title_routing_contract(); verify_taobao_private_helpers(); verify_product_kt_geometry_helpers(); verify_product_image_pipeline(); verify_remaining_private_entrypoints(); verify_auto_live_action_spacing_contract(); verify_image_clone_resource_lifecycle(); verify_image_clone_save_frame_diagnostics(); verify_image_clone_model_assets(); verify_image_clone_generate_cleanup(); verify_pfld_ghostone_architecture(); verify_s3fd_architecture(); verify_kuaishou_message_protocol(); verify_text_special_variables(); verify_funasr_sentence_contract(); verify_get_srt_lifecycle(); verify_ip_agent_post_process_helpers(); verify_origin_video_ffmpeg_reader(); verify_ip_agent_real_media_pipeline(); verify_ip_agent_project_schema_contract(); verify_ip_agent_rewrite_contract(); verify_generate_script_contract(); verify_ip_agent_publish_meta_contract(); verify_main_system_identity_contract(); verify_main_local_resources_contract(); verify_main_file_dialog_contract(); verify_main_live_sticker_project_contract(); verify_clone_manager_local_resources_contract(); verify_main_translate_text_contract(); verify_main_llm_config_contract(); verify_record_live_start_lifecycle(); verify_barrage_port_cleanup(); verify_shopee_action_dispatch(); verify_shopee_page_states(); verify_controller_workers(); verify_v2_fade_curves(); verify_v2_queue_selection(); verify_keyword_contract_behaviors(); verify_core_method_coverage(); verify_all_binary_class_methods(); verify_binary_class_signature_arity(); verify_binary_module_signature_arity(); verify_public_name_inventory(); verify_binary_qualified_module_names(); asyncio.run(verify_live_protocols())
    print("PASS: 128/128 mappings/imports, public/private callable and binary class method inventories, signatures, core methods, live managers, protocols")


if __name__ == "__main__": main()
