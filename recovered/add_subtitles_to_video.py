"""Recovered styled subtitle renderer backed by FFmpeg/libass."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


DEFAULT_SUBTITLE_STYLE_PRESET = "classic_white"
SUBTITLE_STYLE_PRESETS = {
    "classic_white": {"font_color": "#FFFFFF", "outline_color": "#000000", "highlight_color": "#FFD43B",
                      "font_scale": .052, "margin_v_scale": .075, "outline_width": 3, "shadow_width": 1,
                      "alignment": 2, "bold": True, "max_chars_scale": .034},
    "viral_yellow": {"font_color": "#FFD43B", "outline_color": "#21180A", "highlight_color": "#FF4D4F",
                     "font_scale": .058, "margin_v_scale": .09, "outline_width": 4, "shadow_width": 1,
                     "alignment": 2, "bold": True, "max_chars_scale": .032},
    "bold_black": {"font_color": "#111111", "outline_color": "#F8FFFC", "highlight_color": "#1D4F91",
                   "font_scale": .055, "margin_v_scale": .08, "outline_width": 3, "shadow_width": 0,
                   "alignment": 2, "bold": True, "max_chars_scale": .034},
    "yellow_emphasis": {"font_color": "#FFF8E6", "outline_color": "#3A2200", "highlight_color": "#F0C35A",
                        "font_scale": .055, "margin_v_scale": .08, "outline_width": 3, "shadow_width": 1,
                        "alignment": 2, "bold": True, "max_chars_scale": .034},
}


def _resolve_media_tool(name: str) -> str:
    configured = os.environ.get("FFMPEG_HOME", "").strip()
    if configured:
        base = Path(configured).expanduser()
        candidate = base / name if base.is_dir() else base
        if candidate.is_file() and (candidate.name == name or name == "ffmpeg"):
            return str(candidate)
    found = shutil.which(name) or shutil.which(name + ".exe")
    if not found:
        raise RuntimeError(f"PATH 或 FFMPEG_HOME 中未找到 {name}")
    return found


def _ensure_file(path: Path, description: str) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_file():
        raise FileNotFoundError(f"{description}不存在: {value}")
    return value


def _get_video_resolution(video_path: Path) -> Tuple[int, int]:
    ffprobe = _resolve_media_tool("ffprobe")
    result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height", "-of", "json", str(video_path)],
                            capture_output=True, text=True, check=True)
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise ValueError("视频没有可用画面流")
    return int(streams[0]["width"]), int(streams[0]["height"])


def _normalize_hex_color(color: str) -> str:
    value = str(color or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError(f"无效颜色: {color}")
    return "#" + value.upper()


def _hex_to_ass_color(color: str, alpha: int = 0) -> str:
    value = _normalize_hex_color(color)[1:]
    return f"&H{max(0, min(255, int(alpha))):02X}{value[4:6]}{value[2:4]}{value[0:2]}"


def _hex_to_ass_inline_color(color: str) -> str:
    return _hex_to_ass_color(color)[4:]


def _escape_force_style_value(text: str) -> str:
    return str(text).replace("'", r"\'").replace(",", r"\,")


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _normalize_highlight_words(words: Optional[Iterable[str]]) -> List[str]:
    unique = []
    for word in words or []:
        value = str(word).strip()
        if value and value not in unique:
            unique.append(value)
    return sorted(unique, key=len, reverse=True)


def _srt_time_to_ass(value: str) -> str:
    hours, minutes, rest = value.strip().replace(".", ",").split(":")
    seconds, milliseconds = rest.split(",")
    centiseconds = int(milliseconds.ljust(3, "0")[:3]) // 10
    return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}.{centiseconds:02d}"


def _parse_srt_blocks(content: str) -> List[Tuple[str, str, str]]:
    blocks = []
    for block in re.split(r"\r?\n\s*\r?\n", content.strip()):
        lines = [line.strip("\ufeff\r") for line in block.splitlines()]
        if lines and lines[0].strip().isdigit():
            lines.pop(0)
        if not lines or "-->" not in lines[0]:
            continue
        start, end = (part.strip().split()[0] for part in lines.pop(0).split("-->", 1))
        blocks.append((start, end, r"\N".join(line.strip() for line in lines if line.strip())))
    return blocks


def _escape_ass_text(text: str) -> str:
    return str(text).replace("\\", r"\textbackslash").replace("{", r"\{").replace("}", r"\}")


def _highlight_ass_text(text: str, words: Iterable[str], highlight_color: str,
                        default_color: str) -> str:
    escaped = _escape_ass_text(text)
    normalized = _normalize_highlight_words(words)
    if not normalized:
        return escaped
    pattern = re.compile("|".join(re.escape(_escape_ass_text(word)) for word in normalized), re.I)
    highlight = _hex_to_ass_inline_color(highlight_color)
    default = _hex_to_ass_inline_color(default_color)
    return pattern.sub(lambda match: rf"{{\c&H{highlight}&}}{match.group(0)}{{\c&H{default}&}}", escaped)


def _build_ass_subtitle_file(
    subtitle: Path, *, width: int, height: int, font_name: str, font_color: str,
    outline_color: str, highlight_words: Iterable[str], highlight_color: str,
    font_size: int, margin_v: int, margin_l: int, margin_r: int,
    outline_width: float, shadow_width: float, alignment: int, is_bold: bool,
    animation: Optional[str],
) -> Path:
    style = (f"Style: Default,{font_name},{font_size},{_hex_to_ass_color(font_color)},"
             f"{_hex_to_ass_color(font_color)},{_hex_to_ass_color(outline_color)},&H80000000,"
             f"{-1 if is_bold else 0},0,0,0,100,100,0,0,1,{outline_width},{shadow_width},"
             f"{alignment},{margin_l},{margin_r},{margin_v},1")
    animation_prefix = {"fade": r"{\fad(150,150)}", "pop": r"{\fscx110\fscy110\t(0,120,\fscx100\fscy100)}"}.get(animation, "")
    events = []
    for start, end, text in _parse_srt_blocks(subtitle.read_text(encoding="utf-8-sig")):
        styled = _highlight_ass_text(text, highlight_words, highlight_color, font_color)
        events.append(f"Dialogue: 0,{_srt_time_to_ass(start)},{_srt_time_to_ass(end)},Default,,0,0,0,,{animation_prefix}{styled}")
    event_text = "\n".join(events)
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{event_text}
"""
    handle = tempfile.NamedTemporaryFile("w", suffix=".ass", encoding="utf-8", delete=False)
    with handle:
        handle.write(content)
    return Path(handle.name)


