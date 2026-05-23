"""FLIR thermal image parser.

FLIR radiometric JPEG contains:
- Outer JPEG = thermal image with palette (ironbow etc.)
- EmbeddedImage (exiftool tag) = real visible-light color photo (JPEG, same resolution)
- RawThermalImage = raw 16-bit thermal sensor data (PNG, 640x480 grayscale)

We use exiftool to extract EmbeddedImage and metadata.
"""

import subprocess
import struct
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_flir_file(file_path: str | Path) -> bool:
    try:
        file_path = Path(file_path)
        with open(file_path, 'rb') as f:
            content = f.read(min(65536, file_path.stat().st_size))
        pos = 2
        while pos < len(content) - 4:
            if content[pos] != 0xFF:
                pos += 1
                continue
            marker = content[pos + 1]
            if marker in (0xDA, 0xD9):
                break
            if 0xD0 <= marker <= 0xD7 or marker == 0x00:
                pos += 2
                continue
            if pos + 4 > len(content):
                break
            length = min(struct.unpack('>H', content[pos + 2:pos + 4])[0], len(content) - pos - 2)
            data = content[pos + 4:pos + 2 + length]
            if marker == 0xE1 and data[:4] == b'Exif':
                return b'FLIR' in data
            pos += 2 + length
    except Exception:
        pass
    return False


def _exiftool_extract(file_path: Path, tag: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            ['exiftool', f'-{tag}', '-b', str(file_path)],
            capture_output=True, timeout=30
        )
        if result.returncode == 0 and len(result.stdout) > 100:
            return result.stdout
    except Exception as e:
        logger.warning(f"exiftool {tag} failed: {e}")
    return None


