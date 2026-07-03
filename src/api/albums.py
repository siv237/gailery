"""albums.py — API endpoints for photo albums (auto-generated + manual)."""

import re
from collections import Counter
from datetime import datetime

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


def _enrich_album_photos(db, photo_ids):
    """Получить полные фото-объекты (с лицами, персонами, дублями) по списку UUID."""
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
        result.append(ep)
    return result


def _detect_junk_dirs(clusters):
    """Папки встречающиеся > JUNK_DIR_THRESHOLD раз — мусорные (DCIM, OpenCamera)."""
    dir_freq = Counter()
    for c in clusters:
        for d in c["dirs"]:
            dir_freq[d] += 1
    return {d for d, f in dir_freq.items() if f > JUNK_DIR_THRESHOLD}


@router.get("/")
async def list_albums():
    """Список всех альбомов."""
    db = get_db()
    return db.get_albums()


@router.get("/{album_id}")
async def get_album(album_id: str, full: bool = False):
    """Один альбом. При full=true — photos содержит полные объекты фото."""
    db = get_db()
    album = db.get_album(album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    photo_ids = db.get_album_photos(album_id)
    album["photo_ids"] = photo_ids
    if full:
        album["photos"] = _enrich_album_photos(db, photo_ids)
    return album


@router.post("/generate")
async def generate_albums():
    """Авто-генерация альбомов из временных кластеров.

    Очищает существующие auto-альбомы, кластеризует фото по времени
    (gap ≤ 2ч, ≥ 5 фото), создаёт альбомы с авто-названием.
    """
    db = get_db()

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
        date_part = _date_title(c["start"])
        named = [n for d in c["dirs"] if (n := _clean_dir_name(d, junk_dirs))]
        if named:
            title = f"{date_part} — {sorted(named, key=len)[0]}"
        else:
            title = date_part

        db.create_album(
            title=title,
            source="auto",
            date_start=c["start"].isoformat(),
            date_end=c["end"].isoformat(),
            photo_ids=c["photo_ids"],
        )
        created += 1

    return {"ok": True, "created": created, "junk_dirs": len(junk_dirs)}


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
