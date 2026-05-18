"""Thumbnail generation for photos using pyvips, Pillow fallback for RAW, ffmpeg for video"""

import pyvips
import logging as _logging
_logging.getLogger("pyvips").setLevel(_logging.WARNING)
from pathlib import Path
from typing import Optional, Dict, Tuple
import logging
import subprocess
import tempfile

from config import THUMBNAILS_DIR, PHOTO_SHARE_PATH, VIDEO_EXTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SIZES = {
    "sm": 400,
    "md": 800,
    "lg": 1200,
}

FORMATS = ["webp", "jpg"]

RAW_EXTENSIONS = {'.cr2', '.nef', '.arw', '.dng', '.raw', '.rw2', '.orf', '.sr2', '.raf'}


def _is_video(path):
    return Path(path).suffix.lower() in VIDEO_EXTS


def _is_raw(path):
    return Path(path).suffix.lower() in RAW_EXTENSIONS


def _extract_video_frame(video_path, seek_sec=1):
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(seek_sec), "-i", str(video_path),
            "-vframes", "1", "-q:v", "3", "-vf", "scale=iw*sar:ih,setsar=1",
            tmp.name
        ], capture_output=True, timeout=30)
        if Path(tmp.name).exists() and Path(tmp.name).stat().st_size > 0:
            return tmp.name
        Path(tmp.name).unlink(missing_ok=True)
        return None
    except Exception:
        return None


def _rawpy_open(image_path):
    try:
        import rawpy
        raw = rawpy.imread(str(image_path))
        rgb = raw.postprocess(use_camera_wb=True, half_size=True)
        raw.close()
        from PIL import Image
        return Image.fromarray(rgb)
    except Exception:
        return None


def _pillow_generate_to_buffer(image_path, width, fmt="webp", quality=80, crop="centre"):
    from PIL import Image, ImageOps
    try:
        if _is_raw(image_path):
            img = _rawpy_open(image_path)
            if img is None:
                img = Image.open(str(image_path))
        else:
            img = Image.open(str(image_path))
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if _is_raw(image_path):
            img = ImageOps.autocontrast(img, cutoff=1, preserve_tone=True)
        ow, oh = img.size
        if crop == "centre":
            scale = width / min(ow, oh)
            nw, nh = int(ow * scale), int(oh * scale)
            img = img.resize((nw, nh), Image.LANCZOS)
            left = (nw - width) // 2
            top = (nh - width) // 2
            img = img.crop((left, top, left + width, top + width))
        else:
            scale = width / max(ow, oh)
            nw, nh = int(ow * scale), int(oh * scale)
            img = img.resize((nw, nh), Image.LANCZOS)
        import io
        buf = io.BytesIO()
        if fmt == "jpg":
            img.save(buf, format="JPEG", quality=quality)
        else:
            img.save(buf, format="WEBP", quality=quality)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Pillow fallback failed for {image_path}: {e}")
        return None


def _pillow_generate_files(image_path, rel, output_dir, sizes, fmts):
    from PIL import Image, ImageOps
    try:
        if _is_raw(image_path):
            img = _rawpy_open(image_path)
            if img is None:
                img = Image.open(str(image_path))
        else:
            img = Image.open(str(image_path))
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if _is_raw(image_path):
            img = ImageOps.autocontrast(img, cutoff=1, preserve_tone=True)
    except Exception as e:
        logger.error(f"Cannot open {image_path}: {e}")
        return None

    last_path = None
    for sname, width in sizes.items():
        ow, oh = img.size
        scale = width / min(ow, oh)
        nw, nh = int(ow * scale), int(oh * scale)
        thumb = img.resize((nw, nh), Image.LANCZOS)
        left = (nw - width) // 2
        top = (nh - width) // 2
        thumb = thumb.crop((left, top, left + width, top + width))
        p = Path(rel)
        for f in fmts:
            out = output_dir / f"{sname}" / p.with_suffix(f".{f}")
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                last_path = out
                continue
            try:
                if f == "jpg":
                    thumb.save(str(out), format="JPEG", quality=80)
                else:
                    thumb.save(str(out), format="WEBP", quality=80)
                last_path = out
            except Exception as e:
                logger.error(f"Pillow failed to save {out}: {e}")
    return last_path


