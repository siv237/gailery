"""albums.py — API endpoints for photo albums (auto-generated + manual)."""

import re
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

from api.photos import _enrich_photo
from api.validators import json_body
from database import get_db

router = APIRouter(prefix="/api/albums", tags=["albums"])

GAP_HOURS = 2
MIN_PHOTOS = 5
JUNK_DIR_THRESHOLD = 50

_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]
_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг",
             "пятница", "суббота", "воскресенье"]


def _clean_dir_name(d, junk_dirs):
    """Извлечь осмысленное имя из пути папки, убрав даты и мусор."""
    if not d or d == "." or d in junk_dirs:
        return None
    parts = d.replace("\\", "/").split("/")
    if any(p in junk_dirs for p in parts):
        return None
    meaningful = []
    for p in parts:
        if re.match(r"^\d{4}$", p):
            continue
        if re.match(r"^\d{1,2}$", p):
            continue
        if re.match(r"^\d{4}[-._]\d{1,2}[-._]\d{1,2}", p):
            continue
        if re.match(r"^\d{1,2}[-._]\d{1,2}$", p):
            continue
        p = re.sub(r"^\d{4}[-._]\d{1,2}[-._]\d{1,2}\s*[-—.:]*\s*", "", p)
        p = re.sub(r"^\d{4}[-._]\d{1,2}\s*[-—.:]*\s*", "", p)
        p = re.sub(r"^\d{1,2}[-._]\d{1,2}\s*[-—.:]*\s*", "", p)
        p = re.sub(r"^\d{1,2}\s+", "", p)
        p = re.sub(r"^\d{1,2}\s*[-—.]+\s*", "", p)
        p = p.strip(" -_.")
        if p:
            meaningful.append(p)
    return " ".join(meaningful) if meaningful else None


def _date_title(dt):
    """Форматировать дату как '18 мая 2012 года (пятница)'."""
    return f"{dt.day} {_MONTHS[dt.month - 1]} {dt.year} года ({_WEEKDAYS[dt.weekday()]})"


def _generate_clusters(db):
    """Кластеризация фото по времени (gap ≤ 2ч, ≥ 5 фото).

    Сортировка по date_utc — единое временное пространство для фото и видео.
    У фото date_utc = локальное - EXIF offset, у видео date_utc = UTC.
    Это объединяет видео и фото одной съёмки даже если видео без utc_offset
    (p.date остался UTC, но date_utc корректен).

    Фото с повреждённым временем (00:00:00 — нет реального EXIF) не
    участвуют в кластеризации самостоятельно, а привязываются к ближайшему
    кластеру того же дня.
    """
    rows = db.sqlite.execute(
        "SELECT p.photo_id, COALESCE(p.date_utc, p.manual_date, p.date) as sort_date, "
        "substr(COALESCE(p.manual_date, p.date), 1, 10) as day_str, cf.parent_dir "
        "FROM photos p "
        "JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 "
        "WHERE p.deleted = 0 AND p.date IS NOT NULL "
        "ORDER BY sort_date"
    ).fetchall()

    gap = GAP_HOURS * 3600
    clusters = []
    cur = {"photo_ids": [], "dirs": set(), "start": None, "end": None}
    prev_dt = None
    zero_time_photos = []  # фото с 00:00:00 — привязать потом

    for r in rows:
        date_str = r[1]
        day_str = r[2]
        try:
            dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue

        # Фото с неизвестным временем (00:00:00) — отложить
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            zero_time_photos.append((r[0], day_str, r[3]))
            continue

        if prev_dt and (dt - prev_dt).total_seconds() > gap:
            if len(cur["photo_ids"]) >= MIN_PHOTOS:
                clusters.append(cur)
            cur = {"photo_ids": [], "dirs": set(), "start": None, "end": None}

        if not cur["photo_ids"]:
            cur["start"] = dt
            cur["day"] = day_str
        cur["end"] = dt
        cur["photo_ids"].append(r[0])
        if r[3]:
            cur["dirs"].add(r[3])
        prev_dt = dt

    if len(cur["photo_ids"]) >= MIN_PHOTOS:
        clusters.append(cur)

    # Привязать фото с 00:00:00 к ближайшему кластеру того же дня
    clusters_by_day = {}
    for c in clusters:
        day = c.get("day") or c["start"].strftime("%Y-%m-%d")
        clusters_by_day.setdefault(day, []).append(c)

    leftover_by_day = {}
    for pid, day_str, parent_dir in zero_time_photos:
        if day_str in clusters_by_day:
            target = clusters_by_day[day_str][0]
            target["photo_ids"].append(pid)
            if parent_dir:
                target["dirs"].add(parent_dir)
        else:
            leftover_by_day.setdefault(day_str, []).append((pid, parent_dir))

    # Фото с 00:00:00 в днях без кластеров — образуют свои кластеры
    for day, items in leftover_by_day.items():
        if len(items) >= MIN_PHOTOS:
            clusters.append({
                "photo_ids": [i[0] for i in items],
                "dirs": {i[1] for i in items if i[1]},
                "start": datetime.strptime(day + " 00:00:00", "%Y-%m-%d %H:%M:%S"),
                "end": datetime.strptime(day + " 00:00:00", "%Y-%m-%d %H:%M:%S"),
            })

    # Сортировка по дате начала
    clusters.sort(key=lambda c: c["start"])
    return clusters


