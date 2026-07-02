#!/usr/bin/env python3
"""video_metadata.py — извлечение метаданных видео через ffprobe."""

import json
import os
import subprocess


def _ffprobe(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def extract_metadata(path):
    data = _ffprobe(path)
    if not data:
        return None

    fmt = data.get("format", {})
    dur_s = float(fmt.get("duration", 0)) if fmt.get("duration") else 0

    width, height = 0, 0
    codec = ""
    has_audio = False

    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not codec:
            width = int(s.get("width", 0) or 0)
            height = int(s.get("height", 0) or 0)
            codec = s.get("codec_name", "")
        if s.get("codec_type") == "audio":
            has_audio = True

    tags = fmt.get("tags", {})
    creation_time = tags.get("creation_time") or tags.get("date") or ""

    return {
        "duration_seconds": round(dur_s, 1),
        "width": width,
        "height": height,
        "codec": codec,
        "has_audio": has_audio,
        "creation_time": creation_time,
        "size_bytes": os.path.getsize(path),
    }


def extract_video_date(path_str):
    meta = extract_metadata(path_str)
    if not meta:
        return None
    ct = meta.get("creation_time", "")
    if not ct:
        return None
    import re
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', ct)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})', ct)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    m = re.match(r'(\d{4}).(\d{2}).(\d{2})\s+(\d{2}).(\d{2}).(\d{2})', ct)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    return ct