def _wrap_srt_content(content: str, max_chars_per_line: int) -> str:
    output = []
    for start, end, text in _parse_srt_blocks(content):
        plain = text.replace(r"\N", " ")
        wrapped = r"\N".join(textwrap.wrap(plain, width=max(1, max_chars_per_line),
                                             replace_whitespace=False, drop_whitespace=True))
        wrapped_lines = wrapped.replace(r"\N", "\n")
        output.append(f"{len(output)+1}\n{start} --> {end}\n{wrapped_lines}")
    return "\n\n".join(output) + ("\n" if output else "")


def _prepare_subtitle_file(subtitle: Path, max_chars_per_line: int):
    if subtitle.suffix.lower() != ".srt" or not max_chars_per_line:
        return subtitle, None
    handle = tempfile.NamedTemporaryFile("w", suffix=".srt", encoding="utf-8", delete=False)
    temp_path = Path(handle.name)
    with handle:
        handle.write(_wrap_srt_content(subtitle.read_text(encoding="utf-8-sig"), max_chars_per_line))
    return temp_path, temp_path


def _get_style_preset(style_preset: Optional[str]):
    name = style_preset or DEFAULT_SUBTITLE_STYLE_PRESET
    if name not in SUBTITLE_STYLE_PRESETS:
        raise ValueError(f"未知字幕样式: {name}")
    return dict(SUBTITLE_STYLE_PRESETS[name])


def _srt_time_ms(value):
    hours,minutes,rest=str(value).strip().replace(".",",").split(":")
    seconds,millis=rest.split(",")
    return ((int(hours)*60+int(minutes))*60+int(seconds))*1000+int(millis.ljust(3,"0")[:3])


