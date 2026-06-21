"""API endpoints for video streaming"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pathlib import Path
import logging
import re
import subprocess
from config import PHOTO_SHARE_PATH, VIDEO_EXTS
import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["video"])

STREAM_VIDEO_EXTS = VIDEO_EXTS

_video_codec_cache = {}


def _video_needs_stream(p):
    if p.get("media_type") != "video":
        return False
    video_path = p.get("path", "")
    if not video_path or not Path(video_path).exists():
        ext = Path(video_path).suffix.lower() if video_path else ""
        return ext in STREAM_VIDEO_EXTS
    ch = p.get("content_hash") or video_path
    if ch in _video_codec_cache:
        return _video_codec_cache[ch]
    vc, ac, _ = _probe_video_codecs(Path(video_path))
    needs = not (vc in ("h264",) and ac in ("aac", "mp4a"))
    _video_codec_cache[ch] = needs
    return needs


def _resolve_photo_path(path: str):
    from database import get_db
    db = get_db()
    row = db.sqlite.execute("SELECT path FROM photos WHERE photo_id = ?", (path,)).fetchone()
    if row:
        return Path(row[0])
    row2 = db.sqlite.execute("SELECT cf.abs_path FROM catalog_files cf WHERE cf.content_hash = ?", (path,)).fetchone()
    if row2:
        return Path(row2[0])
    return PHOTO_SHARE_PATH / path


def _probe_video_codecs(input_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-hide_banner", "-loglevel", "error",
             "-show_entries", "stream=codec_type,codec_name,pix_fmt",
             "-print_format", "json", str(input_path)],
            capture_output=True, timeout=10
        )
        import json
        info = json.loads(result.stdout)
        video_codec = None
        audio_codec = None
        pix_fmt = None
        for s in info.get("streams", []):
            if s.get("codec_type") == "video" and not video_codec:
                video_codec = s.get("codec_name")
                pix_fmt = s.get("pix_fmt")
            elif s.get("codec_type") == "audio" and not audio_codec:
                audio_codec = s.get("codec_name")
        return video_codec, audio_codec, pix_fmt
    except Exception:
        return None, None, None


def _start_ffmpeg_transcode(input_path, seek_time=0):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if seek_time > 0:
        cmd.extend(["-ss", f"{seek_time:.3f}"])
    cmd.extend([
        "-i", str(input_path),
        "-err_detect", "ignore_err",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ])
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _start_ffmpeg_audio_transcode(input_path, seek_time=0):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if seek_time > 0:
        cmd.extend(["-ss", f"{seek_time:.3f}"])
    cmd.extend([
        "-i", str(input_path),
        "-err_detect", "ignore_err",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ])
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _start_ffmpeg_remux(input_path, seek_time=0):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if seek_time > 0:
        cmd.extend(["-ss", f"{seek_time:.3f}"])
    cmd.extend([
        "-i", str(input_path),
        "-err_detect", "ignore_err",
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ])
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _stream_ffmpeg(process):
    try:
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=3)
        except Exception:
            pass


def _estimate_transcode_size(duration, width, height):
    pixels = (width or 640) * (height or 480)
    if pixels <= 640 * 480:
        vbr = 2_800_000
    elif pixels <= 1280 * 720:
        vbr = 4_500_000
    elif pixels <= 1920 * 1080:
        vbr = 7_000_000
    else:
        vbr = 10_000_000
    abr = 128_000
    return int((vbr + abr) * max(duration, 1) / 8)


@router.get("/video_stream")
async def video_stream(path: str = "", t: float = 0, request: Request = None):
    photo_path = _resolve_photo_path(path)
    if not photo_path.exists() or not photo_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    video_codec, audio_codec, pix_fmt = _probe_video_codecs(photo_path)

    h264_ok = video_codec in ("h264",)
    aac_ok = audio_codec in ("aac", "mp4a")
    yuv420p_ok = pix_fmt in ("yuv420p", "yuvj420p")

    if h264_ok and aac_ok:
        strategy = "remux"
    elif h264_ok and yuv420p_ok:
        strategy = "audio_transcode"
    else:
        strategy = "transcode"

    from database import get_db
    db = get_db()
    photo = db.get_photo_by_path(str(photo_path))
    if not photo:
        row = db.sqlite.execute(
            "SELECT duration_seconds, img_width, img_height FROM photos WHERE path = ?",
            (str(photo_path),)
        ).fetchone()
        if row:
            duration, width, height = row[0] or 30, row[1] or 640, row[2] or 480
        else:
            duration, width, height = 30, 640, 480
    else:
        duration = photo.get("duration_seconds", 30) or 30
        width = photo.get("img_width", 640) or 640
        height = photo.get("img_height", 480) or 480

    MAX_TRANSCODE_SIZE = 500 * 1024 * 1024
    estimated_size = _estimate_transcode_size(duration, width, height)
    if strategy == "transcode" and estimated_size > MAX_TRANSCODE_SIZE:
        raise HTTPException(status_code=413, detail=f"Video too large to transcode on-the-fly ({estimated_size // 1024 // 1024}MB estimated)")

    seek_time = max(0, min(t, duration - 0.5))

    def start_ffmpeg(seek):
        if strategy == "remux":
            return _start_ffmpeg_remux(photo_path, seek)
        elif strategy == "audio_transcode":
            return _start_ffmpeg_audio_transcode(photo_path, seek)
        else:
            return _start_ffmpeg_transcode(photo_path, seek)

    range_header = request.headers.get("range", "") if request else ""
    if range_header and strategy == "remux":
        m = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if m:
            start_byte = int(m.group(1))
        else:
            start_byte = 0

        if estimated_size > 0 and start_byte > 0:
            seek_time = max(0, min((start_byte / estimated_size) * duration, duration - 0.5))

        process = start_ffmpeg(seek_time)
        return StreamingResponse(
            _stream_ffmpeg(process),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start_byte}-*/*",
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
            }
        )

    process = start_ffmpeg(seek_time)
    return StreamingResponse(
        _stream_ffmpeg(process),
        status_code=200,
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
        }
    )


@router.get("/video_meta")
async def video_meta(path: str = ""):
    photo_path = _resolve_photo_path(path)
    if not photo_path.exists() or not photo_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    import json as _json
    try:
        result = subprocess.run(
            ["ffprobe", "-hide_banner", "-loglevel", "error",
             "-show_format", "-show_streams",
             "-print_format", "json", str(photo_path)],
            capture_output=True, timeout=10
        )
        info = _json.loads(result.stdout)
    except Exception as e:
        logger.error(f"ffprobe failed for {photo_path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to probe video")

    meta = {
        "duration": 0,
        "creation_time": None,
        "camera": None,
        "video_codec": None,
        "audio_codec": None,
        "width": None,
        "height": None,
        "fps": None,
        "pix_fmt": None,
        "bit_rate": None,
        "audio_sample_rate": None,
        "audio_channels": None,
        "container": None,
    }

    fmt = info.get("format", {})
    if fmt.get("duration"):
        meta["duration"] = float(fmt["duration"])
    if fmt.get("bit_rate"):
        meta["bit_rate"] = int(fmt["bit_rate"])
    tags = fmt.get("tags", {})
    if tags.get("creation_time"):
        meta["creation_time"] = tags["creation_time"]
    qt_model = tags.get("com.apple.quicktime.model")
    qt_make = tags.get("com.apple.quicktime.make")
    if qt_model:
        meta["camera"] = (qt_make + " " + qt_model).strip() if qt_make and qt_make not in qt_model else qt_model
    elif tags.get("comment") and "camera" in tags["comment"].lower():
        meta["camera"] = tags["comment"]
    elif tags.get("software"):
        meta["camera"] = tags["software"]
    if fmt.get("format_name"):
        meta["container"] = fmt["format_name"]

    for s in info.get("streams", []):
        ct = s.get("codec_type")
        if ct == "video" and not meta["video_codec"]:
            meta["video_codec"] = s.get("codec_name")
            meta["width"] = s.get("width")
            meta["height"] = s.get("height")
            meta["pix_fmt"] = s.get("pix_fmt")
            rfr = s.get("r_frame_rate", "0/0")
            if "/" in str(rfr):
                num, den = str(rfr).split("/")
                den = int(den) if int(den) else 1
                meta["fps"] = round(int(num) / den, 2)
        elif ct == "audio" and not meta["audio_codec"]:
            meta["audio_codec"] = s.get("codec_name")
            meta["audio_sample_rate"] = s.get("sample_rate")
            meta["audio_channels"] = s.get("channels")

    all_tags = {}
    for k, v in tags.items():
        all_tags[k] = v
    for s in info.get("streams", []):
        st = s.get("tags", {})
        for k, v in st.items():
            if k not in all_tags:
                all_tags[k] = v
    meta["tags"] = all_tags

    return meta