def _exiftool_text(file_path: Path, tag: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ['exiftool', f'-{tag}', '-s3', str(file_path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _exiftool_float(file_path: Path, tag: str) -> Optional[float]:
    val = _exiftool_text(file_path, tag)
    if val:
        try:
            return float(val.replace(' C', '').replace(' m', '').replace(' %', '').replace(' deg', ''))
        except ValueError:
            pass
    return None


def _exiftool_planck(file_path: Path) -> Optional[dict]:
    tags = [
        ('emissivity', 'Emissivity'),
        ('object_distance', 'ObjectDistance'),
        ('reflected_temp', 'ReflectedApparentTemperature'),
        ('atmospheric_temp', 'AtmosphericTemperature'),
        ('ir_window_temp', 'IRWindowTemperature'),
        ('ir_window_transmission', 'IRWindowTransmission'),
        ('humidity', 'RelativeHumidity'),
        ('planck_r1', 'PlanckR1'),
        ('planck_b', 'PlanckB'),
        ('planck_f', 'PlanckF'),
        ('planck_o', 'PlanckO'),
        ('planck_r2', 'PlanckR2'),
    ]
    params = {}
    for key, tag in tags:
        val = _exiftool_float(file_path, tag)
        if val is not None:
            params[key] = val
    return params if params else None


def _exiftool_alignment(file_path: Path) -> Optional[dict]:
    real2ir = _exiftool_float(file_path, 'Real2IR')
    if real2ir is None or real2ir == 0:
        return None
    offset_x = _exiftool_float(file_path, 'OffsetX')
    offset_y = _exiftool_float(file_path, 'OffsetY')
    ir_w = _exiftool_float(file_path, 'RawThermalImageWidth') or 640
    ir_h = _exiftool_float(file_path, 'RawThermalImageHeight') or 480
    return {
        'real2ir': real2ir,
        'offset_x': offset_x or 0,
        'offset_y': offset_y or 0,
        'ir_width': int(ir_w),
        'ir_height': int(ir_h),
    }


def parse_flir(file_path: str | Path) -> Optional[dict]:
    file_path = Path(file_path)
    if not file_path.exists():
        return None

    visual_jpeg = _exiftool_extract(file_path, 'EmbeddedImage')
    if not visual_jpeg:
        return None

    planck_params = _exiftool_planck(file_path)
    alignment = _exiftool_alignment(file_path)

    return {
        'is_flir': True,
        'visual_jpeg': visual_jpeg,
        'planck_params': planck_params,
        'alignment': alignment,
    }


def parse_alignment(file_path: str | Path) -> dict:
    """Parse FLIR EXIF for orientation and alignment data."""
    file_path = Path(file_path)
    r = subprocess.run(["exiftool",
        "-EmbeddedImageWidth", "-EmbeddedImageHeight",
        "-RawThermalImageWidth", "-RawThermalImageHeight",
        "-f", str(file_path)], capture_output=True, text=True, timeout=15)
    eiw = eih = rtw = rth = None
    for l in r.stdout.split('\n'):
        if 'Embedded Image Width' in l: eiw = int(l.split(':')[-1].strip())
        if 'Embedded Image Height' in l: eih = int(l.split(':')[-1].strip())
        if 'Raw Thermal Image Width' in l: rtw = int(l.split(':')[-1].strip())
        if 'Raw Thermal Image Height' in l: rth = int(l.split(':')[-1].strip())
    orient = "LAND" if eiw and eih and eiw > eih else "PORT"
    return {
        'orient': orient,
        'vis_w': eiw or 1440,
        'vis_h': eih or 1080,
        'ir_w': rtw or 640,
        'ir_h': rth or 480,
    }


def create_overlay(visual_jpeg: bytes, thermal_path: str | Path,
                   alignment: Optional[dict] = None,
                   alpha: float = 0.5) -> Optional[bytes]:
    try:
        import pyvips
    except ImportError:
        logger.error("pyvips required for overlay creation")
        return None

    try:
        visual = pyvips.Image.new_from_buffer(visual_jpeg, '')
        thermal = pyvips.Image.new_from_file(str(thermal_path))

        if visual.bands < 3:
            visual = visual.colourspace('srgb')
        if visual.bands == 4:
            visual = visual.extract_band(0, n=3)
        if thermal.bands == 4:
            thermal = thermal.extract_band(0, n=3)

        vis_w, vis_h = visual.width, visual.height

        cfg = parse_alignment(thermal_path) if not alignment else {
            'orient': 'LAND' if vis_w > vis_h else 'PORT',
            'vis_w': vis_w, 'vis_h': vis_h,
            'ir_w': alignment.get('ir_width', 640),
            'ir_h': alignment.get('ir_height', 480),
        }

        scale = 1.5
        ir_w, ir_h = cfg['ir_w'], cfg['ir_h']

        outer_w, outer_h = thermal.width, thermal.height
        same_as_vis = abs(outer_w - vis_w) < 20 and abs(outer_h - vis_h) < 20

        if same_as_vis:
            th_scaled = thermal.resize(vis_w / outer_w, vscale=vis_h / outer_h)
            th_canvas = th_scaled
        else:
            tw = int(ir_w * scale)
            th = int(ir_h * scale)
            if cfg['orient'] == 'LAND' and vis_w == 1440 and vis_h == 1080:
                m_x, m_y = 219, 141
            else:
                m_x = int((vis_w - tw) / 2)
                m_y = int((vis_h - th) / 2)

            th_scaled = thermal.resize(tw / outer_w, vscale=th / outer_h)
            th_canvas = pyvips.Image.black(vis_w, vis_h, bands=3)
            th_canvas = th_canvas.insert(th_scaled, m_x, m_y, expand=False)

        vis_f = visual.cast('float')
        th_f = th_canvas.cast('float')
        mask_f = (th_canvas.extract_band(0).add(
            th_canvas.extract_band(1)).add(
            th_canvas.extract_band(2)) > 0).cast('float').divide(255.0)
        diff = th_f.subtract(vis_f)
        result = vis_f.add(diff.multiply(mask_f).multiply(alpha)).cast('uchar')

        buf = result.jpegsave_buffer(Q=85)
        return buf
    except Exception as e:
        logger.error(f"Failed to create overlay: {e}")
        return None