def _portable_font(size, font_name=None, fonts_dir=None):
    from PIL import ImageFont
    candidates=[]
    if fonts_dir:
        root=Path(fonts_dir)
        candidates.extend(root.glob("*.ttf"));candidates.extend(root.glob("*.otf"));candidates.extend(root.glob("*.ttc"))
    candidates.extend((Path("/System/Library/Fonts/PingFang.ttc"),Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                       Path("C:/Windows/Fonts/msyh.ttc")))
    for path in candidates:
        try:
            if Path(path).is_file():return ImageFont.truetype(str(path),int(size))
        except OSError:continue
    try:return ImageFont.truetype("DejaVuSans.ttf",int(size))
    except OSError:return ImageFont.load_default()


def _burn_subtitles_portable(video, subtitle, output, *, font_name, font_color, outline_color,
                             highlight_words, highlight_color, font_size, margin_v,
                             max_chars_per_line, animation, fonts_dir):
    """Portable fallback for FFmpeg builds compiled without libass."""
    import cv2
    import numpy as np
    from PIL import Image,ImageDraw
    events=[(_srt_time_ms(start),_srt_time_ms(end),text.replace(r"\N"," "))
            for start,end,text in _parse_srt_blocks(Path(subtitle).read_text(encoding="utf-8-sig"))]
    capture=cv2.VideoCapture(str(video))
    if not capture.isOpened():raise RuntimeError(f"无法打开视频: {video}")
    fps=float(capture.get(cv2.CAP_PROP_FPS) or 25);width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fd,temp_name=tempfile.mkstemp(suffix=".mp4");os.close(fd);temporary=Path(temp_name)
    writer=cv2.VideoWriter(str(temporary),cv2.VideoWriter_fourcc(*"mp4v"),fps,(width,height))
    font=_portable_font(font_size,font_name,fonts_dir);fill=_normalize_hex_color(font_color);stroke=_normalize_hex_color(outline_color)
    highlight=_normalize_hex_color(highlight_color);words=_normalize_highlight_words(highlight_words);frame_index=0
    try:
        while True:
            ok,frame=capture.read()
            if not ok:break
            current_ms=round(frame_index/fps*1000);frame_index+=1
            event=next(((start,end,text) for start,end,text in events if start<=current_ms<end),None)
            if event:
                start,end,text=event;lines=textwrap.wrap(text,width=max(1,int(max_chars_per_line))) or [text]
                image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).convert("RGBA");layer=Image.new("RGBA",image.size,(0,0,0,0));draw=ImageDraw.Draw(layer)
                alpha=255
                if animation=="fade":alpha=max(0,min(255,round(min((current_ms-start)/150,(end-current_ms)/150,1)*255)))
                y=height-int(margin_v)-sum((draw.textbbox((0,0),line,font=font,stroke_width=2)[3] for line in lines))
                for line in lines:
                    box=draw.textbbox((0,0),line,font=font,stroke_width=2);line_width=box[2]-box[0];x=(width-line_width)//2
                    draw.text((x,y),line,font=font,fill=fill+f"{alpha:02X}",stroke_width=2,stroke_fill=stroke+f"{alpha:02X}")
                    for word in words:
                        match=re.search(re.escape(word),line,re.I)
                        if match:
                            prefix=line[:match.start()];px=draw.textlength(prefix,font=font)
                            draw.text((x+px,y),match.group(0),font=font,fill=highlight+f"{alpha:02X}",stroke_width=2,stroke_fill=stroke+f"{alpha:02X}")
                    y+=box[3]-box[1]+4
                frame=cv2.cvtColor(np.asarray(Image.alpha_composite(image,layer).convert("RGB")),cv2.COLOR_RGB2BGR)
            writer.write(frame)
    finally:capture.release();writer.release()
    ffmpeg=_resolve_media_tool("ffmpeg")
    try:
        result=subprocess.run([ffmpeg,"-y","-i",str(temporary),"-i",str(video),"-map","0:v:0","-map","1:a:0?",
                               "-c:v","libx264","-pix_fmt","yuv420p","-c:a","copy","-shortest",str(output)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError("ffmpeg 合并字幕视频失败: "+result.stderr[-2000:])
        return str(output)
    finally:temporary.unlink(missing_ok=True)


def add_subtitles_to_video(
    video_path, subtitle_path, *, style_preset=DEFAULT_SUBTITLE_STYLE_PRESET,
    font_name=None, font_color=None, outline_color=None, font_size=None,
    margin_v=None, margin_l=None, margin_r=None, max_chars_per_line=None,
    highlight_words=None, highlight_color=None, animation=None, fonts_dir=None,
    output_path=None,
) -> str:
    video = _ensure_file(Path(video_path), "视频文件")
    subtitle = _ensure_file(Path(subtitle_path), "字幕文件")
    ffmpeg = _resolve_media_tool("ffmpeg")
    width, height = _get_video_resolution(video)
    preset = _get_style_preset(style_preset)
    resolved_font_name = font_name or "Microsoft YaHei"
    resolved_font_color = font_color or preset["font_color"]
    resolved_outline_color = outline_color or preset["outline_color"]
    resolved_highlight_color = highlight_color or preset["highlight_color"]
    font_size = int(font_size or max(18, height * preset["font_scale"]))
    margin_v = int(margin_v if margin_v is not None else height * preset["margin_v_scale"])
    margin_l, margin_r = int(margin_l or width * .04), int(margin_r or width * .04)
    max_chars_per_line = int(max_chars_per_line or max(8, width * preset["max_chars_scale"]))
    processed, temp_subtitle = _prepare_subtitle_file(subtitle, max_chars_per_line)
    temp_ass = None
    try:
        use_ass = bool(highlight_words or animation)
        if use_ass:
            processed = temp_ass = _build_ass_subtitle_file(
                processed, width=width, height=height, font_name=resolved_font_name,
                font_color=resolved_font_color, outline_color=resolved_outline_color,
                highlight_words=highlight_words or [], highlight_color=resolved_highlight_color,
                font_size=font_size, margin_v=margin_v, margin_l=margin_l, margin_r=margin_r,
                outline_width=preset["outline_width"], shadow_width=preset["shadow_width"],
                alignment=preset["alignment"], is_bold=preset["bold"], animation=animation,
            )
            subtitle_filter = f"ass=filename='{_escape_filter_path(processed)}'"
        else:
            fields = [f"FontName={_escape_force_style_value(resolved_font_name)}", f"Fontsize={font_size}",
                      f"PrimaryColour={_hex_to_ass_color(resolved_font_color)}",
                      f"OutlineColour={_hex_to_ass_color(resolved_outline_color)}", "BorderStyle=1",
                      f"Outline={preset['outline_width']}", f"Shadow={preset['shadow_width']}",
                      f"Alignment={preset['alignment']}", f"MarginL={margin_l}", f"MarginR={margin_r}",
                      f"MarginV={margin_v}", f"Bold={-1 if preset['bold'] else 0}"]
            subtitle_filter = (f"subtitles=filename='{_escape_filter_path(processed)}'"
                               f":force_style='{','.join(fields)}'")
        if fonts_dir:
            subtitle_filter += f":fontsdir='{_escape_filter_path(Path(fonts_dir))}'"
        output = Path(output_path) if output_path else video.with_name(video.stem + "_with_subtitles" + video.suffix)
        result = subprocess.run([ffmpeg, "-y", "-i", str(video), "-vf", subtitle_filter,
                                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                                 "-c:a", "copy", str(output)], capture_output=True, text=True)
        if result.returncode:
            if "No such filter: 'subtitles'" in result.stderr or "No such filter: 'ass'" in result.stderr:
                return _burn_subtitles_portable(
                    video,subtitle,output,font_name=resolved_font_name,font_color=resolved_font_color,
                    outline_color=resolved_outline_color,highlight_words=highlight_words or [],
                    highlight_color=resolved_highlight_color,font_size=font_size,margin_v=margin_v,
                    max_chars_per_line=max_chars_per_line,animation=animation,fonts_dir=fonts_dir,
                )
            raise RuntimeError("ffmpeg 添加字幕失败: " + result.stderr[-2000:])
        return str(output)
    finally:
        for path in (temp_ass, temp_subtitle):
            if path and Path(path).is_file():
                Path(path).unlink()