def _enrich_album_photos(db, photo_ids, cameras=None):
    """Получить полные фото-объекты (с лицами, персонами, дублями) по списку UUID.

    Если передан cameras (результат _collect_album_cameras), каждому фото
    присваивается cam_idx — индекс его камеры в этом списке (-1 если нет).
    """
    import json as _json
    _fake = re.compile(r'^(h264|h265|hevc|mjpeg|mpeg4|vp[89]|av1|aac|mp4a|pcm|opus|vp9|theora|flac)$', re.I)
    cam_lookup = {}
    if cameras:
        for ci, c in enumerate(cameras):
            key = (c["make"], c["model"], c["serial"])
            cam_lookup[key] = ci
    photos = db.get_photos_by_ids(photo_ids)
    if not photos:
        return []

    hashes = [p.get("content_hash", "") for p in photos if p.get("content_hash")]

    photo_faces = {}
    persona_ids_needed = set()
    if hashes:
        ph = ",".join("?" * len(hashes))
        face_rows = db.sqlite.execute(
            f"SELECT face_id, photo_id, content_hash, persona_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence "
            f"FROM faces WHERE content_hash IN ({ph})",  # nosec B608 — values parameterized through ?
            hashes
        ).fetchall()
        face_cols = ["face_id", "photo_id", "content_hash", "persona_id",
                     "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence"]
        for fr in face_rows:
            fd = dict(zip(face_cols, fr))
            ch = fd.get("content_hash") or ""
            if ch:
                photo_faces.setdefault(ch, []).append(fd)
            if fd.get("persona_id"):
                persona_ids_needed.add(fd["persona_id"])

    persona_map = {}
    if persona_ids_needed:
        pids = list(persona_ids_needed)
        pid_ph = ",".join("?" * len(pids))
        p_rows = db.sqlite.execute(
            f"SELECT persona_id, name, display_name, comment FROM personas WHERE persona_id IN ({pid_ph})",  # nosec B608
            pids
        ).fetchall()
        for pr in p_rows:
            pid = pr[0]
            cnt_row = db.sqlite.execute("SELECT COUNT(*) FROM faces WHERE persona_id = ?", (pid,)).fetchone()
            persona_map[pid] = {
                "persona_id": pid, "name": pr[1], "display_name": pr[2],
                "comment": pr[3], "total_face_count": cnt_row[0] if cnt_row else 0,
            }

    result = []
    for p in photos:
        ep = _enrich_photo(p, photo_faces, persona_map, include_created=True)
        hash_val = ep.get("content_hash")
        try:
            if hash_val:
                ep["duplicate_paths"] = db.get_duplicate_paths(hash_val)
                ep["edits"] = db.get_edits(hash_val)
            else:
                ep["duplicate_paths"] = []
                ep["edits"] = []
        except Exception:
            ep["duplicate_paths"] = []
            ep["edits"] = []
        if cam_lookup:
            mk = (ep.get("camera_make") or "").strip()
            mdl = (ep.get("camera_model") or "").strip()
            if _fake.match(mk):
                mk = ""
            if _fake.match(mdl):
                mdl = ""
            serial = ""
            raw = ep.get("exif_raw")
            if raw:
                try:
                    rd = _json.loads(raw)
                    serial = str(rd.get("EXIF BodySerialNumber", "") or "").strip()
                    if not serial:
                        serial = str(rd.get("EXIF LensSerialNumber", "") or "").strip()
                except (ValueError, TypeError):
                    pass
            ep["cam_idx"] = cam_lookup.get((mk, mdl, serial), -1)
        else:
            ep["cam_idx"] = -1
        result.append(ep)
    return result


