"""FLIR thermal image API endpoints"""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pathlib import Path
from config import PHOTO_SHARE_PATH

router = APIRouter(prefix="/api/photos", tags=["flir"])


def _resolve_photo_path(path: str) -> Path:
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
    return photo_path


@router.get("/flir_visual")
async def get_flir_visual(path: str):
    photo_path = _resolve_photo_path(path)
    from flir_parser import parse_flir
    flir = parse_flir(photo_path)
    if not flir or not flir.get('visual_jpeg'):
        raise HTTPException(status_code=404, detail="No FLIR visual image found")
    return Response(content=flir['visual_jpeg'], media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/flir_thermal")
async def get_flir_thermal(path: str):
    photo_path = _resolve_photo_path(path)
    return FileResponse(str(photo_path), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/flir_thermal_src")
async def get_flir_thermal_src(path: str, w: int = 640, h: int = 480):
    photo_path = _resolve_photo_path(path)
    try:
        import pyvips
        img = pyvips.Image.new_from_file(str(photo_path))
        if abs(img.width - w) > 5 or abs(img.height - h) > 5:
            img = img.resize(w / img.width, vscale=h / img.height)
        buf = img.jpegsave_buffer(Q=85)
        return Response(content=buf, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    except Exception:
        return FileResponse(str(photo_path), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


def _get_flir_temps(photo_path):
    """Extract RawThermalImage, byte-swap, compute Planck temps.
    Returns (temps_2d, t_min, t_max, meta) or raises HTTPException."""
    from flir_parser import _exiftool_extract
    import cv2, numpy as np, json, re, math, subprocess, io
    from PIL import Image as PILImage

    raw_bytes = _exiftool_extract(photo_path, 'RawThermalImage')
    if not raw_bytes:
        raise HTTPException(status_code=404, detail="No RawThermalImage found")

    buf = io.BytesIO(raw_bytes)
    pil = PILImage.open(buf)
    arr = np.array(pil, dtype=np.uint16)

    fix = lambda x: ((x & 0xff) << 8) | (x >> 8)
    vfix = np.vectorize(fix)
    arr_fixed = vfix(arr).astype(np.float64)

    meta_s = subprocess.check_output([
        'exiftool', str(photo_path), '-j',
        '-Emissivity', '-SubjectDistance', '-AtmosphericTemperature',
        '-ReflectedApparentTemperature', '-IRWindowTemperature', '-IRWindowTransmission',
        '-RelativeHumidity', '-PlanckR1', '-PlanckB', '-PlanckF', '-PlanckO', '-PlanckR2'
    ]).decode()
    meta = json.loads(meta_s)[0]

    def f(s):
        if s is None: return None
        d = re.findall(r"[-+]?\d*\.?\d+", str(s))
        return float(d[0]) if d else None

    E = f(meta.get('Emissivity')) or 0.95
    OD = f(meta.get('SubjectDistance')) or 1.0
    AT = f(meta.get('AtmosphericTemperature')) or 20.0
    RT = f(meta.get('ReflectedApparentTemperature')) or 20.0
    IW = f(meta.get('IRWindowTemperature')) or 20.0
    IRTv = f(meta.get('IRWindowTransmission')) or 1.0
    RH = f(meta.get('RelativeHumidity')) or 50.0
    PR1 = f(meta.get('PlanckR1')) or 21106.77
    PB = f(meta.get('PlanckB')) or 1501.0
    PF = f(meta.get('PlanckF')) or 1.0
    PO = f(meta.get('PlanckO')) or -7340.0
    PR2 = f(meta.get('PlanckR2')) or 0.012545258

    ATA1, ATA2, ATB1, ATB2, ATX = 0.006569, 0.01262, -0.002276, -0.00667, 1.9
    emiss_wind = 1 - IRTv
    h2o = (RH/100)*math.exp(1.5587+0.06939*AT-0.00027816*AT**2+0.00000068455*AT**3)
    sd2 = math.sqrt(OD/2)
    ta = ATX*math.exp(-sd2*(ATA1+ATB1*math.sqrt(h2o)))+(1-ATX)*math.exp(-sd2*(ATA2+ATB2*math.sqrt(h2o)))
    tau1 = tau2 = ta

    rr1 = PR1/(PR2*(math.exp(PB/(RT+273.15))-PF))-PO
    ra1 = PR1/(PR2*(math.exp(PB/(AT+273.15))-PF))-PO
    rw  = PR1/(PR2*(math.exp(PB/(IW+273.15))-PF))-PO
    ra2 = ra1

    denom = E*tau1*IRTv*tau2
    raw_obj = arr_fixed/denom - (1-E)/E*rr1 - (1-tau1)/E/tau1*ra1 - emiss_wind/E/tau1/IRTv*rw - (1-tau2)/E/tau1/IRTv/tau2*ra2
    arg = PR2*(raw_obj+PO)
    arg = np.clip(arg, 0.001, None)
    temps = PB/np.log(PR1/arg+PF)-273.15
    temps = np.where(np.isfinite(temps), temps, np.nan)

    t_mean = float(np.nanmean(temps))
    if t_mean < -50 or t_mean > 150:
        temps = arr_fixed / 1000.0

    t_min, t_max = float(np.nanmin(temps)), float(np.nanmax(temps))
    if t_max <= t_min:
        t_max = t_min + 1.0
    return temps, t_min, t_max


@router.get("/flir_temperature")
async def get_flir_temperature(path: str, x: int = 0, y: int = 0):
    """Temperature at a given pixel in the RawThermalImage."""
    photo_path = _resolve_photo_path(path)
    try:
        temps, _, _ = _get_flir_temps(photo_path)
        h, w = temps.shape
        x = max(0, min(w-1, x))
        y = max(0, min(h-1, y))
        t = float(temps[y, x])
        return {"x": x, "y": y, "temp_c": round(t, 1)}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Temperature probe failed: {e}\n{traceback.format_exc()}")


@router.get("/flir_raw_palette")
async def get_flir_raw_palette(path: str):
    """Render RawThermalImage with byte-swap + Planck + camera palette."""
    photo_path = _resolve_photo_path(path)
    from flir_parser import _exiftool_extract
    try:
        import cv2, numpy as np
        from PIL import Image as PILImage
        import io

        temps, t_min, t_max = _get_flir_temps(photo_path)

        pal_bin = _exiftool_extract(photo_path, 'Palette')
        if pal_bin and len(pal_bin) >= 672:
            pal_ycc = np.frombuffer(pal_bin, dtype=np.uint8)[:672].reshape(-1, 3)
            y = pal_ycc[:, 0].astype(np.float32)/255.0
            cb = (pal_ycc[:, 1].astype(np.float32)-128.0)/255.0
            cr = (pal_ycc[:, 2].astype(np.float32)-128.0)/255.0
            r = np.clip((y+1.402*cr)*255, 0, 255).astype(np.uint8)
            g = np.clip((y-0.344136*cb-0.714136*cr)*255, 0, 255).astype(np.uint8)
            b = np.clip((y+1.772*cb)*255, 0, 255).astype(np.uint8)
            pal_rgb = np.stack([r, g, b], axis=1)
            pal_rgb = pal_rgb[::-1]
            n_colors = len(pal_rgb)
        else:
            pal_rgb = None

        if pal_rgb is not None:
            norm = np.clip((temps - t_min)/(t_max - t_min), 0, 1)*(n_colors-1)
            idx_low = np.floor(norm).astype(np.int32)
            idx_high = np.minimum(idx_low + 1, n_colors - 1)
            frac = norm - idx_low.astype(np.float32)
            r = (pal_rgb[idx_low,0].astype(np.float32)*(1-frac)+pal_rgb[idx_high,0].astype(np.float32)*frac).clip(0,255).astype(np.uint8)
            g = (pal_rgb[idx_low,1].astype(np.float32)*(1-frac)+pal_rgb[idx_high,1].astype(np.float32)*frac).clip(0,255).astype(np.uint8)
            b = (pal_rgb[idx_low,2].astype(np.float32)*(1-frac)+pal_rgb[idx_high,2].astype(np.float32)*frac).clip(0,255).astype(np.uint8)
            color = np.stack([r, g, b], axis=2)
        else:
            norm = np.clip((temps - t_min)/(t_max - t_min)*255, 0, 255).astype(np.uint8)
            color = cv2.cvtColor(cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO), cv2.COLOR_BGR2RGB)

        out_bytes = io.BytesIO()
        PILImage.fromarray(color).save(out_bytes, format='JPEG', quality=90)
        return Response(content=out_bytes.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Raw thermal failed: {e}\n{traceback.format_exc()}")


@router.get("/flir_overlay")
async def get_flir_overlay(path: str, alpha: float = 0.5):
    if alpha < 0.1:
        alpha = 0.1
    if alpha > 0.9:
        alpha = 0.9
    photo_path = _resolve_photo_path(path)
    from flir_parser import parse_flir, create_overlay
    flir = parse_flir(photo_path)
    if not flir or not flir.get('visual_jpeg'):
        raise HTTPException(status_code=404, detail="No FLIR visual image found")
    overlay = create_overlay(flir['visual_jpeg'], photo_path, alignment=flir.get('alignment'), alpha=alpha)
    if not overlay:
        raise HTTPException(status_code=500, detail="Failed to create overlay")
    return Response(content=overlay, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/flir_info")
async def get_flir_info(path: str):
    photo_path = _resolve_photo_path(path)
    from flir_parser import parse_flir
    flir = parse_flir(photo_path)
    if not flir:
        return {"is_flir": False}
    return {
        "is_flir": flir['is_flir'],
        "has_visual": flir.get('visual_jpeg') is not None,
        "alignment": flir.get('alignment'),
        "planck_params": flir.get('planck_params'),
    }
