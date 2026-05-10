"""API endpoints for photos"""

from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import StreamingResponse

from pathlib import Path
from typing import Optional, List
import logging
import os
import re
import subprocess
import time
import threading
from config import PHOTO_SHARE_PATH, THUMBNAILS_DIR, LLAMA_CPP_DIR, PROJECT_ROOT, LOG_FILE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

STREAM_VIDEO_EXTS = {'.avi', '.3gp', '.wmv', '.mpg', '.mpeg', '.flv', '.m4v', '.mov', '.mkv'}

FOTO_PREFIX = str(PHOTO_SHARE_PATH) + "/"


def _rel_path(abs_path):
    if abs_path and abs_path.startswith(FOTO_PREFIX):
        return abs_path[len(FOTO_PREFIX):]
    return abs_path or ""


def _enrich_photo(p, photo_faces, persona_map, include_created=False, include_thumbnail=False, include_score=False, score=None):
    rel = _rel_path(p.get("path", ""))
    content_hash = p.get("content_hash", "")
    faces = photo_faces.get(content_hash, []) if content_hash else []
    if not faces:
        faces = photo_faces.get(rel, [])
        if not faces:
            abs_path = p.get("path", "")
            if abs_path:
                for prefix in ["/mnt/share/Foto/", "/opt/gailray/photos/"]:
                    if abs_path.startswith(prefix):
                        rel2 = abs_path[len(prefix):]
                        faces = photo_faces.get(rel2, [])
                        if faces:
                            break
    personas_info = []
    seen_pids = set()
    faces_info = []
    for f in faces:
        pers_id = f.get("persona_id")
        faces_info.append({
            "face_id": f.get("face_id"),
            "persona_id": pers_id,
            "display_name": (persona_map.get(pers_id, {}).get("display_name")) if pers_id else None,
            "name": (persona_map.get(pers_id, {}).get("name") or pers_id) if pers_id else None,
            "bbox_x1": f.get("bbox_x1"),
            "bbox_y1": f.get("bbox_y1"),
            "bbox_x2": f.get("bbox_x2"),
            "bbox_y2": f.get("bbox_y2"),
        })
        if pers_id and pers_id not in seen_pids:
            seen_pids.add(pers_id)
            persona = persona_map.get(pers_id, {})
            personas_info.append({
                "persona_id": pers_id,
                "name": persona.get("name") or pers_id,
                "display_name": persona.get("display_name"),
                "face_count": sum(1 for ff in faces if ff.get("persona_id") == pers_id),
                "total_face_count": persona.get("total_face_count", 0),
                "face_ids": [ff["face_id"] for ff in faces if ff.get("persona_id") == pers_id],
            })
    is_raw = Path(p.get("path", "")).suffix.lower() in {'.cr2', '.nef', '.arw', '.dng', '.raw', '.rw2', '.orf', '.sr2', '.raf'}
    result = {
        "path": p.get("path", ""),
        "photo_id": rel,
        "db_id": p.get("photo_id"),
        "description": p.get("description"),
        "rich_description": p.get("rich_description"),
        "faces_present": bool(p.get("faces_present")),
        "date": p.get("manual_date") or p.get("date"),
        "original_date": p.get("date"),
        "manual_date": p.get("manual_date"),
        "gps_lat": p.get("gps_lat"),
        "gps_lon": p.get("gps_lon"),
        "manual_gps": bool(p.get("manual_gps")),
        "camera_make": p.get("camera_make"),
        "camera_model": p.get("camera_model"),
        "total_faces": len(faces),
        "personas": personas_info,
        "faces": faces_info,
        "img_width": p.get("img_width"),
        "img_height": p.get("img_height"),
        "photo_type": p.get("photo_type", "photo"),
        "has_issues": bool(p.get("has_issues")),
        "issue_type": p.get("issue_type"),
        "deleted": bool(p.get("deleted")),
        "exif_checked": bool(p.get("exif_checked")),
        "embedded": bool(p.get("embedded")),
        "exif_raw": p.get("exif_raw"),
        "is_raw": is_raw,
        "media_type": p.get("media_type", "photo"),
        "duration_seconds": p.get("duration_seconds", 0),
        "needs_stream": p.get("media_type") == "video" and Path(p.get("path", "")).suffix.lower() in STREAM_VIDEO_EXTS,
        "is_canonical": p.get("is_canonical", True),
        "duplicate_paths": p.get("duplicate_paths", []),
        "content_hash": p.get("content_hash"),
    }
    if include_thumbnail:
        result["thumbnail_path"] = p.get("thumbnail_path")
    if include_created:
        result["created_at"] = p.get("created_at")
    if include_score and score is not None:
        result["score"] = round(score, 4)
    return result