def _detect_junk_dirs(clusters):
    """Папки встречающиеся > JUNK_DIR_THRESHOLD раз — мусорные (DCIM, OpenCamera)."""
    dir_freq = Counter()
    for c in clusters:
        for d in c["dirs"]:
            dir_freq[d] += 1
    return {d for d, f in dir_freq.items() if f > JUNK_DIR_THRESHOLD}


_Fake_CAM_RE = re.compile(
    r'^(h264|h265|hevc|mjpeg|mpeg4|vp[89]|av1|aac|mp4a|pcm|opus|vp9|theora|flac)$',
    re.IGNORECASE,
)


def _camera_key(make, model):
    """Нормализованный ключ камеры для группировки."""
    m = (make or '').strip()
    ml = (model or '').strip()
    if _Fake_CAM_RE.match(m):
        m = ''
    if _Fake_CAM_RE.match(ml):
        ml = ''
    if not m and not ml:
        return None
    return (m + ' ' + ml).strip()


def _collect_album_cameras(db, photo_ids):
    """Собрать уникальные камеры альбома.

    Группировка по make+model+serial (серийник разделяет одинаковые модели).
    Возвращает список: [{"make":..., "model":..., "serial":..., "count":N}, ...]
    Сортировка: по убыванию количества фото.
    """
    if not photo_ids:
        return []
    import json as _json
    ph = ",".join("?" * len(photo_ids))
    rows = db.sqlite.execute(
        "SELECT camera_make, camera_model, exif_raw FROM photos "
        "WHERE photo_id IN (" + ph + ")",
        photo_ids
    ).fetchall()
    _fake = re.compile(r'^(h264|h265|hevc|mjpeg|mpeg4|vp[89]|av1|aac|mp4a|pcm|opus|vp9|theora|flac)$', re.I)
    cams = {}
    for make, model, exif_raw in rows:
        m = (make or "").strip()
        mdl = (model or "").strip()
        if _fake.match(m):
            m = ""
        if _fake.match(mdl):
            mdl = ""
        if not m and not mdl:
            continue
        serial = ""
        if exif_raw:
            try:
                raw = _json.loads(exif_raw)
                serial = str(raw.get("EXIF BodySerialNumber", "") or "").strip()
                if not serial:
                    serial = str(raw.get("EXIF LensSerialNumber", "") or "").strip()
            except (ValueError, TypeError):
                pass
        key = (m, mdl, serial)
        if key not in cams:
            cams[key] = {"make": m, "model": mdl, "serial": serial, "count": 0}
        cams[key]["count"] += 1
    result = sorted(cams.values(), key=lambda c: -c["count"])
    return result


def _resolve_photo_uuid(db, photo_id):
    """Резолв photo_id (UUID или rel_path) в UUID photos.photo_id."""
    if not photo_id:
        return None
    row = db.sqlite.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    return row[0] if row else None