def _video_generate_files(video_path, rel, output_dir, sizes_to_gen, fmts_to_gen):
    frame_path = _extract_video_frame(video_path)
    if not frame_path:
        logger.error(f"Failed to extract frame from {video_path}")
        return None

    last_path = None
    try:
        img = pyvips.Image.new_from_file(frame_path, access="random")
        for sname, width in sizes_to_gen.items():
            try:
                thumb = img.thumbnail_image(width, crop="centre")
            except Exception:
                continue
            for f in fmts_to_gen:
                out = output_dir / f"{sname}" / Path(rel).with_suffix(f".{f}")
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if f == "jpg":
                        thumb.write_to_file(str(out), Q=80)
                    else:
                        thumb.write_to_file(str(out), Q=80)
                    last_path = out
                except Exception as e:
                    logger.error(f"Failed to save video thumb {out}: {e}")
    finally:
        Path(frame_path).unlink(missing_ok=True)

    return last_path


def _video_generate_to_buffer(video_path, width, fmt="webp", quality=80):
    frame_path = _extract_video_frame(video_path)
    if not frame_path:
        return None
    try:
        img = pyvips.Image.new_from_file(frame_path, access="random")
        thumb = img.thumbnail_image(width, crop="centre")
        ext = f".{fmt}"
        return thumb.write_to_buffer(ext, Q=quality)
    except Exception as e:
        logger.error(f"Failed to generate video thumb buffer: {e}")
        return None
    finally:
        Path(frame_path).unlink(missing_ok=True)


class ThumbnailGenerator:
    """Generate thumbnails using pyvips (libvips)"""

    def __init__(self, output_dir: Path = None, sizes: Dict[str, int] = None):
        self.output_dir = output_dir or THUMBNAILS_DIR
        self.sizes = sizes or SIZES

    def _thumb_path(self, rel_path: str, size_name: str, fmt: str) -> Path:
        p = Path(rel_path)
        return self.output_dir / f"{size_name}" / p.with_suffix(f".{fmt}")

    def generate(self, image_path: Path, size_name: str = None, fmt: str = None) -> Optional[Path]:
        if not image_path.exists():
            logger.warning(f"Image does not exist: {image_path}")
            return None

        try:
            rel = str(image_path.relative_to(PHOTO_SHARE_PATH))
        except ValueError:
            rel = image_path.name

        sizes_to_gen = {size_name: self.sizes[size_name]} if size_name else self.sizes
        fmts_to_gen = [fmt] if fmt else FORMATS

        if _is_video(image_path):
            return _video_generate_files(image_path, rel, self.output_dir, sizes_to_gen, fmts_to_gen)

        if _is_raw(image_path):
            logger.info(f"RAW {image_path.name}, using rawpy+Pillow")
            return _pillow_generate_files(image_path, rel, self.output_dir, sizes_to_gen, fmts_to_gen)

        try:
            img = pyvips.Image.new_from_file(str(image_path), access="random")
        except Exception as e:
            logger.error(f"Failed to load {image_path}: {e}")
            return None

        last_path = None
        for sname, width in sizes_to_gen.items():
            try:
                thumb = img.thumbnail_image(width, crop="centre")
            except Exception as e:
                logger.error(f"Failed to resize {image_path} to {width}: {e}")
                continue

            for f in fmts_to_gen:
                out = self._thumb_path(rel, sname, f)
                out.parent.mkdir(parents=True, exist_ok=True)
                if out.exists():
                    last_path = out
                    continue
                try:
                    if f == "jpg":
                        thumb.write_to_file(str(out), Q=80)
                    else:
                        thumb.write_to_file(str(out), Q=80)
                    last_path = out
                except Exception as e:
                    logger.error(f"Failed to save {out}: {e}")

        return last_path

    def generate_to_buffer(self, image_path: Path, width: int, fmt: str = "webp", quality: int = 80) -> Optional[bytes]:
        if not image_path.exists():
            return None
        if _is_video(image_path):
            return _video_generate_to_buffer(image_path, width, fmt, quality)
        if _is_raw(image_path):
            return _pillow_generate_to_buffer(image_path, width, fmt, quality, crop="centre")
        try:
            img = pyvips.Image.new_from_file(str(image_path), access="random")
            thumb = img.thumbnail_image(width, crop="centre")
            ext = f".{fmt}"
            return thumb.write_to_buffer(ext, Q=quality)
        except Exception as e:
            logger.error(f"Failed to generate buffer for {image_path}: {e}")
            return None

    def generate_fit_buffer(self, image_path: Path, width: int = 400, quality: int = 80) -> Optional[bytes]:
        if not image_path.exists():
            return None
        if _is_video(image_path):
            return _video_generate_to_buffer(image_path, width, "webp", quality)
        if _is_raw(image_path):
            return _pillow_generate_to_buffer(image_path, width, "webp", quality, crop="none")
        try:
            img = pyvips.Image.new_from_file(str(image_path), access="random")
            thumb = img.thumbnail_image(width, crop="none")
            return thumb.write_to_buffer(".webp", Q=quality)
        except Exception as e:
            logger.error(f"Failed to generate fit buffer for {image_path}: {e}")
            return None

    def exists(self, image_path: Path, size_name: str = "sm", fmt: str = "webp") -> bool:
        try:
            rel = str(image_path.relative_to(PHOTO_SHARE_PATH))
        except ValueError:
            rel = image_path.name
        return self._thumb_path(rel, size_name, fmt).exists()

    def get_thumbnail_path(self, image_path: Path, size_name: str = "sm", fmt: str = "webp") -> Path:
        try:
            rel = str(image_path.relative_to(PHOTO_SHARE_PATH))
        except ValueError:
            rel = image_path.name
        return self._thumb_path(rel, size_name, fmt)

    def needs_regeneration(self, image_path: Path, size_name: str = "sm", fmt: str = "webp") -> bool:
        thumb = self.get_thumbnail_path(image_path, size_name, fmt)
        if not thumb.exists():
            return True
        try:
            if image_path.stat().st_mtime > thumb.stat().st_mtime:
                return True
        except OSError:
            return True
        return False


