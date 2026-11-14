"""Recovered batch WAV/TXT editor API used by the standalone WebView tool."""

from __future__ import annotations

import base64
import os
import re
import shutil
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


DEFAULT_CONFIG = {
    "device": "cuda",
    "items_per_page": 50,
    "last_folder": "",
    "models_base_path": "assets/pretrained_models",
}

EDIT_AUDIO_HTML = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>音频批量编辑</title><style>
body{font:14px system-ui;margin:0;background:#f3f4f6;color:#111827}main{max-width:1000px;margin:auto;padding:20px}
.bar,.item{background:white;padding:12px;margin-bottom:12px;border-radius:10px}.row{display:flex;gap:8px;flex-wrap:wrap}
input,textarea,button{font:inherit;padding:8px;border:1px solid #d1d5db;border-radius:7px}textarea{width:100%;box-sizing:border-box}
button{cursor:pointer;background:#2563eb;color:white}.danger{background:#dc2626}#status{margin:10px 0}audio{width:100%}
</style></head><body><main><h2>音频批量编辑</h2><div class="bar"><div class="row">
<button onclick="choose()">选择文件夹</button><input id="old" placeholder="原关键词"><input id="new" placeholder="新关键词">
<button onclick="replaceAll()">批量替换</button><input id="filters" placeholder="删除关键词，逗号分隔">
<button class="danger" onclick="filterDelete()">过滤删除</button><button onclick="convertAll()">全部重新合成</button></div>
<div id="folder"></div><div id="status"></div></div><div id="items"></div><audio id="player" controls></audio></main><script>
let state={items:[]}; const api=()=>window.pywebview.api;
function esc(v){return String(v||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function sync(){document.querySelectorAll('textarea[data-name]').forEach(e=>{const i=state.items.find(x=>x.basename===e.dataset.name);if(i)i.current_text=e.value.trim()})}
function render(p){if(p)state={...state,...p};folder.textContent=state.current_folder||'';status.textContent=state.message||'';
items.innerHTML=(state.items||[]).map(i=>`<div class="item"><b>${esc(i.basename)}.wav</b><textarea data-name="${esc(i.basename)}">${esc(i.current_text)}</textarea><div class="row"><button onclick="play('${esc(i.basename)}')">播放</button><button onclick="convertOne('${esc(i.basename)}')">重新合成</button></div></div>`).join('')}
async function choose(){render(await api().select_folder())} async function replaceAll(){sync();render(await api().apply_keyword_replace(old.value,new.value,state.items))}
async function filterDelete(){sync();render(await api().filter_delete(filters.value,state.items))} async function convertOne(n){sync();const i=state.items.find(x=>x.basename===n);render(await api().convert_item(n,i.current_text))}
async function convertAll(){sync();render(await api().convert_all(state.items))} async function play(n){const p=await api().get_audio_base64(n);render(p);if(p.success){player.src=p.audio_data;player.play()}}
window.addEventListener('pywebviewready',async()=>render(await api().get_state()));
</script></body></html>"""

# Verbatim UI embedded by tools/edit_audio/main.pyd.
EDIT_AUDIO_HTML = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>碎片化音频编辑</title>
    <style>
        body { margin: 0; font-family: "Microsoft YaHei", sans-serif; background: #f5f7fb; color: #222; }
        .layout { display: flex; height: 100vh; box-sizing: border-box; }
        .sidebar { width: 320px; padding: 16px; border-right: 1px solid #e5e7eb; overflow-y: auto; background: #fff; }
        .content { flex: 1; padding: 16px; overflow: hidden; display: flex; flex-direction: column; }
        .card { background: #fff; border-radius: 10px; padding: 14px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        h1 { margin: 0 0 12px 0; font-size: 20px; }
        h2 { margin: 0 0 10px 0; font-size: 15px; }
        label { display: block; font-size: 13px; margin-bottom: 6px; font-weight: bold; }
        input, textarea, button { box-sizing: border-box; font-size: 13px; }
        input, textarea { width: 100%; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 8px; }
        textarea { resize: vertical; min-height: 72px; }
        button { border: none; border-radius: 8px; padding: 9px 12px; cursor: pointer; color: #fff; background: #4f46e5; width: 100%; }
        button:hover { background: #4338ca; }
        .btn-secondary { background: #10b981; }
        .btn-secondary:hover { background: #059669; }
        .btn-danger { background: #ef4444; }
        .btn-danger:hover { background: #dc2626; }
        .folder-path { font-size: 12px; color: #555; word-break: break-all; margin-top: 10px; }
        .status-bar { padding: 10px 12px; background: #eef2ff; border-radius: 8px; font-size: 13px; color: #3730a3; margin-bottom: 12px; }
        .pagination { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
        .pagination button { width: auto; }
        .item-list { overflow-y: auto; flex: 1; padding-right: 6px; }
        .audio-item { background: #fff; border-radius: 10px; padding: 12px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .audio-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 10px; }
        .audio-name { font-weight: bold; }
        .audio-meta { font-size: 12px; color: #666; }
        .audio-actions { display: flex; gap: 8px; margin-top: 8px; }
        .audio-actions button { width: auto; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; }
        .badge.modified { background: #fef3c7; color: #92400e; }
        .badge.clean { background: #dcfce7; color: #166534; }
        .tip { font-size: 12px; color: #666; line-height: 1.6; margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="layout">
        <div class="sidebar">
            <h1>碎片化音频编辑</h1>

            <div class="card">
                <h2>工作目录</h2>
                <button onclick="selectFolder()">选择文件夹</button>
                <div class="folder-path" id="folderPath">尚未选择文件夹</div>
            </div>

            <div class="card">
                <h2>关键词替换</h2>
                <label>原文</label>
                <input id="oldKeyword" type="text" />
                <label style="margin-top: 10px;">替换为</label>
                <input id="newKeyword" type="text" />
                <button style="margin-top: 10px;" onclick="runKeywordReplace()">执行替换</button>
            </div>

            <div class="card">
                <h2>关键词过滤删除</h2>
                <div class="tip">多个关键词用空格分隔，命中的音频和文本会一起删除。</div>
                <label>关键词</label>
                <input id="filterKeywords" type="text" />
                <button class="btn-danger" style="margin-top: 10px;" onclick="runKeywordFilterDelete()">删除命中片段</button>
            </div>

            <div class="card">
                <h2>批量操作</h2>
                <button onclick="convertAll()">一键全部转化</button>
            </div>
        </div>

        <div class="content">
            <div class="status-bar" id="statusBar">准备就绪</div>
            <div class="pagination">
                <button onclick="prevPage()">上一页</button>
                <div id="pageInfo">未加载</div>
                <button onclick="nextPage()">下一页</button>
            </div>
            <div class="item-list" id="itemList"></div>
        </div>
    </div>
    <audio id="audioPlayer"></audio>

    <script>
        let state = {
            items: [],
            currentPage: 1,
            currentFolder: '',
            itemsPerPage: 50,
            currentPlaying: null,
        };

        function setStatus(message) {
            document.getElementById('statusBar').textContent = message || '准备就绪';
        }

        function escapeHtml(text) {
            return String(text || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function applyPayload(payload) {
            if (!payload) return;
            if (payload.items_per_page) {
                state.itemsPerPage = Math.max(1, parseInt(payload.items_per_page, 10) || 50);
            }
            if (Array.isArray(payload.items)) {
                state.items = payload.items;
            }
            state.currentFolder = payload.current_folder || '';
            document.getElementById('folderPath').textContent = state.currentFolder || '尚未选择文件夹';
            if (payload.message) {
                setStatus(payload.message);
            }
            renderItems();
        }

        function getCurrentPageItems() {
            const start = (state.currentPage - 1) * state.itemsPerPage;
            return state.items.slice(start, start + state.itemsPerPage);
        }

        function syncStateFromDom() {
            document.querySelectorAll('.item-text').forEach((textarea) => {
                const basename = textarea.dataset.basename;
                const item = state.items.find((entry) => entry.basename === basename);
                if (item) {
                    item.current_text = textarea.value.trim();
                }
            });
        }

        function renderItems() {
            const itemList = document.getElementById('itemList');
            if (!state.items.length) {
                itemList.innerHTML = '<div class="card">当前没有可编辑的音频片段</div>';
                document.getElementById('pageInfo').textContent = '未加载';
                return;
            }

            const totalPages = Math.max(1, Math.ceil(state.items.length / state.itemsPerPage));
            if (state.currentPage > totalPages) {
                state.currentPage = totalPages;
            }

            const pageItems = getCurrentPageItems();
            itemList.innerHTML = pageItems.map((item) => {
                const modified = (item.current_text || '') !== (item.original_text || '');
                return `
                    <div class="audio-item">
                        <div class="audio-head">
                            <div>
                                <div class="audio-name">${escapeHtml(item.basename)}.wav</div>
                                <div class="audio-meta">${modified ? '文本已修改' : '文本未修改'}</div>
                            </div>
                            <span class="badge ${modified ? 'modified' : 'clean'}">${modified ? '已修改' : '未修改'}</span>
                        </div>
                        <textarea class="item-text" data-basename="${escapeHtml(item.basename)}">${escapeHtml(item.current_text || '')}</textarea>
                        <div class="audio-actions">
                            <button onclick="playAudio('${escapeHtml(item.basename)}')">试听</button>
                            <button class="btn-secondary" onclick="convertItem('${escapeHtml(item.basename)}')">开始转化</button>
                        </div>
                    </div>
                `;
            }).join('');

            document.getElementById('pageInfo').textContent = `第 ${state.currentPage} / ${totalPages} 页，共 ${state.items.length} 条`;
        }

        async function initialize() {
            const payload = await pywebview.api.get_state();
            applyPayload(payload);
        }

        async function selectFolder() {
            syncStateFromDom();
            const payload = await pywebview.api.select_folder();
            state.currentPage = 1;
            applyPayload(payload);
        }

        async function runKeywordReplace() {
            syncStateFromDom();
            const payload = await pywebview.api.apply_keyword_replace(
                document.getElementById('oldKeyword').value,
                document.getElementById('newKeyword').value,
                state.items
            );
            applyPayload(payload);
        }

        async function runKeywordFilterDelete() {
            syncStateFromDom();
            if (!confirm('此操作会删除命中的音频和文本文件，是否继续？')) {
                return;
            }
            const payload = await pywebview.api.filter_delete(
                document.getElementById('filterKeywords').value,
                state.items
            );
            state.currentPage = 1;
            applyPayload(payload);
        }

        async function convertItem(basename) {
            syncStateFromDom();
            const item = state.items.find((entry) => entry.basename === basename);
            if (!item) return;
            setStatus(`正在转化 ${basename}...`);
            const payload = await pywebview.api.convert_item(basename, item.current_text);
            applyPayload(payload);
        }

        async function convertAll() {
            syncStateFromDom();
            if (!state.items.length) {
                setStatus('请先加载音频文件夹');
                return;
            }
            if (!confirm('即将批量转化所有已修改的条目，是否继续？')) {
                return;
            }
            setStatus('正在批量转化，请稍候...');
            const payload = await pywebview.api.convert_all(state.items);
            applyPayload(payload);
            if (payload.failed_items && payload.failed_items.length) {
                alert(payload.failed_items.join('\n'));
            }
        }

        async function playAudio(basename) {
            const audioPlayer = document.getElementById('audioPlayer');
            if (state.currentPlaying === basename && !audioPlayer.paused) {
                audioPlayer.pause();
                state.currentPlaying = null;
                setStatus('已停止播放');
                return;
            }

            const payload = await pywebview.api.get_audio_base64(basename);
            if (!payload.success) {
                setStatus(payload.message || '音频读取失败');
                return;
            }
            audioPlayer.src = payload.audio_data;
            await audioPlayer.play();
            state.currentPlaying = basename;
            setStatus(`正在播放 ${basename}.wav`);
        }

        function prevPage() {
            if (state.currentPage > 1) {
                syncStateFromDom();
                state.currentPage -= 1;
                renderItems();
            }
        }

        function nextPage() {
            const totalPages = Math.max(1, Math.ceil(state.items.length / state.itemsPerPage));
            if (state.currentPage < totalPages) {
                syncStateFromDom();
                state.currentPage += 1;
                renderItems();
            }
        }

        window.addEventListener('pywebviewready', initialize);
    </script>
</body>
</html>

"""
EDIT_AUDIO_HTML = EDIT_AUDIO_HTML[1:-1]


def natural_sort_key(value):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", str(value))]


class AudioEditorAPI:
    MAX_PREVIEW_BYTES = 64 * 1024 * 1024

    def __init__(self):
        runtime = Path(os.environ.get("YUNCHUANG_RUNTIME_DIR") or
                       getattr(sys, "_MEIPASS", Path.cwd())).resolve()
        self.runtime_dir = runtime
        self.config_path = runtime / "tools" / "edit_audio" / "config" / "config.yaml"
        self.root_config_path = runtime / "config" / "config.yaml"
        self.config = self._load_config()
        self.current_folder = ""
        self.items: Dict[str, Dict[str, Any]] = {}
        self.synthesizer = None
        self._load_last_folder()

    def _root_defaults(self) -> Dict[str, Any]:
        if not self.root_config_path.is_file():
            return {}
        try:
            value = yaml.safe_load(self.root_config_path.read_text(encoding="utf-8")) or {}
            return {key: value[key] for key in ("device", "models_base_path") if key in value}
        except Exception as error:
            print(f"读取主配置失败: {error}")
            return {}

    def _load_config(self) -> Dict[str, Any]:
        config = dict(DEFAULT_CONFIG)
        config.update(self._root_defaults())
        if self.config_path.is_file():
            try:
                loaded = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    config.update(loaded)
            except Exception as error:
                print(f"读取本地配置失败: {error}")
        return config

    def _save_config(self, config: Optional[Dict[str, Any]] = None):
        if config is not None:
            self.config = dict(config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            yaml.safe_dump(self.config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def _resolve_path(self, path_value: str) -> str:
        path = Path(str(path_value or "")).expanduser()
        return str(path.resolve() if path.is_absolute() else (self.runtime_dir / path).resolve())

    def _load_last_folder(self):
        folder = str(self.config.get("last_folder") or "").strip()
        if folder and Path(folder).is_dir():
            self._load_folder(folder)

    def _serialize_items(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.items.values()]

    def _build_state(self, message="", success=True, **extra):
        state = {
            "success": bool(success), "message": message,
            "current_folder": self.current_folder,
            "items": self._serialize_items(),
            "items_per_page": max(1, int(self.config.get("items_per_page", 50))),
        }
        state.update(extra)
        return state

    def _item_from_basename(self, basename: str) -> Dict[str, Any]:
        safe_name = Path(str(basename)).stem
        wav_path = Path(self.current_folder) / f"{safe_name}.wav"
        txt_path = Path(self.current_folder) / f"{safe_name}.txt"
        text = txt_path.read_text(encoding="utf-8").strip() if txt_path.is_file() else ""
        return {"basename": safe_name, "original_text": text, "current_text": text,
                "wav_path": str(wav_path), "txt_path": str(txt_path)}

    @staticmethod
    def _validate_wav(path: Path) -> Dict[str, Any]:
        try:
            with wave.open(str(path), "rb") as source:
                channels, width, rate, frames = (source.getnchannels(), source.getsampwidth(),
                                                  source.getframerate(), source.getnframes())
                compression = source.getcomptype()
        except (OSError, EOFError, wave.Error) as error:
            raise ValueError(f"{path.name} 不是有效的 WAV: {error}") from error
        if compression != "NONE" or channels not in range(1, 9) or width not in range(1, 5):
            raise ValueError(f"{path.name} 的 WAV 编码或声道不受支持")
        if not 8000 <= rate <= 192000 or frames <= 0:
            raise ValueError(f"{path.name} 的采样率或时长无效")
        duration = frames / rate
        if duration > 4 * 60 * 60:
            raise ValueError(f"{path.name} 超过 4 小时时长上限")
        return {"channels": channels, "sample_width": width, "sample_rate": rate,
                "frames": frames, "duration": duration}

    def _convert_basename(self, basename: str) -> Dict[str, Any]:
        item = self.items[basename]
        text_content = str(item["current_text"] or "").strip()
        if not text_content:
            raise ValueError(".txt 为空，无法转化")
        if text_content == item["original_text"]:
            return {"success": True, "changed": False, "message": "文本未修改"}
        synthesizer = self._ensure_synthesizer(item["wav_path"], item["original_text"])
        temp_output_path = synthesizer.synthesize(
            text=text_content,
            speed=1.0,
            reference_audio=item["wav_path"],
            reference_text=item["original_text"],
        )
        if not temp_output_path or not Path(temp_output_path).is_file():
            raise RuntimeError(f"{basename} 未生成有效音频")
        self._validate_wav(Path(temp_output_path))
        shutil.move(temp_output_path, item["wav_path"])
        Path(item["txt_path"]).write_text(text_content, encoding="utf-8")
        item["original_text"] = item["current_text"] = text_content
        return {"success": True, "changed": True, "message": "转化完成"}

    def _load_folder(self, folder_path: str) -> str:
        folder = Path(folder_path).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError("文件夹无效")
        wav_files = sorted(
            (path for path in folder.iterdir()
             if path.is_file() and path.name.lower().endswith(".wav")),
            key=lambda path: natural_sort_key(path.name),
        )
        if not wav_files:
            raise ValueError("文件夹中没有 wav 文件")
        if any(not path.with_suffix(".txt").is_file() for path in wav_files):
            raise ValueError(
                f"找到 {len(wav_files)} 个 wav，但缺少同名 txt，无法加载。"
                "请先用「AI碎片化音频处理」生成带文本的切片。"
            )
        for path in wav_files:
            self._validate_wav(path)
        self.current_folder = str(folder)
        self.items = {
            path.stem: self._item_from_basename(path.stem) for path in wav_files
        }
        self.config["last_folder"] = self.current_folder
        self._save_config()
        return self.current_folder

    def _sync_items(self, items: List[Dict[str, Any]], persist: bool = False):
        by_name = {str(item.get("basename")): item for item in items or []}
        for local in self.items.values():
            incoming = by_name.get(local["basename"])
            if incoming is None:
                continue
            local["current_text"] = str(incoming.get("current_text") or "").strip()
            if persist:
                Path(local["txt_path"]).write_text(local["current_text"], encoding="utf-8")
                local["original_text"] = local["current_text"]
        return self._serialize_items()

    def _ensure_synthesizer(self, sample_audio: str, sample_text: str):
        if self.synthesizer is not None:
            return self.synthesizer
        from bin.voice_infer.infer_api import VoiceSynthesizer

        self.synthesizer = VoiceSynthesizer(
            self._resolve_path(self.config.get("models_base_path")),
            sample_audio, sample_text,
            device=str(self.config.get("device") or "cuda"),
        )
        return self.synthesizer

    def get_state(self):
        return self._build_state()

    def select_folder(self):
        try:
            import webview
            selected = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            if not selected:
                return self._build_state("已取消选择", False)
            folder = selected[0] if isinstance(selected, (tuple, list)) else selected
            self._load_folder(folder)
            return self._build_state(f"已加载 {len(self.items)} 个音频文件")
        except Exception as error:
            return self._build_state(str(error), False)

    def apply_keyword_replace(self, old_keyword: str, new_keyword: str,
                              items: List[Dict[str, Any]]):
        old = str(old_keyword or "")
        if not old:
            return self._build_state("请输入要替换的原文", False)
        self._sync_items(items)
        replaced_count = 0
        for item in self.items.values():
            if old in item["current_text"]:
                item["current_text"] = item["current_text"].replace(old, str(new_keyword or ""))
                replaced_count += 1
        self._sync_items(self._serialize_items(), persist=True)
        return self._build_state(
            f"替换完成，共处理 {replaced_count} 条",
            replaced_count=replaced_count,
        )

    def filter_delete(self, keywords_text: str, items: List[Dict[str, Any]]):
        keywords = [value.strip() for value in re.split(r"[,，\n]+", str(keywords_text or ""))
                    if value.strip()]
        if not keywords:
            return self._build_state("请输入过滤关键词", False)
        self._sync_items(items)
        to_delete = [item for item in self.items.values()
                     if any(keyword in item["current_text"] for keyword in keywords)]
        for item in to_delete:
            for key in ("wav_path", "txt_path"):
                Path(item[key]).unlink(missing_ok=True)
        for item in to_delete:
            self.items.pop(item["basename"], None)
        return self._build_state(
            f"删除完成，共删除 {len(to_delete)} 条",
            deleted_count=len(to_delete),
        )

    def convert_item(self, basename: str, current_text: str):
        try:
            basename = Path(basename).stem
            if basename not in self.items:
                return self._build_state("目标音频不存在", False)
            item = self.items[basename]
            text = str(current_text or "").strip()
            if not text:
                return self._build_state(".txt 为空，无法转化", False)
            item["current_text"] = text
            result = self._convert_basename(basename)
            return self._build_state(result["message"], result=result)
        except Exception as error:
            return self._build_state(f"转化失败: {error}", False)

    def convert_all(self, items: List[Dict[str, Any]]):
        try:
            self._sync_items(items)
            modified_items = [
                item for item in self.items.values()
                if item["current_text"] != item["original_text"]
            ]
            if not modified_items:
                return self._build_state("没有检测到修改过的文本", False)
            success_count, failed_items = 0, []
            for item in modified_items:
                try:
                    self._convert_basename(item["basename"])
                    success_count += 1
                except Exception as error:
                    failed_items.append(f"{item['basename']}: {error}")
            return self._build_state(
                f"批量转化完成，成功 {success_count}，失败 {len(failed_items)}",
                success=not failed_items,
                success_count=success_count,
                failed_items=failed_items,
            )
        except Exception as error:
            return self._build_state(f"批量转化失败: {error}", False)

    def get_audio_base64(self, basename: str):
        try:
            safe_name = Path(str(basename)).stem
            if safe_name not in self.items:
                raise ValueError("目标音频不存在")
            path = Path(self.current_folder) / f"{safe_name}.wav"
            self._validate_wav(path)
            if path.stat().st_size > self.MAX_PREVIEW_BYTES:
                raise ValueError("音频超过 64 MiB 预览上限")
            audio_data = "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
            return self._build_state(audio_data=audio_data)
        except Exception as error:
            return self._build_state(str(error), False)

    def shutdown(self):
        if self.synthesizer is not None:
            try:
                self.synthesizer.clear()
            finally:
                self.synthesizer = None
        return {"success": True}


def main():
    try:
        import webview
    except ImportError as error:
        raise RuntimeError("音频编辑器需要 pywebview") from error
    api = AudioEditorAPI()
    window = webview.create_window("碎片化音频编辑", html=EDIT_AUDIO_HTML, js_api=api,
                                   width=1400, height=860, min_size=(1100, 720),
                                   resizable=True, text_select=True)

    def on_closed():
        api.shutdown()
        os._exit(0)

    window.events.closed += on_closed
    webview.start(debug=False, private_mode=False)


if __name__ == "__main__":
    main()