def _resolve_photo_by_any(db, ident):
    """Резолв идентификатора в UUID photos.photo_id.

    Принимает: UUID, content_hash (xxh128), или путь.
    Схема: content_hash → catalog_files(abs_path) → photos(path) → photos.photo_id
    """
    if not ident:
        return None
    # 1. Прямой UUID
    row = db.sqlite.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ?", (ident,)
    ).fetchone()
    if row:
        return row[0]
    # 2. Через content_hash → catalog_files → photos
    row = db.sqlite.execute(
        "SELECT p.photo_id FROM photos p "
        "JOIN catalog_files cf ON cf.abs_path = p.path "
        "WHERE cf.content_hash = ? AND cf.is_canonical = 1",
        (ident,)
    ).fetchone()
    if row:
        return row[0]
    # 3. По пути (rel_path или abs_path)
    row = db.sqlite.execute(
        "SELECT photo_id FROM photos WHERE path LIKE ?", ('%' + ident,)
    ).fetchone()
    if row:
        return row[0]
    return None


def _parse_date(s):
    """Парсинг 'YYYY-MM-DD HH:MM:SS' в datetime."""
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _exif_time(exif_raw_str):
    """Извлечь время из EXIF DateTimeOriginal → секунды от полуночи."""
    if not exif_raw_str:
        return None
    try:
        import json as _json
        raw = _json.loads(exif_raw_str)
        for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
            val = raw.get(key)
            if not val:
                continue
            s = str(val).strip()
            if len(s) >= 19 and s[4] == ':':
                s = s[:10].replace(':', '-') + s[10:]
            try:
                dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
                return dt.hour * 3600 + dt.minute * 60 + dt.second
            except ValueError:
                continue
    except (ValueError, TypeError):
        pass
    return None


@router.get("/")
async def list_albums():
    """Список всех альбомов с preview-фото для стопки карточек.

    cover_photo_id — на вершине стопки, остальные 2 — случайные каждый запрос.
    """
    import random as _random
    db = get_db()
    albums = db.get_albums()
    if not albums:
        return []
    album_ids = [a["album_id"] for a in albums]
    ph = ",".join("?" * len(album_ids))
    rows = db.sqlite.execute(
        "SELECT ap.album_id, ap.photo_id FROM album_photos ap "
        "JOIN photos p ON p.photo_id = ap.photo_id "
        "WHERE ap.album_id IN (" + ph + ")",
        album_ids
    ).fetchall()
    all_pids = {}
    for aid, pid in rows:
        all_pids.setdefault(aid, []).append(pid)
    for a in albums:
        ids = all_pids.get(a["album_id"], [])
        cover = a.get("cover_photo_id")
        rest = [i for i in ids if i != cover]
        if len(rest) > 2:
            rest = _random.sample(rest, 2)
        preview = ([cover] if cover else []) + rest
        a["preview_photos"] = preview[:3]
    return albums


@router.get("/by_photo/{photo_id}")
async def find_album_by_photo(photo_id: str):
    """Найти альбом(ы), содержащие фото.

    photo_id может быть UUID, content_hash или путём — резолвим через БД.
    """
    db = get_db()
    uuid = _resolve_photo_by_any(db, photo_id)
    if not uuid:
        raise HTTPException(status_code=404, detail="Photo not found")
    rows = db.sqlite.execute(
        "SELECT a.album_id, a.title, a.description, a.date_start, a.date_end, "
        "a.photo_count, a.source "
        "FROM albums a JOIN album_photos ap ON ap.album_id = a.album_id "
        "WHERE ap.photo_id = ? ORDER BY a.date_start DESC",
        (uuid,)
    ).fetchall()
    if not rows:
        return {"albums": [], "photo_uuid": uuid}
    albums = [dict(zip(
        ["album_id", "title", "description", "date_start", "date_end",
         "photo_count", "source"], r
    )) for r in rows]
    return {"albums": albums, "photo_uuid": uuid}