def generate_batch(photo_paths, sizes=None, fmt=None, workers=4):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import time

    gen = ThumbnailGenerator(sizes=sizes)
    t0 = time.time()
    done = 0
    failed = 0

    def _gen(path_str):
        p = Path(path_str)
        result = gen.generate(p, fmt=fmt)
        return result is not None

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_gen, str(p)): p for p in photo_paths}
        for future in as_completed(futures):
            if future.result():
                done += 1
            else:
                failed += 1
            total = done + failed
            if total % 500 == 0:
                elapsed = time.time() - t0
                rate = total / max(elapsed, 1)
                print(f"  [{total}/{len(photo_paths)}] {done} ok, {failed} fail, {rate:.0f}/s")

    elapsed = time.time() - t0
    print(f"Done: {done} generated, {failed} failed in {elapsed:.1f}s ({done/max(elapsed,1):.0f}/s)")
    return done, failed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch thumbnail generation")
    parser.add_argument("--all", action="store_true", help="Generate for all photos in DB")
    parser.add_argument("--missing", action="true", help="Generate only missing thumbnails")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of photos")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--size", type=str, default=None, help="Size name (sm/md/lg)")
    parser.add_argument("--format", type=str, default=None, help="Format (webp/jpg)")
    args = parser.parse_args()

    from database import DatabaseManager
    db = DatabaseManager()
    rows = db.sqlite.execute("SELECT path FROM photos ORDER BY path").fetchall()
    paths = [Path(r[0]) for r in rows if r[0] and Path(r[0]).exists()]

    if args.limit > 0:
        paths = paths[:args.limit]

    sizes = {args.size: SIZES[args.size]} if args.size else None
    fmt = args.format or None

    print(f"Generating thumbnails for {len(paths)} photos (workers={args.workers})")
    generate_batch(paths, sizes=sizes, fmt=fmt, workers=args.workers)


if __name__ == "__main__":
    main()
