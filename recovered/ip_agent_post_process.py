"""Recovered IP-agent finishing helpers: music, covers, fonts and keywords."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


CLIENT_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_ROOT = CLIENT_ROOT / "assets" / "ip_agent_resources"
MUSIC_CACHE_DIR = RESOURCE_ROOT / "music_cache"
MUSIC_LIBRARY_PATH = RESOURCE_ROOT / "cloud_music_library.csv"
FONT_DIR = RESOURCE_ROOT / "fonts"
DURABLE_MUSIC_HOST_HINTS = ("mixkit.co", "pixabay.com", "aliyuncs.com", "myqcloud.com")
DURABLE_FALLBACK_MUSIC_URLS = (
    "https://assets.mixkit.co/music/130/130.mp3",
    "https://assets.mixkit.co/music/695/695.mp3",
)

FONT_OPTIONS = [
    {"id": "system", "name": "系统默认", "file": ""},
    {"id": "siyuan_heiti", "name": "思源黑体", "file": "SourceHanSansCN-Regular.otf"},
    {"id": "wenkai_light", "name": "霞鹜文楷", "file": "LXGWWenKai-Light.ttf"},
    {"id": "alipuhui", "name": "阿里巴巴普惠体", "file": "AlibabaPuHuiTi-3-55-Regular.ttf"},
]
COVER_TEMPLATES = [
    {"id": "impact_yellow", "name": "冲击黄", "background": "#211C12", "accent": "#FFD43B", "text": "#FFFFFF"},
    {"id": "business_blue", "name": "商务蓝", "background": "#071B36", "accent": "#3B82F6", "text": "#FFFFFF"},
    {"id": "fresh_green", "name": "清新绿", "background": "#063A30", "accent": "#0D3D35", "text": "#FFF8E6"},
    {"id": "red_focus", "name": "焦点红", "background": "#2A0606", "accent": "#FF3B30", "text": "#FFFFFF"},
    {"id": "ink_style", "name": "墨色", "background": "#111111", "accent": "#111827", "text": "#FFFFFF"},
]


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode: raise RuntimeError(result.stderr.strip() or "命令执行失败")
    return result


def _safe_filename(value, default="asset"):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return value[:80] or default


def _hex_to_rgb(color):
    value=str(color or "").strip().lstrip("#")
    if len(value)==3:value="".join(char*2 for char in value)
    if len(value)!=6 or not re.fullmatch(r"[0-9a-fA-F]{6}",value):
        raise ValueError(f"Invalid RGB color: {color}")
    return tuple(int(value[index:index+2],16) for index in (0,2,4))


def _template(template_id):
    return dict(next((item for item in COVER_TEMPLATES if item["id"]==template_id),COVER_TEMPLATES[0]))


def _text_width(draw, text, font):
    try:
        box=draw.textbbox((0,0),str(text),font=font)
        return int(box[2]-box[0])
    except AttributeError:
        return int(draw.textlength(str(text),font=font))


def _wrap_title(draw, text, font, max_width, max_lines=4):
    value=re.sub(r"\s+"," ",str(text or "").strip())
    if not value:return []
    lines=[];current=""
    for character in value:
        candidate=current+character
        if current and _text_width(draw,candidate,font)>int(max_width):
            lines.append(current.rstrip());current=character.lstrip()
            if len(lines)>=max(1,int(max_lines)):break
        else:current=candidate
    if len(lines)<max(1,int(max_lines)) and current:lines.append(current.rstrip())
    consumed="".join(lines)
    if len(consumed)<len(value) and lines:
        suffix="…";last=lines[-1]
        while last and _text_width(draw,last+suffix,font)>int(max_width):last=last[:-1]
        lines[-1]=last.rstrip()+suffix
    return lines


def _cover_canvas(frame, target_ratio=3/4):
    from PIL import Image
    image=frame.convert("RGB");width,height=image.size
    if width/height>float(target_ratio):
        crop=round(height*float(target_ratio));left=(width-crop)//2
        image=image.crop((left,0,left+crop,height))
    else:
        crop=round(width/float(target_ratio));top=(height-crop)//2
        image=image.crop((0,top,width,top+crop))
    return image.resize((1080,1440),Image.Resampling.LANCZOS)


def _download_url_to_path(url, output_path):
    target=Path(output_path);target.parent.mkdir(parents=True,exist_ok=True)
    request=urllib.request.Request(str(url),headers={"User-Agent":"Mozilla/5.0"})
    temporary=target.with_suffix(target.suffix+".part")
    try:
        with urllib.request.urlopen(request,timeout=30) as response,temporary.open("wb") as output:
            shutil.copyfileobj(response,output)
        if not temporary.is_file() or not temporary.stat().st_size:raise RuntimeError("empty response")
        os.replace(temporary,target)
    finally:
        if temporary.exists():temporary.unlink()
    return None


def _is_durable_music_url(url):
    try: host = urlparse(url).netloc.lower()
    except Exception: return False
    return urlparse(url).scheme in {"http", "https"} and any(hint in host for hint in DURABLE_MUSIC_HOST_HINTS)


def _fallback_music_url(seed_text):
    digest = int(hashlib.sha256(str(seed_text).encode()).hexdigest()[:8], 16)
    return DURABLE_FALLBACK_MUSIC_URLS[digest % len(DURABLE_FALLBACK_MUSIC_URLS)]


def _probe_json(path):
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    return json.loads(_run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def _video_duration(path):
    return float((_probe_json(path).get("format") or {}).get("duration") or 0)


def _has_audio(path):
    return any(item.get("codec_type") == "audio" for item in _probe_json(path).get("streams", []))


def list_music_library(category="", limit=300):
    items = []
    if MUSIC_LIBRARY_PATH.is_file():
        with MUSIC_LIBRARY_PATH.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if category and row.get("category") != category: continue
                items.append(row)
                if len(items) >= limit: break
    return {"items": items, "categories": sorted({x.get("category", "") for x in items if x.get("category")})}


def list_font_options(): return [dict(item) for item in FONT_OPTIONS]
def list_cover_templates(): return [dict(item) for item in COVER_TEMPLATES]


def _font_path(font_file=None):
    candidates = [font_file, FONT_DIR / str(font_file or ""), Path("C:/Windows/Fonts/msyh.ttc"),
                  Path("/System/Library/Fonts/PingFang.ttc"), Path("/System/Library/Fonts/STHeiti Medium.ttc")]
    return next((str(Path(x)) for x in candidates if x and Path(x).is_file()), None)


def resolve_font_family_name(font_file=None, fallback=""):
    path = _font_path(font_file)
    if path:
        try:
            from fontTools.ttLib import TTFont
            font = TTFont(path, fontNumber=0)
            for record in font["name"].names:
                if record.nameID == 1: return record.toUnicode()
        except Exception: pass
    return fallback


def _generate_fallback_music(output_path, seed_text=""):
    output = Path(output_path); output.parent.mkdir(parents=True, exist_ok=True)
    frequency = 180 + int(hashlib.md5(str(seed_text).encode()).hexdigest()[:4], 16) % 240
    _run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-f", "lavfi", "-i",
          f"sine=frequency={frequency}:duration=24", "-filter:a", "volume=0.07,afade=t=in:ss=0:d=1,afade=t=out:st=23:d=1",
          "-b:a", "128k", str(output)])
    return str(output)


def download_music(music_id, url):
    MUSIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = MUSIC_CACHE_DIR / (_safe_filename(music_id, "music") + "_stable.mp3")
    if target.is_file() and target.stat().st_size: return str(target)
    source_url = url if _is_durable_music_url(url) else _fallback_music_url(music_id)
    try:
        _download_url_to_path(source_url,target)
    except Exception: return _generate_fallback_music(target, music_id)
    return str(target)


def mix_bgm(video_path, bgm_path, output_path, *, volume=0.16):
    output = Path(output_path); output.parent.mkdir(parents=True, exist_ok=True)
    duration = _video_duration(video_path)
    command = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", str(video_path), "-stream_loop", "-1", "-i", str(bgm_path)]
    if _has_audio(video_path):
        graph = f"[1:a]volume={float(volume)},atrim=0:{duration}[bgm];[0:a]volume=1.0[main];[main][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]"
        command += ["-filter_complex", graph, "-map", "0:v:0", "-map", "[a]"]
    else:
        command += ["-filter:a", f"volume={float(volume)}", "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    command += ["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(output)]
    _run(command); return str(output)


def _first_video_frame(video_path):
    import cv2
    capture = cv2.VideoCapture(str(video_path)); ok, frame = capture.read(); capture.release()
    if not ok: raise RuntimeError("无法读取视频首帧")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _load_font(size, font_file=None):
    from PIL import ImageFont
    path = _font_path(font_file)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def generate_cover(video_path, output_path, *, title, template_id="impact_yellow", font_file=None):
    from PIL import Image, ImageDraw
    frame = _cover_canvas(Image.fromarray(_first_video_frame(video_path)))
    style = _template(template_id)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0)); draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 860, 1080, 1440), fill=style["background"] + "D9")
    font = _load_font(86, font_file); text = str(title or "精彩内容")[:64]
    lines = _wrap_title(draw,text,font,940,4)
    for index, line in enumerate(lines):
        draw.text((70, 930 + index * 112), line, font=font, fill=style["text"], stroke_width=2, stroke_fill="#111111")
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB").save(target, quality=95)
    return str(target)


def infer_keywords_from_text(text, limit=8):
    stop_words = {"这个", "那个", "我们", "你们", "他们", "可以", "就是", "一个", "什么", "没有"}
    values = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z0-9]{3,18}", str(text or ""))
    result = []
    for value in values:
        if value not in stop_words and value.lower() not in {x.lower() for x in result}: result.append(value)
        if len(result) >= limit: break
    return result