@router.get("/{album_id}")
async def get_album(album_id: str, full: bool = False):
    """Один альбом. При full=true — photos содержит полные объекты фото."""
    db = get_db()
    album = db.get_album(album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    photo_ids = db.get_album_photos(album_id)
    album["photo_ids"] = photo_ids
    cameras = _collect_album_cameras(db, photo_ids)
    album["cameras"] = cameras
    if full:
        album["photos"] = _enrich_album_photos(db, photo_ids, cameras)
    return album


@router.post("/generate")
async def generate_albums():
    """Авто-генерация альбомов из временных кластеров.

    Очищает существующие auto-альбомы, кластеризует фото по времени
    (gap ≤ 2ч, ≥ 5 фото), создаёт альбомы с авто-названием.
    """
    db = get_db()

    # Сохранить пользовательские правки auto-альбомов
    preserved = []
    for r in db.sqlite.execute(
        "SELECT album_id, title, description FROM albums "
        "WHERE source = 'auto' AND user_modified = 1"
    ).fetchall():
        aid, atitle, adesc = r
        pids = set(db.get_album_photos(aid))
        preserved.append({"title": atitle, "description": adesc, "photo_ids": pids})

    # Очищаем только auto-альбомы
    auto_ids = [r[0] for r in db.sqlite.execute(
        "SELECT album_id FROM albums WHERE source = 'auto'"
    ).fetchall()]
    for aid in auto_ids:
        db.delete_album(aid)

    clusters = _generate_clusters(db)
    junk_dirs = _detect_junk_dirs(clusters)

    created = 0
    for c in clusters:
        new_pids = set(c["photo_ids"])

        best_title = None
        best_desc = None
        best_overlap = 0
        for p in preserved:
            overlap = len(new_pids & p["photo_ids"])
            if overlap > best_overlap and overlap >= len(new_pids) // 2:
                best_overlap = overlap
                best_title = p["title"]
                best_desc = p["description"]

        if best_title:
            title = best_title
        else:
            date_part = _date_title(c["start"])
            named = [n for d in c["dirs"] if (n := _clean_dir_name(d, junk_dirs))]
            if named:
                title = f"{date_part} — {sorted(named, key=len)[0]}"
            else:
                title = date_part

        album_id = db.create_album(
            title=title,
            description=best_desc or "",
            source="auto",
            date_start=c["start"].isoformat(),
            date_end=c["end"].isoformat(),
            photo_ids=c["photo_ids"],
        )
        if best_title:
            db.sqlite.execute(
                "UPDATE albums SET user_modified = 1 WHERE album_id = ?",
                (album_id,)
            )
            db.sqlite.commit()
        created += 1

    return {
        "ok": True, "created": created,
        "junk_dirs": len(junk_dirs), "preserved": len(preserved),
    }


@router.delete("/clear")
async def clear_albums():
    """Удалить все альбомы (для экспериментов/регенерации)."""
    db = get_db()
    db.clear_all_albums()
    return {"ok": True}


@router.post("/{album_id}/photos")
async def add_photos(album_id: str, request: Request):
    """Добавить фото в альбом."""
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")
    body = await json_body(request)
    photo_ids = body.get("photo_ids", [])
    if not isinstance(photo_ids, list):
        photo_ids = []
    db.add_photos_to_album(album_id, photo_ids)
    return {"ok": True, "added": len(photo_ids)}


@router.delete("/{album_id}/photos")
async def remove_photos(album_id: str, request: Request):
    """Удалить фото из альбома."""
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")
    body = await json_body(request)
    photo_ids = body.get("photo_ids", [])
    if not isinstance(photo_ids, list):
        photo_ids = []
    db.remove_photos_from_album(album_id, photo_ids)
    return {"ok": True, "removed": len(photo_ids)}


@router.put("/{album_id}")
async def update_album(album_id: str, request: Request):
    """Обновить название/описание/обложку альбома."""
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")
    body = await json_body(request)
    db.update_album(
        album_id,
        title=body.get("title"),
        description=body.get("description"),
        cover_photo_id=body.get("cover_photo_id"),
    )
    return {"ok": True}


@router.post("/merge")
async def merge_albums(request: Request):
    """Склеить два альбома: фото из source → target, source удаляется."""
    db = get_db()
    body = await json_body(request)
    target_id = body.get("target_id")
    source_id = body.get("source_id")
    new_title = body.get("title")
    if not target_id or not source_id:
        raise HTTPException(status_code=400, detail="target_id and source_id required")
    if not db.get_album(target_id):
        raise HTTPException(status_code=404, detail="Target album not found")
    if not db.get_album(source_id):
        raise HTTPException(status_code=404, detail="Source album not found")
    db.merge_albums(target_id, source_id, new_title)
    return {"ok": True}


@router.delete("/{album_id}")
async def delete_album(album_id: str):
    """Удалить альбом."""
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")
    db.delete_album(album_id)
    return {"ok": True}


# ─── Коррекция времени камеры в альбоме ───────────────────────


@router.get("/{album_id}/camera_group")
async def get_camera_group(album_id: str, photo_id: str):
    """Данные для коррекции времени камеры в альбоме.

    Anchor остаётся на своей позиции (00:00:00 из БД).
    Остальные кадры камеры получают позицию = anchor + (exif_time_кадра - exif_time_anchor).
    Timeline: обычные фото на своей дате, кадры камеры на сдвинутой позиции.
    """
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")

    anchor_uuid = _resolve_photo_uuid(db, photo_id)
    if not anchor_uuid:
        raise HTTPException(status_code=404, detail="Anchor photo not found")

    album_photo_ids = db.get_album_photos(album_id)
    if not album_photo_ids:
        raise HTTPException(status_code=404, detail="Album has no photos")

    ph = ",".join("?" * len(album_photo_ids))
    rows = db.sqlite.execute(
        f"SELECT p.photo_id, p.path, p.date, p.manual_date, p.date_utc, "  # nosec B608
        f"p.camera_make, p.camera_model, p.exif_raw, p.date_tz "
        f"FROM photos p WHERE p.photo_id IN ({ph}) AND p.deleted = 0 "
        f"ORDER BY COALESCE(p.date_utc, p.manual_date, p.date) ASC",
        album_photo_ids
    ).fetchall()

    anchor_row = None
    anchor_cam_key = None
    for r in rows:
        if r[0] == anchor_uuid:
            anchor_row = r
            anchor_cam_key = _camera_key(r[5], r[6])
            break

    if not anchor_row:
        raise HTTPException(status_code=404, detail="Anchor photo not in album")
    if not anchor_cam_key:
        raise HTTPException(status_code=400, detail="Photo has no camera info")

    # EXIF время anchor в секундах от полуночи
    anchor_exif_secs = _exif_time(anchor_row[7]) or 0
    anchor_date_str = anchor_row[2]  # p.date
    anchor_base = _parse_date(anchor_date_str)

    camera_photos = []
    other_count = 0
    timeline = []

    for r in rows:
        pid, path, date, mdate, dutc, cmake, cmodel, exif_raw, date_tz = r
        cam_key = _camera_key(cmake, cmodel)
        is_camera = (cam_key == anchor_cam_key)
        is_anchor = (pid == anchor_uuid)

        if is_camera:
            cam_exif_secs = _exif_time(exif_raw) or 0
            rel_shift = cam_exif_secs - anchor_exif_secs
            if anchor_base:
                positioned = anchor_base + timedelta(seconds=rel_shift)
                display_date = positioned.strftime("%Y-%m-%d %H:%M:%S")
            else:
                display_date = date
            timeline.append({
                "db_id": pid,
                "date": mdate or display_date,
                "original_date": display_date,
                "is_camera": True,
                "is_anchor": is_anchor,
            })
            camera_photos.append({
                "db_id": pid,
                "photo_id": path,
                "date": date,
                "manual_date": mdate,
                "exif_secs": cam_exif_secs,
            })
        else:
            eff_date = mdate or date
            timeline.append({
                "db_id": pid,
                "date": eff_date,
                "original_date": date,
                "is_camera": False,
                "is_anchor": False,
                "date_tz": date_tz or "",
            })
            other_count += 1

    return {
        "camera_name": anchor_cam_key,
        "camera_count": len(camera_photos),
        "other_count": other_count,
        "anchor_uuid": anchor_uuid,
        "anchor_date": anchor_date_str,
        "anchor_exif_secs": anchor_exif_secs,
        "camera_photos": camera_photos,
        "timeline": timeline,
    }


@router.post("/{album_id}/apply_time_shift")
async def apply_time_shift(album_id: str, request: Request):
    """Применить коррекцию: new_anchor_time → manual_date каждому кадру камеры.

    shift = new_anchor_time - anchor.date (00:00:00).
    Для каждого кадра: manual_date = anchor.date + (exif_secs_кадра - anchor_exif_secs) + shift.
    """
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")

    body = await json_body(request)
    anchor_photo_id = body.get("anchor_photo_id")
    new_anchor_time = body.get("new_anchor_time")
    if not anchor_photo_id or not new_anchor_time:
        raise HTTPException(400, "anchor_photo_id and new_anchor_time required")

    anchor_uuid = _resolve_photo_uuid(db, anchor_photo_id)
    if not anchor_uuid:
        raise HTTPException(status_code=404, detail="Anchor photo not found")

    anchor_row = db.sqlite.execute(
        "SELECT date, camera_make, camera_model, exif_raw FROM photos WHERE photo_id = ?",
        (anchor_uuid,)
    ).fetchone()
    if not anchor_row:
        raise HTTPException(status_code=404, detail="Anchor photo not in DB")

    a_date_str, cmake, cmodel, a_exif = anchor_row
    cam_key = _camera_key(cmake, cmodel)
    if not cam_key:
        raise HTTPException(400, "Anchor photo has no camera info")

    anchor_base = _parse_date(a_date_str)
    anchor_exif_secs = _exif_time(a_exif) or 0
    target = _parse_date(new_anchor_time)
    if not anchor_base or not target:
        raise HTTPException(400, "Cannot parse dates")

    # Сдвиг: пользователь задаёт правильное время anchor (на позиции 00:00:00)
    user_shift = target - anchor_base

    album_photo_ids = db.get_album_photos(album_id)
    ph = ",".join("?" * len(album_photo_ids))
    rows = db.sqlite.execute(
        f"SELECT photo_id, date, date_utc, camera_make, camera_model, exif_raw "  # nosec B608
        f"FROM photos WHERE photo_id IN ({ph}) AND deleted = 0",
        album_photo_ids
    ).fetchall()

    count = 0
    for r in rows:
        pid, date_str, dutc_str, rmake, rmodel, exif_raw = r
        if _camera_key(rmake, rmodel) != cam_key:
            continue
        cam_exif_secs = _exif_time(exif_raw) or 0
        rel_shift = cam_exif_secs - anchor_exif_secs
        new_md = (anchor_base + timedelta(seconds=rel_shift) + user_shift)
        new_md_str = new_md.strftime("%Y-%m-%d %H:%M:%S")
        db.sqlite.execute(
            "UPDATE photos SET manual_date = ?, date_utc = NULL WHERE photo_id = ?",
            (new_md_str, pid)
        )
        count += 1

    if not count:
        raise HTTPException(400, "No camera photos found in album")

    db.sqlite.commit()
    return {"ok": True, "updated": count, "shift_seconds": user_shift.total_seconds()}


@router.post("/{album_id}/save_manual_dates")
async def save_manual_dates(album_id: str, request: Request):
    """Сохранить manual_date для списка фото.

    Body: {updates: [{photo_id, manual_date}, ...], tz_offset: minutes}
    Записывает manual_date, вычисляет date_utc из tz_offset, ставит date_tz='local'.
    """
    db = get_db()
    if not db.get_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found")

    body = await json_body(request)
    updates = body.get("updates")
    if not updates or not isinstance(updates, list):
        raise HTTPException(status_code=400, detail="updates required")

    tz_offset = body.get("tz_offset", 0)
    try:
        tz_offset = int(tz_offset)
    except (ValueError, TypeError):
        tz_offset = 0

    count = 0
    for u in updates:
        pid = u.get("photo_id")
        md = u.get("manual_date")
        if not pid or not md:
            continue
        date_utc = None
        try:
            dt_local = datetime.strptime(md[:19], "%Y-%m-%d %H:%M:%S")
            dt_utc = dt_local - timedelta(minutes=tz_offset)
            date_utc = dt_utc.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass
        db.sqlite.execute(
            "UPDATE photos SET manual_date = ?, date_utc = ?, date_tz = 'local' WHERE photo_id = ?",
            (md, date_utc, pid)
        )
        count += 1

    db.sqlite.commit()
    return {"ok": True, "updated": count}
