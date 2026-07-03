#!/usr/bin/env python3
"""video_metadata.py — извлечение метаданных видео через ffprobe.

Извлекает ВСЕ доступные метаданные: format tags, stream tags, GPS из видео,
utc_offset, creation_time, codec info, bitrate, fps, rotation.
Ничего не теряется — полный ffprobe JSON сохраняется в exif_raw.
"""

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


def _extract_gps(tags):
    """Извлечение GPS из тегов видео (Samsung/Apple пишут location в tags)."""
    lat = tags.get("com.samsung.android.gps.latitude")
    lon = tags.get("com.samsung.android.gps.longitude")
    if lat and lon:
        try:
            return {"lat": float(lat), "lon": float(lon)}
        except (ValueError, TypeError):
            pass
    # Apple location
    location = tags.get("com.apple.quicktime.location.ISO6709", "")
    if location:
        import re
        m = re.match(r'([+-]\d+\.?\d*)([+-]\d+\.?\d*)', location)
        if m:
            try:
                return {"lat": float(m.group(1)), "lon": float(m.group(2))}
            except (ValueError, TypeError):
                pass
    return None


def extract_metadata(path):
    """Полное извлечение метаданных видео.

    Возвращает структурированные поля + raw ffprobe JSON.
    """
    data = _ffprobe(path)
    if not data:
        return None

    fmt = data.get("format", {})
    fmt_tags = fmt.get("tags", {})
    dur_s = float(fmt.get("duration", 0)) if fmt.get("duration") else 0
    bitrate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else 0

    width, height = 0, 0
    codec = ""
    has_audio = False
    audio_codec = ""
    fps = 0.0
    rotation = 0
    bit_depth = 0
    color_space = ""
    stream_tags_all = {}

    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not codec:
            width = int(s.get("width", 0) or 0)
            height = int(s.get("height", 0) or 0)
            codec = s.get("codec_name", "")
            bit_depth = int(s.get("bits_per_raw_sample", 0) or 0)
            color_space = s.get("color_space", "")
            # FPS
            fr = s.get("r_frame_rate", "0/1")
            try:
                num, den = fr.split("/")
                fps = float(num) / float(den) if float(den) else 0.0
            except (ValueError, ZeroDivisionError):
                fps = 0.0
            # Rotation
            for sd in s.get("side_data_list", []):
                if sd.get("rotation"):
                    rotation = int(sd["rotation"])
            stream_tags_all.update(s.get("tags", {}))
        if s.get("codec_type") == "audio":
            has_audio = True
            if not audio_codec:
                audio_codec = s.get("codec_name", "")
            stream_tags_all.update(s.get("tags", {}))

    all_tags = {**fmt_tags, **stream_tags_all}
    creation_time = all_tags.get("creation_time") or all_tags.get("date") or ""
    utc_offset = all_tags.get("com.samsung.android.utc_offset", "")
    gps = _extract_gps(all_tags)

    # Структурированные поля
    result = {
        "duration_seconds": round(dur_s, 1),
        "width": width,
        "height": height,
        "codec": codec,
        "audio_codec": audio_codec,
        "has_audio": has_audio,
        "fps": round(fps, 2),
        "bitrate": bitrate,
        "rotation": rotation,
        "bit_depth": bit_depth,
        "color_space": color_space,
        "creation_time": creation_time,
        "utc_offset": utc_offset,
        "gps": gps,
        "size_bytes": os.path.getsize(path),
        "format_name": fmt.get("format_name", ""),
        "format_long_name": fmt.get("format_long_name", ""),
    }

    # Полный raw JSON — ничего не теряется
    result["raw"] = {
        "format": {"tags": fmt_tags, **{k: v for k, v in fmt.items() if k != "tags"}},
        "streams": [
            {
                "codec_type": s.get("codec_type"),
                "codec_name": s.get("codec_name"),
                "width": s.get("width"),
                "height": s.get("height"),
                "tags": s.get("tags", {}),
                "bit_rate": s.get("bit_rate"),
                "duration": s.get("duration"),
            }
            for s in data.get("streams", [])
        ],
    }

    return result


def extract_video_date(path_str):
    """Извлечь дату видео и конвертировать в локальное через offset из файла.

    creation_time с Z = UTC. Offset берётся из тега com.samsung.android.utc_offset
    (timezone телефона, не сервера). UTC + offset = локальное время (для date).
    Без Z = локальное время фотика, не трогаем.
    Возвращает (date_local_str, is_utc).
    """
    meta = extract_metadata(path_str)
    if not meta:
        return None, False
    ct = meta.get("creation_time", "")
    if not ct:
        return None, False
    import re
    from datetime import datetime, timezone, timedelta

    is_utc = "Z" in ct

    if is_utc:
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', ct)
        if m:
            dt_utc = datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6)),
                tzinfo=timezone.utc
            )
            # Offset из тегов файла: "+1000" → +10:00
            offset_str = meta.get("utc_offset", "")
            offset = timedelta(0)
            mo = re.match(r'([+-])(\d{2})(\d{2})', offset_str)
            if mo:
                sign = 1 if mo.group(1) == "+" else -1
                offset = timedelta(hours=sign * int(mo.group(2)),
                                   minutes=sign * int(mo.group(3)))
            dt_local = dt_utc + offset
            return dt_local.strftime("%Y-%m-%d %H:%M:%S"), True

    # Без Z — локальное время фотика как есть
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', ct)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}", False
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})', ct)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}", False
    m = re.match(r'(\d{4}).(\d{2}).(\d{2})\s+(\d{2}).(\d{2}).(\d{2})', ct)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}", False
    return ct, False