@router.get("/")
async def get_photo(path: str):
    photo_path = None
    from database import get_db
    db = get_db()
    row = db.sqlite.execute("SELECT path FROM photos WHERE photo_id = ?", (path,)).fetchone()
    if row:
        photo_path = Path(row[0])
    else:
        row2 = db.sqlite.execute("SELECT cf.abs_path FROM catalog_files cf WHERE cf.content_hash = ?", (path,)).fetchone()
        if row2:
            photo_path = Path(row2[0])
    if not photo_path:
        photo_path = PHOTO_SHARE_PATH / path
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Not a file")
    ext = photo_path.suffix.lower()
    raw_exts = {'.cr2', '.nef', '.arw', '.dng', '.raw', '.rw2', '.orf', '.sr2', '.raf'}
    if ext in raw_exts:
        try:
            from PIL import Image, ImageOps
            from io import BytesIO
            img = None
            try:
                import rawpy
                raw = rawpy.imread(str(photo_path))
                rgb = raw.postprocess(use_camera_wb=True)
                raw.close()
                img = Image.fromarray(rgb)
            except Exception:
                pass
            if img is None:
                img = Image.open(str(photo_path))
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img = ImageOps.autocontrast(img, cutoff=1, preserve_tone=True)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return Response(
                content=buf.getvalue(),
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"}
            )
        except Exception as e:
            logger.error(f"Failed to convert RAW {path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to convert RAW photo")
    content_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".3gp": "video/3gpp",
        ".wmv": "video/x-ms-wmv",
    }.get(ext, "application/octet-stream")
    try:
        with open(photo_path, "rb") as f:
            content = f.read()
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        logger.error(f"Failed to read photo {path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read photo")


@router.get("/thumbnail")
async def get_thumbnail(path: str = "", size: str = "sm", fit: bool = False, abs_path: str = ""):
    photo_path = None
    if abs_path:
        photo_path = Path(abs_path)
    else:
        from database import get_db
        db = get_db()
        row = db.sqlite.execute("SELECT path FROM photos WHERE photo_id = ?", (path,)).fetchone()
        if row:
            photo_path = Path(row[0])
        else:
            row2 = db.sqlite.execute("SELECT cf.abs_path FROM catalog_files cf WHERE cf.content_hash = ?", (path,)).fetchone()
            if row2:
                photo_path = Path(row2[0])
        if not photo_path:
            photo_path = PHOTO_SHARE_PATH / path
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    try:
        rel = str(photo_path.relative_to(PHOTO_SHARE_PATH))
    except ValueError:
        rel = photo_path.name

    from thumbnails import ThumbnailGenerator, SIZES
    gen = ThumbnailGenerator()

    if size not in SIZES:
        size = "sm"

    if fit:
        import asyncio
        loop = asyncio.get_event_loop()
        buf = await loop.run_in_executor(None, gen.generate_fit_buffer, photo_path, SIZES.get(size, 400))
        if not buf:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        return Response(
            content=buf,
            media_type="image/webp",
            headers={"Cache-Control": "no-cache"}
        )

    for fmt in ["webp", "jpg"]:
        thumb_path = gen.get_thumbnail_path(photo_path, size, fmt)
        if thumb_path.exists():
            break
    else:
        import asyncio
        loop = asyncio.get_event_loop()
        thumb_path = await loop.run_in_executor(None, gen.generate, photo_path, size, None)
        if not thumb_path:
            raise HTTPException(status_code=404, detail="Thumbnail not found")

    fmt = thumb_path.suffix.lstrip(".")
    media_map = {"webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg"}

    try:
        with open(thumb_path, "rb") as f:
            content = f.read()
        return Response(
            content=content,
            media_type=media_map.get(fmt, "image/webp"),
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        logger.error(f"Failed to read thumbnail {path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read thumbnail")


@router.get("/face/{face_id}")
async def get_face_crop(face_id: str, margin: float = 0.5):
    import asyncio
    from database import get_db

    db = get_db()
    face = db.get_face(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    photo_path = None
    ch_row = db.sqlite.execute("SELECT content_hash FROM faces WHERE face_id = ?", (face_id,)).fetchone()
    if ch_row and ch_row[0]:
        abs_row = db.sqlite.execute("SELECT abs_path FROM catalog_files WHERE content_hash = ? AND is_canonical = 1 AND deleted = 0", (ch_row[0],)).fetchone()
        if abs_row:
            photo_path = Path(abs_row[0])
    if not photo_path or not photo_path.exists():
        photo_path = PHOTO_SHARE_PATH / face.get("photo_id", "")
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    raw_exts = {'.cr2', '.nef', '.arw', '.dng', '.raw', '.rw2', '.orf', '.sr2', '.raf'}
    is_raw = photo_path.suffix.lower() in raw_exts

    bbox = (int(face["bbox_x1"]), int(face["bbox_y1"]), int(face["bbox_x2"]), int(face["bbox_y2"]))

    def _crop():
        if is_raw:
            from PIL import Image, ImageOps
            import io
            img = None
            scale = 0.5
            try:
                import rawpy
                raw = rawpy.imread(str(photo_path))
                rgb = raw.postprocess(use_camera_wb=True, half_size=True)
                raw.close()
                img = Image.fromarray(rgb)
            except Exception:
                scale = 1.0
                pass
            if img is None:
                img = Image.open(str(photo_path))
            img = ImageOps.autocontrast(img, cutoff=1, preserve_tone=True)
            x1, y1, x2, y2 = [int(v * scale) for v in bbox]
            fw, fh = x2 - x1, y2 - y1
            mx, my = int(fw * margin), int(fh * margin)
            ix1, iy1 = max(0, x1 - mx), max(0, y1 - my)
            ix2 = min(img.width, x2 + mx)
            iy2 = min(img.height, y2 + int(fh * margin * 1.5))
            crop = img.crop((ix1, iy1, ix2, iy2))
            max_dim = 200
            if max(crop.size[0], crop.size[1]) > max_dim:
                ratio = max_dim / max(crop.size[0], crop.size[1])
                crop = crop.resize((int(crop.size[0]*ratio), int(crop.size[1]*ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            crop.save(buf, format="WEBP", quality=85)
            return buf.getvalue()
        import pyvips
        img = pyvips.Image.new_from_file(str(photo_path), access="random")
        x1, y1, x2, y2 = bbox
        fw = x2 - x1
        fh = y2 - y1
        mx = int(fw * margin)
        my = int(fh * margin)
        ix1 = max(0, x1 - mx)
        iy1 = max(0, y1 - my)
        ix2 = min(img.width, x2 + mx)
        iy2 = min(img.height, y2 + int(fh * margin * 1.5))
        crop = img.crop(ix1, iy1, ix2 - ix1, iy2 - iy1)
        max_dim = 200
        if max(crop.width, crop.height) > max_dim:
            crop = crop.thumbnail_image(max_dim, crop="none")
        return crop.write_to_buffer(".webp", Q=85)

    try:
        loop = asyncio.get_event_loop()
        buf = await loop.run_in_executor(None, _crop)
        return Response(content=buf, media_type="image/webp",
                        headers={"Cache-Control": "no-cache"})
    except Exception as e:
        logger.error(f"Failed to crop face {face_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to crop face")


@router.get("/face_context/{face_id}")
async def get_face_context(face_id: str, zoom: float = 3.0):
    from database import get_db
    import io

    db = get_db()
    face = db.get_face(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    photo_path = None
    ch_row = db.sqlite.execute("SELECT content_hash FROM faces WHERE face_id = ?", (face_id,)).fetchone()
    if ch_row and ch_row[0]:
        abs_row = db.sqlite.execute("SELECT abs_path FROM catalog_files WHERE content_hash = ? AND is_canonical = 1 AND deleted = 0", (ch_row[0],)).fetchone()
        if abs_row:
            photo_path = Path(abs_row[0])
    if not photo_path or not photo_path.exists():
        photo_path = PHOTO_SHARE_PATH / face.get("photo_id", "")
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    raw_exts = {'.cr2', '.nef', '.arw', '.dng', '.raw', '.rw2', '.orf', '.sr2', '.raf'}
    is_raw = photo_path.suffix.lower() in raw_exts

    bbox_raw = (float(face["bbox_x1"]), float(face["bbox_y1"]), float(face["bbox_x2"]), float(face["bbox_y2"]))

    def _context():
        from PIL import Image as PILImage, ImageDraw, ImageOps
        import io
        if is_raw:
            img = None
            scale = 0.5
            try:
                import rawpy
                raw = rawpy.imread(str(photo_path))
                rgb = raw.postprocess(use_camera_wb=True, half_size=True)
                raw.close()
                img = PILImage.fromarray(rgb)
            except Exception:
                scale = 1.0
            except Exception:
                pass
            if img is None:
                img = PILImage.open(str(photo_path))
            img = ImageOps.autocontrast(img, cutoff=1, preserve_tone=True)
            bbox = tuple(v * scale for v in bbox_raw)
        else:
            import pyvips
            vimg = pyvips.Image.new_from_file(str(photo_path), access="random")
            crop_buf = vimg.write_to_buffer(".png")
            img = PILImage.open(io.BytesIO(crop_buf))
            bbox = bbox_raw
        iw, ih = img.size
        x1, y1, x2, y2 = bbox
        fw, fh = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        vw, vh = fw * zoom, fh * zoom
        vx1 = max(0, int(cx - vw / 2))
        vy1 = max(0, int(cy - vh / 2))
        vx2 = min(iw, int(cx + vw / 2))
        vy2 = min(ih, int(cy + vh / 2))
        pil_crop = img.crop((vx1, vy1, vx2, vy2))
        rx1, ry1 = int(x1 - vx1), int(y1 - vy1)
        rx2, ry2 = int(x2 - vx1), int(y2 - vy1)
        draw = ImageDraw.Draw(pil_crop)
        draw.rectangle([rx1, ry1, rx2, ry2], outline="red", width=3)
        buf = io.BytesIO()
        pil_crop.save(buf, format='JPEG', quality=90)
        return buf.getvalue()

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, _context)
        return Response(content=content, media_type="image/jpeg",
                         headers={"Cache-Control": "no-cache"})
    except Exception as e:
        logger.error(f"Failed to get face context {face_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get face context")


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
    if range_header:
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
            "Accept-Ranges": "bytes",
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


@router.get("/list")
async def list_photos(limit: int = 100, offset: int = 0, sort: str = "changed_desc"):
    from database import get_db
    from datetime import datetime

    db = get_db()

    actual_sort = "created_desc" if sort not in ("changed_desc", "changed_asc") else sort

    if sort == "changed_desc":
        recent_rows = db.sqlite.execute(
            "SELECT p.photo_id, MAX(c.changed_at) as cat FROM changes c "
            "JOIN photos p ON c.photo_id = p.photo_id "
            "GROUP BY p.photo_id ORDER BY cat DESC LIMIT ?",
            (limit,)
        ).fetchall()
        recent_pids = [r[0] for r in recent_rows]
        change_times = {r[0]: r[1] for r in recent_rows}
        photos = []
        for pid in recent_pids:
            row = db.sqlite.execute("SELECT * FROM photos WHERE photo_id=?", (pid,)).fetchone()
            if row:
                cols = [d[0] for d in db.sqlite.execute("SELECT * FROM photos LIMIT 0").description]
                photos.append(dict(zip(cols, row)))
        total = db.count_photos()

    hashes = [p.get("content_hash", "") for p in photos if p.get("content_hash")]
    persona_ids_needed = set()
    photo_faces = {}
    if hashes:
        ph = ",".join("?" * len(hashes))
        face_rows = db.sqlite.execute(
            f"SELECT face_id, photo_id, content_hash, persona_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence FROM faces WHERE content_hash IN ({ph})",
            hashes
        ).fetchall()
        face_cols = ["face_id", "photo_id", "content_hash", "persona_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence"]
        for fr in face_rows:
            fd = dict(zip(face_cols, fr))
            ch = fd.get("content_hash") or ""
            if ch:
                photo_faces.setdefault(ch, []).append(fd)
            pid = fd.get("photo_id", "")
            if pid:
                photo_faces.setdefault(pid, []).append(fd)
            if fd.get("persona_id"):
                persona_ids_needed.add(fd["persona_id"])

    persona_map = {}
    if persona_ids_needed:
        pids = list(persona_ids_needed)
        pid_ph = ",".join("?" * len(pids))
        for pr in db.sqlite.execute(f"SELECT persona_id, name, display_name FROM personas WHERE persona_id IN ({pid_ph})", pids).fetchall():
            persona_map[pr[0]] = {"persona_id": pr[0], "name": pr[1], "display_name": pr[2]}

    last_changes = {}
    if sort == "changed_desc":
        for p in photos:
            last_changes[p.get("path", "")] = change_times.get(p.get("photo_id"))
    else:
        rows = db.sqlite.execute(
            "SELECT photo_id, MAX(changed_at) as cat FROM changes GROUP BY photo_id"
        ).fetchall()
        change_by_pid = {r[0]: r[1] for r in rows}
        pid_to_path = {}
        for r in db.sqlite.execute("SELECT photo_id, path FROM photos").fetchall():
            pid_to_path[r[0]] = r[1]
        for pid, cat in change_by_pid.items():
            path = pid_to_path.get(pid)
            if path:
                last_changes[path] = cat

    enriched = []
    for p in photos:
        ep = _enrich_photo(p, photo_faces, persona_map, include_thumbnail=True)
        ep["changed_at"] = last_changes.get(p.get("path"))
        enriched.append(ep)

    if sort == "changed_desc":
        enriched.sort(key=lambda x: x.get("changed_at") or "", reverse=True)
        enriched = [e for e in enriched if e.get("changed_at")] + [e for e in enriched if not e.get("changed_at")]
    elif sort == "changed_asc":
        enriched.sort(key=lambda x: x.get("changed_at") or "", reverse=False)

    server_time = datetime.now().isoformat()
    return {"total": total, "photos": enriched[:limit], "server_time": server_time}


@router.get("/description")
async def get_description(path: str):
    from database import get_db

    db = get_db()
    if path.startswith("/"):
        photo = db.get_photo_by_path(path)
    else:
        photo = db.get_photo_by_path(str(PHOTO_SHARE_PATH / path))

    if photo and photo.get("description"):
        return {"path": path, "description": photo["description"]}

    return {"path": path, "description": None}


@router.get("/search")
async def search_photos(
    q: str = "",
    person: str = "",
    date_from: str = "",
    date_to: str = "",
    date_after: str = "",
    date_before: str = "",
    path_after: str = "",
    path_before: str = "",
    has_faces: Optional[bool] = None,
    no_description: Optional[bool] = None,
    has_issues: Optional[bool] = None,
    issue_type: Optional[str] = None,
    photo_type: Optional[str] = None,
    has_gps: Optional[bool] = None,
    no_date: Optional[bool] = None,
    has_description: Optional[bool] = None,
    deleted: Optional[bool] = None,
    deleted_only: Optional[bool] = None,
    file_type: Optional[str] = None,
    media_type: Optional[str] = None,
    sort: str = "date_desc",
    limit: int = 60,
    offset: int = 0,
):
    from database import get_db

    db = get_db()

    _hash_q = None
    _text_q = q or None
    if q and len(q) >= 4 and all(c in '0123456789abcdefABCDEF' for c in q):
        _hash_q = q
        _text_q = None

    total, photos = db.search_photos(
        q=_text_q,
        person=person or None,
        date_from=date_from or None,
        date_to=date_to or None,
        date_after=date_after or None,
        date_before=date_before or None,
        path_after=path_after or None,
        path_before=path_before or None,
        has_faces=has_faces,
        no_description=no_description,
        has_issues=has_issues,
        issue_type=issue_type,
        photo_type=photo_type,
        has_gps=has_gps,
        no_date=no_date,
        has_description=has_description,
        deleted=deleted,
        deleted_only=deleted_only,
        file_type=file_type,
        media_type=media_type,
        content_hash=_hash_q,
        sort=sort,
        limit=limit,
        offset=offset,
    )

    hashes = [p.get("content_hash", "") for p in photos if p.get("content_hash")]
    persona_ids_needed = set()

    photo_faces = {}
    if hashes:
        ph = ",".join("?" * len(hashes))
        face_rows = db.sqlite.execute(
            f"SELECT face_id, photo_id, content_hash, persona_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence FROM faces WHERE content_hash IN ({ph})",
            hashes
        ).fetchall()
        face_cols = ["face_id", "photo_id", "content_hash", "persona_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence"]
        for fr in face_rows:
            fd = dict(zip(face_cols, fr))
            ch = fd.get("content_hash") or ""
            if ch:
                photo_faces.setdefault(ch, []).append(fd)
            pid = fd.get("photo_id", "")
            if pid:
                photo_faces.setdefault(pid, []).append(fd)
            if fd.get("persona_id"):
                persona_ids_needed.add(fd["persona_id"])

    persona_map = {}
    if persona_ids_needed:
        pids = list(persona_ids_needed)
        pid_ph = ",".join("?" * len(pids))
        p_rows = db.sqlite.execute(
            f"SELECT persona_id, name, display_name FROM personas WHERE persona_id IN ({pid_ph})",
            pids
        ).fetchall()
        for pr in p_rows:
            pid = pr[0]
            cnt_row = db.sqlite.execute("SELECT COUNT(*) FROM faces WHERE persona_id = ?", (pid,)).fetchone()
            persona_map[pid] = {"persona_id": pid, "name": pr[1], "display_name": pr[2], "total_face_count": cnt_row[0] if cnt_row else 0}

    result = [_enrich_photo(p, photo_faces, persona_map, include_created=True) for p in photos]

    for p in result:
        abs_path = p.get("path", "")
        hash_val = p.get("content_hash")
        try:
            if hash_val:
                dup_paths = db.get_duplicate_paths(hash_val)
                p["duplicate_paths"] = dup_paths
                p["edits"] = db.get_edits(hash_val)
            else:
                p["duplicate_paths"] = []
                p["edits"] = []
        except Exception:
            p["duplicate_paths"] = []
            p["edits"] = []

    return {"total": total, "photos": result}


def _get_mqtt_api():
    try:
        from mqtt_client import create_api_mqtt
        from main import _get_api_mqtt
        return _get_api_mqtt()
    except Exception:
        return None


_embed_engine = None
_embed_lock = None


def _get_embed_engine():
    global _embed_engine, _embed_lock
    if _embed_lock is None:
        _embed_lock = threading.Lock()
    with _embed_lock:
        if _embed_engine is None:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from embed import EmbedEngine
            import config
            be = config.search_backend or config.OLLAMA_MODE
            _embed_engine = EmbedEngine(backend=be)
            logger.info(f"[SEMSEARCH] EmbedEngine loaded, backend={be}")
        return _embed_engine


def _unload_embed_engine():
    global _embed_engine
    if _embed_engine is not None:
        _embed_engine.cleanup()
        _embed_engine = None
        logger.info("[SEMSEARCH] EmbedEngine unloaded, GPU memory released")


def _embed_query(query_text):
    engine = _get_embed_engine()
    vec = engine.encode_single(query_text)
    return vec.tolist()


@router.get("/semantic_search")
async def semantic_search(q: str = "", limit: int = 20, threshold: float = 1.0):
    from database import get_db

    if not q:
        return {"total": 0, "photos": [], "query": q}

    logger.info(f"[SEMSEARCH] Start: q={q!r} threshold={threshold} limit={limit}")

    db = get_db()

    task = "Retrieve photographs matching the description, including people, places, events, and scenes"
    query_text = "Instruct: " + task + "\nQuery: " + q

    mq = _get_mqtt_api()
    gpu_acquired = False
    gpu_t0 = time.time()
    if mq and _embed_engine is None:
        gpu_acquired = mq.request_gpu_gentle(worker_name="semantic_search", timeout=120)
        if gpu_acquired:
            logger.info(f"[SEMSEARCH] GPU acquired gently in {time.time()-gpu_t0:.1f}s")
        else:
            logger.warning("[SEMSEARCH] GPU busy, search unavailable now")
            return {"total": 0, "photos": [], "query": q, "error": "GPU busy, try again later"}
    else:
        logger.warning("[SEMSEARCH] No MQTT, proceeding without GPU lock")

    q_emb = None
    try:
        q_emb = _embed_query(query_text)
        logger.info(f"[SEMSEARCH] Got embedding size={len(q_emb)}")
    except Exception as e:
        logger.error(f"[SEMSEARCH] Error getting embedding: {e}")
        _unload_embed_engine()
        return {"total": 0, "photos": [], "query": q, "error": str(e)}
    finally:
        if mq and gpu_acquired:
            mq.release_gpu_from_api()
            logger.info("[SEMSEARCH] GPU released via MQTT")

    if q_emb is None:
        logger.error("[SEMSEARCH] No embedding obtained")
        return {"total": 0, "photos": [], "query": q, "error": "no embedding"}

    logger.info(f"[SEMSEARCH] Searching LanceDB with threshold={threshold}")
    try:
        results = db.search_photo_embeddings(q_emb, limit=limit * 2)
    except RuntimeError as e:
        err_msg = str(e)
        logger.error(f"[SEMSEARCH] LanceDB RuntimeError: {err_msg}")
        if "open files" in err_msg.lower() or "Too many" in err_msg:
            try:
                db._open_vector_tables()
                logger.info("[SEMSEARCH] Reopened LanceDB tables after FD exhaustion, retrying search")
                results = db.search_photo_embeddings(q_emb, limit=limit * 2)
            except Exception as e2:
                logger.error(f"[SEMSEARCH] Retry after reopen also failed: {e2}")
                return {"total": 0, "photos": [], "query": q, "error": "LanceDB unavailable (too many open files), please try again"}
        else:
            return {"total": 0, "photos": [], "query": q, "error": f"LanceDB error: {err_msg[:200]}"}
    except Exception as e:
        logger.error(f"[SEMSEARCH] LanceDB error: {e}")
        return {"total": 0, "photos": [], "query": q, "error": str(e)[:200]}
    logger.info(f"[SEMSEARCH] LanceDB returned {len(results)} raw results")
    if results:
        top_dist = results[0].get("_distance", results[0].get("_relevance_score", "?"))
        logger.info(f"[SEMSEARCH] Top distance={top_dist}")

    out_list = []
    seen_pids = set()
    skipped_no_photo = 0
    skipped_not_embedded = 0
    skipped_threshold = 0
    for r in results:
        pid = r.get("photo_id", "")
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        photo = db.get_photo(pid)
        if not photo:
            skipped_no_photo += 1
            continue
        if not photo.get("embedded"):
            skipped_not_embedded += 1
            continue
        score = r.get("_distance", r.get("_relevance_score", 999))
        if score > threshold:
            skipped_threshold += 1
            continue
        out_list.append((photo, score))
        if len(out_list) >= limit:
            break

    hashes = [p.get("content_hash", "") for p, _ in out_list if p.get("content_hash")]
    persona_ids_needed = set()
    photo_faces = {}
    if hashes:
        ph = ",".join("?" * len(hashes))
        face_rows = db.sqlite.execute(
            f"SELECT face_id, photo_id, content_hash, persona_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence FROM faces WHERE content_hash IN ({ph})",
            hashes
        ).fetchall()
        face_cols = ["face_id", "photo_id", "content_hash", "persona_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence"]
        for fr in face_rows:
            fd = dict(zip(face_cols, fr))
            ch = fd.get("content_hash") or ""
            if ch:
                photo_faces.setdefault(ch, []).append(fd)
            pid_legacy = fd.get("photo_id", "")
            if pid_legacy:
                photo_faces.setdefault(pid_legacy, []).append(fd)
            if fd.get("persona_id"):
                persona_ids_needed.add(fd["persona_id"])

    persona_map = {}
    if persona_ids_needed:
        pids = list(persona_ids_needed)
        pid_ph = ",".join("?" * len(pids))
        for pr in db.sqlite.execute(f"SELECT persona_id, name, display_name FROM personas WHERE persona_id IN ({pid_ph})", pids).fetchall():
            persona_map[pr[0]] = {"persona_id": pr[0], "name": pr[1], "display_name": pr[2]}

    enriched_list = []
    for photo, score in out_list:
        ep = _enrich_photo(photo, photo_faces, persona_map, include_created=True, include_score=True, score=score)
        hash_val = db.sqlite.execute(
            "SELECT content_hash FROM catalog_files WHERE abs_path = ? AND content_hash IS NOT NULL",
            (photo.get("path", ""),)
        ).fetchone()
        if hash_val:
            ep["duplicate_paths"] = db.get_duplicate_paths(hash_val[0])
        else:
            ep["duplicate_paths"] = []
        enriched_list.append(ep)

    logger.info(f"[SEMSEARCH] Final: {len(enriched_list)} results (skipped: no_photo={skipped_no_photo}, not_embedded={skipped_not_embedded}, threshold={skipped_threshold})")
    return {"total": len(enriched_list), "photos": enriched_list, "query": q}


@router.post("/{photo_id}/enrich")
async def enrich_description(photo_id: str):
    import subprocess, os
    from database import get_db
    db = get_db()
    photo = db.get_photo(photo_id)
    if not photo:
        photo = db.get_photo_by_path(photo_id)
    if not photo:
        return {"ok": False, "error": "photo not found"}

    path = photo.get("path", "")
    if not path:
        return {"ok": False, "error": "no path"}

    from config import VENV_PYTHON as VENV
    cmd = [VENV, str(PROJECT_ROOT / "enrich_description.py"), "--photo", path]
    env = os.environ.copy()
    _vnvidia = str(PROJECT_ROOT / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
    env["LD_LIBRARY_PATH"] = ":".join([
        _vnvidia + "/cublas/lib",
        _vnvidia + "/cuda_runtime/lib",
        "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
        str(LLAMA_CPP_DIR / "build" / "bin"),
    ])

    mq = _get_mqtt_api()
    if mq:
        mq.request_gpu_for_api(worker_name="enrich")
        logger.info("[ENRICH] GPU acquired via MQTT")
    else:
        logger.warning("[ENRICH] No MQTT, proceeding without GPU lock")
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        db2 = get_db()
        updated = db2.get_photo(photo_id)
        if not updated:
            updated = db2.get_photo_by_path(path)
        rich = updated.get("rich_description") if updated else None
        return {"ok": True, "rich_description": rich}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if mq:
            mq.release_gpu_from_api()
            logger.info("[ENRICH] GPU released via MQTT")


@router.put("/{photo_id}/rich_description")
async def save_rich_description(photo_id: str, request: Request):
    from database import get_db

    body = await request.json()
    rich = body.get("rich_description")

    if rich is None:
        raise HTTPException(status_code=400, detail="rich_description is required")

    db = get_db()
    photo = db.get_photo(photo_id)
    if not photo:
        photo = db.get_photo_by_path(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    db.update_photo(photo["photo_id"], rich_description=rich)
    return {"ok": True, "rich_description": rich}


@router.get("/dates")
async def get_date_histogram():
    import asyncio
    from database import get_db

    db = get_db()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, db.get_date_histogram)


@router.post("/describe")
async def describe_photos(paths: List[str], batch_size: int = 10):
    import subprocess
    import sys

    valid_paths = []
    for p in paths:
        full_path = PHOTO_SHARE_PATH / p
        if full_path.exists():
            valid_paths.append(str(full_path))

    if not valid_paths:
        raise HTTPException(status_code=400, detail="No valid photo paths")

    cmd = [
        sys.executable, str(PROJECT_ROOT / "vision_describe.py"),
        "--single" if len(valid_paths) == 1 else valid_paths[0],
    ]

    return {
        "status": "accepted",
        "count": len(valid_paths),
        "message": f"Use CLI: python {PROJECT_ROOT / 'vision_describe.py'} {PHOTO_SHARE_PATH}/dir --batch-size {batch_size}",
    }


@router.get("/map")
async def get_map_photos():
    try:
        from database import get_db
        db = get_db()
        cur = db.sqlite.cursor()
        rows = cur.execute("""
            SELECT photo_id, path, description, gps_lat, gps_lon, COALESCE(manual_date, date) as date, camera_make, camera_model, img_width, img_height, manual_gps
            FROM photos
            WHERE gps_lat IS NOT NULL AND gps_lon IS NOT NULL
              AND gps_lat != 0 AND gps_lon != 0
              AND deleted = 0
        """).fetchall()
        result = []
        for r in rows:
            abs_path = r[1] or ""
            rel = abs_path[len(FOTO_PREFIX):] if abs_path.startswith(FOTO_PREFIX) else abs_path
            cam_parts = []
            if r[6]: cam_parts.append(r[6])
            if r[7]: cam_parts.append(r[7])
            result.append({
                "photo_id": r[0],
                "path": abs_path,
                "rel_path": rel,
                "description": r[2] or "",
                "lat": r[3],
                "lon": r[4],
                "date": r[5] or "",
                "camera": " ".join(cam_parts) if cam_parts else "",
                "w": r[8],
                "h": r[9],
                "manual_gps": r[10] or 0,
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/neighbor")
async def get_neighbor(date: str, dir: str = "next"):
    from database import get_db

    if dir not in ("next", "prev"):
        raise HTTPException(status_code=400, detail="dir must be next or prev")

    db = get_db()
    cur = db.sqlite.cursor()

    if dir == "next":
        row = cur.execute(
            "SELECT photo_id, path, description, COALESCE(manual_date, date) as effective_date, camera_make, camera_model, gps_lat, gps_lon "
            "FROM photos WHERE COALESCE(manual_date, date) > ? AND deleted = 0 ORDER BY effective_date ASC LIMIT 1",
            (date,)
        ).fetchone()
    else:
        row = cur.execute(
            "SELECT photo_id, path, description, COALESCE(manual_date, date) as effective_date, camera_make, camera_model, gps_lat, gps_lon "
            "FROM photos WHERE COALESCE(manual_date, date) < ? AND deleted = 0 ORDER BY effective_date DESC LIMIT 1",
            (date,)
        ).fetchone()

    if not row:
        return None

    abs_path = row[1] or ""
    rel = abs_path[len(FOTO_PREFIX):] if abs_path.startswith(FOTO_PREFIX) else abs_path
    cam_parts = []
    if row[4]: cam_parts.append(row[4])
    if row[5]: cam_parts.append(row[5])

    return {
        "photo_id": row[0],
        "path": abs_path,
        "rel_path": rel,
        "description": row[2] or "",
        "date": row[3] or "",
        "camera": " ".join(cam_parts) if cam_parts else "",
        "lat": row[6],
        "lon": row[7],
    }


@router.post("/reverse_geocode")
async def reverse_geocode(request: Request):
    import reverse_geocoder
    body = await request.json()
    if isinstance(body, list):
        coords = body
    else:
        coords = body.get("coords", [])
    points = [(c["lat"], c["lon"]) for c in coords]
    results = reverse_geocoder.search(points)
    out = []
    for r in results:
        parts = []
        if r.get("name"):
            parts.append(r["name"])
        if r.get("admin1") and r["admin1"] != r.get("name"):
            parts.append(r["admin1"])
        cc = r.get("cc", "")
        country_map = {
            "RU": "Россия", "UA": "Украина", "BY": "Беларусь", "KZ": "Казахстан",
            "GE": "Грузия", "AM": "Армения", "UZ": "Узбекистан", "KG": "Кыргызстан",
            "TJ": "Таджикистан", "MD": "Молдова", "AZ": "Азербайджан", "TR": "Турция",
            "TH": "Таиланд", "VN": "Вьетнам", "KR": "Корея", "KP": "КНДР",
            "CN": "Китай", "JP": "Япония", "DE": "Германия", "FR": "Франция",
            "IT": "Италия", "ES": "Испания", "GB": "Великобритания", "US": "США",
            "EG": "Египет", "TR": "Турция", "AE": "ОАЭ", "CZ": "Чехия",
            "PL": "Польша", "FI": "Финляндия", "SE": "Швеция", "NO": "Норвегия",
            "ME": "Черногория", "HR": "Хорватия", "RS": "Сербия", "BG": "Болгария",
            "GR": "Греция", "CY": "Кипр", "IL": "Израиль", "IN": "Индия",
            "CU": "Куба", "MX": "Мексика", "BR": "Бразилия", "AU": "Австралия",
        }
        country = country_map.get(cc, cc)
        if country and country != parts[-1] if parts else True:
            parts.append(country)
        out.append(", ".join(parts))
    return out


@router.post("/set_gps")
async def set_gps(request: Request):
    from database import get_db

    body = await request.json()
    photo_id = body.get("photo_id")
    lat = body.get("lat")
    lon = body.get("lon")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat and lon are required")

    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="lat and lon must be valid numbers")

    db = get_db()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET gps_lat = ?, gps_lon = ?, manual_gps = 1 WHERE photo_id = ?",
        (lat, lon, real_id)
    )
    db.sqlite.commit()

    return {"success": True}


@router.post("/set_date")
async def set_date(request: Request):
    from database import get_db

    body = await request.json()
    photo_id = body.get("photo_id")
    manual_date = body.get("manual_date")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")
    if not manual_date:
        raise HTTPException(status_code=400, detail="manual_date is required")

    if len(manual_date) == 10 and manual_date[4] == '-' and manual_date[7] == '-':
        manual_date += " 00:00:00"
    elif len(manual_date) == 16 and manual_date[10] == ' ':
        manual_date += ":00"

    db = get_db()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET manual_date = ? WHERE photo_id = ?",
        (manual_date, real_id)
    )
    db.sqlite.commit()

    return {"success": True, "manual_date": manual_date}


@router.post("/clear_date")
async def clear_date(request: Request):
    from database import get_db

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = get_db()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET manual_date = NULL WHERE photo_id = ?",
        (real_id,)
    )
    db.sqlite.commit()

    return {"success": True}


@router.post("/clear_gps")
async def clear_gps(request: Request):
    from database import get_db

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = get_db()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET gps_lat = NULL, gps_lon = NULL, manual_gps = 0 WHERE photo_id = ?",
        (real_id,)
    )
    db.sqlite.commit()

    return {"success": True}


@router.post("/mark_deleted")
async def mark_deleted(request: Request):
    from database import get_db

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = get_db()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    cur.execute("UPDATE photos SET deleted = 1 WHERE photo_id = ?", (row[0],))
    db.sqlite.commit()

    return {"success": True}


@router.post("/undelete")
async def undelete(request: Request):
    from database import get_db

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = get_db()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    cur.execute("UPDATE photos SET deleted = 0 WHERE photo_id = ?", (row[0],))
    db.sqlite.commit()

    return {"success": True}


@router.get("/edits/{content_hash}")
async def get_edits(content_hash: str):
    from database import get_db
    db = get_db()
    return {"edits": db.get_edits(content_hash), "content_hash": content_hash}


@router.post("/edits/{content_hash}")
async def save_edit(content_hash: str, request: Request):
    from database import get_db
    db = get_db()
    body = await request.json()
    action = body.get("action")
    params = body.get("params", {})
    if not action:
        raise HTTPException(status_code=400, detail="action required")
    if body.get("replace"):
        db.clear_edits(content_hash, action)
    edit_id = db.add_edit(content_hash, action, params)
    return {"ok": True, "edit_id": edit_id}


@router.delete("/edits/{edit_id}")
async def delete_edit(edit_id: int):
    from database import get_db
    db = get_db()
    db.remove_edit(edit_id)
    return {"ok": True}
