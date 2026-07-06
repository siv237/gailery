"""share.py - Public read-only gallery access with scope-based filtering.

Architecture:
  /s/album/{id}  - set cookie share_scope=album:{id}, redirect to /s/gallery
  /s/photo/{id}  - set cookie share_scope=photo:{id}, redirect to /s/gallery
  /s/gallery     - gallery.html with rewritten paths
  /s/albums      - albums.html with rewritten paths
  /s/map         - map.html with rewritten paths
  /s/persons     - personas.html with rewritten paths
  /s/api/*       - mirrors of /api/* endpoints, filtered by scope
  /s/{static}    - CSS/JS/images with rewritten paths

Scope:
  Cookie share_scope = "album:{album_id}" or "photo:{photo_id}"
  _get_scope_photo_ids() resolves to list of photo_id UUIDs
  All /s/api/* endpoints filter results through scope photo_ids

Security:
  - Only read-only endpoints (GET) - mutations return 403
  - Path traversal blocked - all file access validated through scope
  - No /s/admin, no /s/catalog - nginx returns 404 for these
  - UUID4 IDs are unguessable
"""

import asyncio
import re as _re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from config import PROJECT_ROOT
from database import get_db

router = APIRouter(prefix="/s", tags=["share"])

_WEB = PROJECT_ROOT / "web"

_STATIC_FILES = {
    "shared.css", "shared.js", "viewer.css", "viewer.js",
    "face-modal.css", "face-modal.js", "gallery-common.js",
    "gallery.js", "gallery-detail.js", "gallery-ui.js",
    "favicon-32.png", "favicon.png", "favicon.ico",
    "apple-touch-icon.png",
    "logo-dark.png", "logo-light.png",
}

_MIME = {
    ".css": "text/css", ".js": "application/javascript",
    ".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".html": "text/html", ".json": "application/json",
}

_PAGES = {
    "gallery": "gallery.html",
    "albums": "albums.html",
    "map": "map.html",
    "persons": "personas.html",
}


# ─── Path rewriting ──────────────────────────────────────────

def _rewrite_paths(content: str) -> str:
    """Rewrite all absolute paths for /s/ isolation."""
    for f in _STATIC_FILES:
        content = content.replace(f'"/{f}"', f'"/s/static/{f}"')
        content = _re.sub(r'"/' + _re.escape(f) + r'\?', f'"/s/static/{f}?', content)
    content = content.replace('"/favicon.ico"', '"/s/static/favicon.ico"')
    content = content.replace("var API = '/api'", "var API = '/s/api'")
    content = content.replace('"/api/photos/', '"/s/api/photos/')
    content = content.replace("'/api/photos/", "'/s/api/photos/")
    content = content.replace("'/api/albums/", "'/s/api/albums/")
    content = content.replace("'/api/persons/", "'/s/api/persons/")
    content = content.replace("'/api/share/config'", "'/s/api/share/config'")
    content = content.replace('"/api/albums/', '"/s/api/albums/')
    content = content.replace('"/api/persons/', '"/s/api/persons/')
    content = content.replace('/albums?album=', '/s/albums?album=')

    # Nav items in shared.js: remove Catalog and Admin, rewrite rest to /s/
    nav_replacement = (
        "var _NAV_ITEMS_SHARED = [\n"
        "    { href: '/s/gallery',  ico: '\\u25A0', label: '\u0413\u0430\u043b\u0435\u0440\u0435\u044f' },\n"
        "    { href: '/s/albums',   ico: '\\u25A0', label: '\u0410\u043b\u044c\u0431\u043e\u043c\u044b' },\n"
        "    { href: '/s/map',      ico: '\\u25C9', label: '\u041a\u0430\u0440\u0442\u0430' },\n"
        "    { href: '/s/persons',  ico: '\\u25C6', label: '\u041f\u0435\u0440\u0441\u043e\u043d\u044b' },\n"
        "];"
    )
    content = _re.sub(
        r"var _NAV_ITEMS = \[.*?\];",
        lambda m: nav_replacement,
        content,
        flags=_re.DOTALL,
    )
    content = content.replace("var _NAV_ITEMS_SHARED = [", "var _NAV_ITEMS = [")
    content = content.replace("_NAV_ITEMS_SHARED", "_NAV_ITEMS")

    # Logo links in shared.js
    content = content.replace('src="/logo-dark.png"', 'src="/s/static/logo-dark.png"')
    content = content.replace('src="/logo-light.png"', 'src="/s/static/logo-light.png"')
    content = content.replace('data-light="/logo-light.png"', 'data-light="/s/static/logo-light.png"')
    content = content.replace('data-dark="/logo-dark.png"', 'data-dark="/s/static/logo-dark.png"')

    # Logo link and active nav path
    content = content.replace('href="/gallery" class="logo-link"', 'href="/s/gallery" class="logo-link"')
    content = content.replace("p === '/' || p === '/gallery'", "p === '/s/' || p === '/s/gallery'")
    content = content.replace("return '/gallery'", "return '/s/gallery'")

    return content


def _inject_shared_css(html: str) -> str:
    """Inject CSS to hide admin-only elements in shared mode."""
    css = """<style>
body.shared-mode #autoActions { display: none !important; }
body.shared-mode #manualActions { display: none !important; }
body.shared-mode .mab-share-btn { display: none !important; }
body.shared-mode .dp-btn-reprocess,
body.shared-mode .dp-btn-enrich,
body.shared-mode .dp-btn-custom,
body.shared-mode .dp-btn-toalbum,
body.shared-mode .dp-btn-restore { display: none !important; }
body.shared-mode #enrichArea,
body.shared-mode #customDescArea,
body.shared-mode #rpOverlay { display: none !important; }
body.shared-mode .manual-date-badge,
body.shared-mode .dp-date-btn,
body.shared-mode .dp-date-clear,
body.shared-mode .dp-date-save,
body.shared-mode .dp-date-cancel,
body.shared-mode #dateEditArea { display: none !important; }
body.shared-mode .dp-persona-comment { display: none !important; }
body.shared-mode .del-mark { display: none !important; }
body.shared-mode .undo-mark { display: none !important; }
body.shared-mode .dp-alt-path { display: none !important; }
body.shared-mode [onclick="generate()"] { display: none !important; }
body.shared-mode [onclick="clearAll()"] { display: none !important; }
body.shared-mode [onclick="copyAlbumShareFromBar()"] { display: none !important; }
body.shared-mode .album-bar-desc-btn { display: none !important; }
body.shared-mode .edit-album-btn { display: none !important; }
body.shared-mode #fmName { display: none !important; }
body.shared-mode .fm-right .btn-save { display: none !important; }
body.shared-mode .rename-dialog { display: none !important; }
body.shared-mode .fm-right .fm-ac { display: none !important; }
</style>
<script>document.addEventListener('DOMContentLoaded',function(){document.body.classList.add('shared-mode');});</script>
"""
    return html.replace("</head>", css + "</head>", 1)


# ─── Scope resolution ────────────────────────────────────────

def _parse_scope(scope: str):
    """Parse scope cookie. Returns (type, id) or None."""
    if not scope:
        return None
    parts = scope.split(":", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _get_scope_photo_ids(scope: str):
    """Resolve scope to list of photo_id UUIDs (primary scope).
    For persona: photos where persona appears.
    For album: photos in album.
    For photo: single photo.
    Returns None if scope invalid or expired."""
    parsed = _parse_scope(scope)
    if not parsed:
        return None
    stype, sid = parsed
    db = get_db()
    if stype == "photo":
        row = db.sqlite.execute(
            "SELECT photo_id FROM photos WHERE photo_id = ? AND deleted = 0", (sid,)
        ).fetchone()
        return [row[0]] if row else None
    if stype == "album":
        return db.get_album_photos(sid) or None
    if stype == "persona":
        rows = db.sqlite.execute(
            "SELECT DISTINCT p.photo_id FROM photos p "
            "JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 "
            "JOIN faces f ON f.content_hash = cf.content_hash "
            "WHERE f.persona_id = ? AND p.deleted = 0",
            (sid,),
        ).fetchall()
        return [r[0] for r in rows] if rows else None
    return None


def _get_scope_album_ids(scope: str):
    """Albums that contain at least one scope photo.
    For persona: albums where persona appears in any photo.
    For album: the album itself.
    For photo: albums containing that photo."""
    parsed = _parse_scope(scope)
    if not parsed:
        return []
    stype, sid = parsed
    db = get_db()
    if stype == "album":
        return [sid] if db.get_album(sid) else []
    if stype == "photo":
        rows = db.sqlite.execute(
            "SELECT DISTINCT album_id FROM album_photos WHERE photo_id = ?", (sid,)
        ).fetchall()
        return [r[0] for r in rows]
    if stype == "persona":
        photo_ids = _get_scope_photo_ids(scope)
        if not photo_ids:
            return []
        ph = ",".join("?" * len(photo_ids))
        rows = db.sqlite.execute(
            f"SELECT DISTINCT album_id FROM album_photos WHERE photo_id IN ({ph})",
            photo_ids,
        ).fetchall()
        return [r[0] for r in rows]
    return []


def _get_extended_scope_photo_ids(scope: str):
    """Extended scope: primary photo_ids + all photos from scope albums.
    Used for media access (thumbnails, full photos, video).
    For persona: persona photos + all photos in albums containing persona.
    For album/photo: same as primary scope."""
    parsed = _parse_scope(scope)
    if not parsed:
        return None
    stype, _ = parsed
    primary = _get_scope_photo_ids(scope)
    if primary is None:
        return None
    if stype == "photo":
        return primary
    if stype == "album":
        return primary
    if stype == "persona":
        album_ids = _get_scope_album_ids(scope)
        extended = set(primary)
        for aid in album_ids:
            album_photos = get_db().get_album_photos(aid)
            extended.update(album_photos)
        return list(extended)
    return primary


def _require_scope(scope: str):
    """Get scope photo_ids or raise 403."""
    ids = _get_scope_photo_ids(scope)
    if ids is None:
        raise HTTPException(status_code=403, detail="Invalid or expired share scope")
    return ids


def _in_scope(photo_path: str, scope_ids: list) -> bool:
    """Check if photo_path corresponds to a photo in scope."""
    if not scope_ids:
        return False
    scope_set = set(scope_ids)
    db = get_db()
    if photo_path in scope_set:
        return True
    row = db.sqlite.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? AND deleted = 0", (photo_path,)
    ).fetchone()
    if row and row[0] in scope_set:
        return True
    row = db.sqlite.execute(
        "SELECT photo_id FROM photos WHERE path = ? AND deleted = 0", (photo_path,)
    ).fetchone()
    if row and row[0] in scope_set:
        return True
    row = db.sqlite.execute(
        "SELECT p.photo_id FROM photos p "
        "JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 "
        "WHERE cf.content_hash = ? AND p.deleted = 0",
        (photo_path,),
    ).fetchone()
    if not row:
        row = db.sqlite.execute(
            "SELECT p.photo_id FROM photos p "
            "JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 "
            "WHERE cf.rel_path = ? AND p.deleted = 0",
            (photo_path,),
        ).fetchone()
    if row and row[0] in scope_set:
        return True
    return False


# ─── Entry points: set cookie, redirect to gallery ───────────

_NOT_FOUND_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Не найдено — Галерея</title>
<style>
body{margin:0;font-family:monospace;background:#0d1117;color:#c9d1d9;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{text-align:center;padding:40px}
.box h1{font-size:48px;margin:0 0 8px;color:#f85149}
.box p{font-size:16px;color:#8b949e;margin:4px 0}
.box a{display:inline-block;margin-top:20px;color:#58a6ff;text-decoration:none;font-size:14px}
.box a:hover{text-decoration:underline}
</style></head><body><div class="box"><h1>404</h1><p>Альбом не найден</p><p>Ссылка недействительна или была удалена</p></div></body></html>"""


def _not_found_resp() -> HTMLResponse:
    return HTMLResponse(_NOT_FOUND_HTML, status_code=404, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/album")
@router.get("/album/")
async def share_album_noid():
    return _not_found_resp()


@router.get("/album/{album_id}")
async def share_album(album_id: str):
    def _prepare():
        db = get_db()
        album = db.get_album(album_id)
        if not album:
            return None
        all_pids = db.get_album_photos(album_id)
        album["photo_ids"] = all_pids
        album["photo_count"] = len(all_pids)
        import random as _r
        cover = album.get("cover_photo_id")
        rest = [p for p in all_pids if p != cover]
        if len(rest) > 2:
            rest = _r.sample(rest, 2)
        album["preview_photos"] = ([cover] if cover else (all_pids[:1] if all_pids else [])) + rest[:3]
        if not album["preview_photos"]:
            album["preview_photos"] = rest[:3]
        members = db.get_album_members(album_id)
        sub_albums = []
        for m in members:
            if m.get("member_type") == "album":
                sa = db.get_album(m["member_id"])
                if sa:
                    sa_pids = db.get_album_photos(sa["album_id"])
                    sa_cover = sa.get("cover_photo_id")
                    sa_rest = [p for p in sa_pids if p != sa_cover]
                    if len(sa_rest) > 2:
                        sa_rest = _r.sample(sa_rest, 2)
                    sa["preview_photos"] = ([sa_cover] if sa_cover else (sa_pids[:1] if sa_pids else [])) + sa_rest[:3]
                    if not sa["preview_photos"]:
                        sa["preview_photos"] = sa_rest[:3]
                    sa["photo_count"] = len(sa_pids)
                    sub_albums.append(sa)
        return {"album": album, "members": members, "sub_albums": sub_albums}
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _prepare)
    if not data:
        return _not_found_resp()
    album = data["album"]
    p = _WEB / "albums.html"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    html = p.read_text(encoding="utf-8")
    html = _inject_shared_css(html)
    html = _rewrite_paths(html)
    import json as _json
    preload = _json.dumps(data, ensure_ascii=False, default=str)
    html = html.replace(
        "</head>",
        f'<script>window.SHARED_ALBUM_ID="{album_id}";window.SHARED_PRELOAD={preload};</script>\n</head>',
        1,
    )
    is_manual = album.get("source") == "manual"
    html = html.replace(
        "var albumId = params.get('album');",
        "var albumId = window.SHARED_ALBUM_ID || params.get('album');",
    )
    if is_manual:
        html = html.replace(
            "if (albumId) openAlbum(albumId);",
            "if (albumId) openManualAlbum(albumId);",
        )
    resp = HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    resp.set_cookie("share_scope", f"album:{album_id}", httponly=True, samesite="lax", secure=True, max_age=86400 * 30)
    return resp


@router.get("/photo")
@router.get("/photo/")
async def share_photo_noid():
    return _not_found_resp()


@router.get("/photo/{photo_id}")
async def share_photo(photo_id: str):
    def _check():
        db = get_db()
        row = db.sqlite.execute(
            "SELECT 1 FROM photos WHERE photo_id = ? AND deleted = 0", (photo_id,)
        ).fetchone()
        return row is not None
    loop = asyncio.get_event_loop()
    exists = await loop.run_in_executor(None, _check)
    if not exists:
        return _not_found_resp()
    p = _WEB / "gallery.html"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    html = p.read_text(encoding="utf-8")
    html = _inject_shared_css(html)
    html = _rewrite_paths(html)
    resp = HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    resp.set_cookie("share_scope", f"photo:{photo_id}", httponly=True, samesite="lax", secure=True, max_age=86400 * 30)
    return resp


# ─── HTML pages ──────────────────────────────────────────────

@router.get("/{page}")
async def serve_page(page: str):
    """Serve gallery pages (gallery, albums, map, persons) with rewritten paths."""
    if page not in _PAGES:
        raise HTTPException(status_code=404, detail="Page not found")
    p = _WEB / _PAGES[page]
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    html = p.read_text(encoding="utf-8")
    html = _inject_shared_css(html)
    html = _rewrite_paths(html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# ─── Static files ────────────────────────────────────────────

@router.get("/static/{filename}")
async def serve_static(filename: str):
    """Serve static assets (CSS/JS/images) with rewritten paths."""
    # favicon.ico fallback to favicon.png
    if filename == "favicon.ico":
        p = _WEB / "favicon.png"
    elif filename not in _STATIC_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    else:
        p = _WEB / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    ext = p.suffix.lower()
    mt = _MIME.get(ext, "application/octet-stream")
    content = p.read_bytes()
    if ext == ".js":
        content = _rewrite_paths(content.decode("utf-8")).encode("utf-8")
    return Response(content=content, media_type=mt,
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# ─── /s/api/* — scoped mirrors of main API ───────────────────

# --- Photos: search ---

def _build_scope_condition_filters(q, person, has_faces, no_description,
                                   has_description, has_issues, issue_type,
                                   photo_type, has_gps):
    """Build condition-based WHERE filters (non-date)."""
    params = []
    parts = []
    if q:
        parts.append(" AND description LIKE ?")
        params.append(f"%{q}%")
    if has_faces is True:
        parts.append(" AND faces_present = 1")
    elif has_faces is False:
        parts.append(" AND faces_present = 0")
    if no_description is True:
        parts.append(" AND (description IS NULL OR description = '')")
    if has_description is True:
        parts.append(" AND description IS NOT NULL AND description != ''")
    if has_issues is True:
        parts.append(" AND has_issues = 1")
    if issue_type:
        parts.append(" AND issue_type = ?")
        params.append(issue_type)
    if photo_type:
        if "," in photo_type:
            types = photo_type.split(",")
            tph = ",".join("?" * len(types))
            parts.append(f" AND photo_type IN ({tph})")
            params.extend(types)
        else:
            parts.append(" AND photo_type = ?")
            params.append(photo_type)
    if has_gps is True:
        parts.append(" AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL")
    elif has_gps is False:
        parts.append(" AND (gps_lat IS NULL OR gps_lon IS NULL)")
    return "".join(parts), params


def _build_scope_date_filters(ed, no_date, date_from, date_to,
                              date_after, date_before, path_after, path_before):
    """Build date-based WHERE filters."""
    params = []
    parts = []
    if no_date is True:
        parts.append(f" AND ({ed} IS NULL OR length({ed}) < 4 OR substr({ed},1,4) = '0000')")
    if date_from:
        parts.append(f" AND {ed} >= ?")
        params.append(date_from)
    if date_to:
        parts.append(f" AND {ed} <= ?")
        params.append(date_to)
    if date_after and path_after:
        parts.append(f" AND ({ed} > ? OR ({ed} = ? AND path > ?))")
        params.extend([date_after, date_after, path_after])
    if date_before and path_before:
        parts.append(f" AND ({ed} < ? OR ({ed} = ? AND path < ?))")
        params.extend([date_before, date_before, path_before])
    return "".join(parts), params


def _build_scope_filters(ed, conn, q, person, has_faces, no_description,
                         has_description, has_issues, issue_type, photo_type,
                         has_gps, no_date, date_from, date_to,
                         date_after, date_before, path_after, path_before):
    """Build WHERE clause filters for scoped search."""
    parts = []
    params = []
    if q:
        parts.append(" AND description LIKE ?")
        params.append(f"%{q}%")
    if person:
        pids_sub = conn.execute(
            "SELECT DISTINCT f.content_hash FROM faces f "
            "JOIN personas p ON p.persona_id = f.persona_id "
            "WHERE (p.display_name LIKE ? OR p.name LIKE ?)",
            (f"%{person}%", f"%{person}%"),
        ).fetchall()
        if pids_sub:
            sub_ph = ",".join("?" * len(pids_sub))
            parts.append(f" AND cf.content_hash IN ({sub_ph})")
            params.extend([r[0] for r in pids_sub])
        else:
            parts.append(" AND 0")
    cond_sql, cond_params = _build_scope_condition_filters(
        q, person, has_faces, no_description, has_description,
        has_issues, issue_type, photo_type, has_gps,
    )
    date_sql, date_params = _build_scope_date_filters(
        ed, no_date, date_from, date_to, date_after, date_before,
        path_after, path_before,
    )
    return "".join(parts) + cond_sql + date_sql, params + cond_params + date_params


def _enrich_search_results(conn, rows):
    """Enrich search results with faces, personas, duplicates, edits."""
    from api.photos import _enrich_photo
    hashes = [r["content_hash"] for r in rows if r["content_hash"]]
    photo_faces = {}
    persona_map = {}
    if hashes:
        hph = ",".join("?" * len(hashes))
        face_rows = conn.execute(
            f"SELECT face_id, photo_id, content_hash, persona_id, "
            f"bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence "
            f"FROM faces WHERE content_hash IN ({hph})",
            hashes,
        ).fetchall()
        face_cols = ["face_id", "photo_id", "content_hash", "persona_id",
                     "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence"]
        pids_needed = set()
        for fr in face_rows:
            fd = dict(zip(face_cols, fr))
            ch = fd.get("content_hash", "")
            if ch:
                photo_faces.setdefault(ch, []).append(fd)
            pid = fd.get("photo_id", "")
            if pid:
                photo_faces.setdefault(pid, []).append(fd)
            if fd.get("persona_id"):
                pids_needed.add(fd["persona_id"])
        if pids_needed:
            pids_list = list(pids_needed)
            pph = ",".join("?" * len(pids_list))
            p_rows = conn.execute(
                f"SELECT persona_id, name, display_name, comment "
                f"FROM personas WHERE persona_id IN ({pph})",
                pids_list,
            ).fetchall()
            for pr in p_rows:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM faces WHERE persona_id = ?", (pr[0],)
                ).fetchone()[0]
                persona_map[pr[0]] = {
                    "persona_id": pr[0], "name": pr[1],
                    "display_name": pr[2], "total_face_count": cnt,
                }
    result = []
    for r in rows:
        d = dict(r)
        d = _enrich_photo(d, photo_faces, persona_map, include_created=True)
        result.append(d)
    return result


@router.get("/api/photos/search")
async def s_search_photos(
    request: Request,
    q: str = "",
    person: str = "",
    date_from: str = "",
    date_to: str = "",
    date_after: str = "",
    date_before: str = "",
    path_after: str = "",
    path_before: str = "",
    has_faces: bool = None,
    no_description: bool = None,
    has_issues: bool = None,
    issue_type: str = None,
    photo_type: str = None,
    has_gps: bool = None,
    no_date: bool = None,
    has_description: bool = None,
    sort: str = "date_desc",
    limit: int = 60,
    offset: int = 0,
):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _search():
        db = get_db()
        import sqlite3 as _sq3
        conn = _sq3.connect(str(db.db_path), timeout=30)
        conn.row_factory = _sq3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            ed = "COALESCE(date_utc, manual_date, date)"
            ph = ",".join("?" * len(scope_ids))
            base = (
                f"SELECT photos.*, {ed} as effective_date, cf.content_hash "
                f"FROM photos JOIN catalog_files cf ON cf.abs_path = photos.path "
                f"WHERE cf.is_canonical = 1 AND cf.deleted = 0 "
                f"AND photos.deleted = 0 AND photos.photo_id IN ({ph})"
            )
            filter_sql, filter_params = _build_scope_filters(
                ed, conn, q, person, has_faces, no_description,
                has_description, has_issues, issue_type, photo_type,
                has_gps, no_date, date_from, date_to,
                date_after, date_before, path_after, path_before,
            )
            params = list(scope_ids) + filter_params
            order_map = {
                "date_desc": "effective_date DESC, path DESC",
                "date_asc": "effective_date ASC, path ASC",
                "created_desc": "created_at DESC, path DESC",
                "created_asc": "created_at ASC, path ASC",
            }
            sql = base + filter_sql + f" ORDER BY {order_map.get(sort, 'effective_date DESC')}"

            from_idx = sql.index(" FROM ")
            count_sql = "SELECT COUNT(*)" + sql[from_idx:]
            count_sql = count_sql.split(" ORDER BY ")[0]
            total = conn.execute(count_sql, params).fetchone()[0]

            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()

            result = _enrich_search_results(conn, rows)

            batch_hashes = [p.get("content_hash") for p in result if p.get("content_hash")]
            if batch_hashes:
                bh_ph = ",".join("?" * len(batch_hashes))
                dup_rows = conn.execute(
                    f"SELECT content_hash, abs_path FROM catalog_files "
                    f"WHERE content_hash IN ({bh_ph}) AND is_canonical = 0 "
                    f"ORDER BY content_hash, abs_path",
                    batch_hashes,
                ).fetchall()
                dup_map = {}
                for dr in dup_rows:
                    dup_map.setdefault(dr[0], []).append(dr[1])
                edits_rows = conn.execute(
                    f"SELECT content_hash, edit_id, action, params, action_order, enabled "
                    f"FROM photo_edits "
                    f"WHERE content_hash IN ({bh_ph}) AND enabled = 1 "
                    f"ORDER BY content_hash, action_order",
                    batch_hashes,
                ).fetchall()
                edits_map = {}
                import json as _json
                for er in edits_rows:
                    edits_map.setdefault(er[0], []).append({
                        "edit_id": er[1], "action": er[2],
                        "params": _json.loads(er[3]), "action_order": er[4],
                        "enabled": er[5],
                    })
                for p in result:
                    h = p.get("content_hash")
                    p["duplicate_paths"] = dup_map.get(h, []) if h else []
                    p["edits"] = edits_map.get(h, []) if h else []
            else:
                for p in result:
                    p["duplicate_paths"] = []
                    p["edits"] = []

            return {"total": total, "photos": result}
        finally:
            conn.close()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search)


# --- Photos: dates histogram ---

@router.get("/api/photos/dates")
async def s_dates(request: Request):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _dates():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        ed = "COALESCE(date_utc, manual_date, date)"
        rows = db.sqlite.execute(
            f"SELECT substr({ed},1,4) as year, substr({ed},1,7) as month, "
            f"substr({ed},1,10) as day, COUNT(*) as cnt "
            f"FROM photos WHERE {ed} IS NOT NULL AND length({ed}) >= 4 "
            f"AND substr({ed},1,4) != '0000' AND deleted = 0 "
            f"AND photo_id IN ({ph}) "
            f"GROUP BY year, month, day ORDER BY year, month, day",
            scope_ids,
        ).fetchall()
        years, months, days = {}, {}, {}
        min_d, max_d = None, None
        for r in rows:
            y, m, d, cnt = r[0], r[1], r[2], r[3]
            years[y] = years.get(y, 0) + cnt
            months[m] = months.get(m, 0) + cnt
            days[d] = days.get(d, 0) + cnt
            if min_d is None or d < min_d:
                min_d = d
            if max_d is None or d > max_d:
                max_d = d
        result = {
            "years": dict(sorted(years.items())),
            "months": dict(sorted(months.items())),
            "days": dict(sorted(days.items())),
            "total": sum(years.values()),
        }
        if min_d:
            result["date_range"] = {"min": min_d, "max": max_d}
        return result

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _dates)


# --- Photos: map ---

@router.get("/api/photos/map")
async def s_map(request: Request):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _map():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        rows = db.sqlite.execute(
            f"SELECT photo_id, path, description, gps_lat, gps_lon, "
            f"COALESCE(manual_date, date) as date, camera_make, camera_model, "
            f"img_width, img_height, manual_gps, media_type "
            f"FROM photos WHERE gps_lat IS NOT NULL AND gps_lon IS NOT NULL "
            f"AND gps_lat != 0 AND gps_lon != 0 AND deleted = 0 "
            f"AND photo_id IN ({ph})",
            scope_ids,
        ).fetchall()
        result = []
        for r in rows:
            d = dict(zip([
                "photo_id", "path", "description", "gps_lat", "gps_lon",
                "date", "camera_make", "camera_model", "img_width",
                "img_height", "manual_gps", "media_type"
            ], r))
            d["lat"] = d.pop("gps_lat")
            d["lon"] = d.pop("gps_lon")
            d["camera"] = f"{d.pop('camera_make', '')} {d.pop('camera_model', '')}".strip()
            d["w"] = d.pop("img_width")
            d["h"] = d.pop("img_height")
            d["faces"] = []
            d["needs_stream"] = d.get("media_type") == "video"
            result.append(d)

        if result:
            map_pids = [p["photo_id"] for p in result]
            face_map = {}
            for i in range(0, len(map_pids), 500):
                batch = map_pids[i:i + 500]
                bph = ",".join("?" * len(batch))
                frs = db.sqlite.execute(
                    f"SELECT p.photo_id, f.face_id, f.persona_id, "
                    f"f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, "
                    f"per.display_name, per.name "
                    f"FROM faces f "
                    f"JOIN catalog_files cf ON cf.content_hash = f.content_hash "
                    f"JOIN photos p ON p.path = cf.abs_path "
                    f"LEFT JOIN personas per ON per.persona_id = f.persona_id "
                    f"WHERE p.photo_id IN ({bph}) AND cf.is_canonical = 1",
                    batch,
                ).fetchall()
                for fr in frs:
                    pid = fr[0]
                    face_map.setdefault(pid, []).append({
                        "face_id": fr[1], "persona_id": fr[2],
                        "bbox_x1": fr[3], "bbox_y1": fr[4],
                        "bbox_x2": fr[5], "bbox_y2": fr[6],
                        "display_name": fr[7], "name": fr[8],
                    })
            for p in result:
                p["faces"] = face_map.get(p["photo_id"], [])
        return result

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _map)


# --- Photos: media (thumbnail, full, face, video) ---

@router.get("/api/photos/thumbnail")
async def s_thumbnail(request: Request, path: str = "", size: str = "sm", fit: bool = False):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)
    if not _in_scope(path, scope_ids):
        raise HTTPException(status_code=404, detail="Not found")
    from api.photos import get_thumbnail
    return await get_thumbnail(path=path, size=size, fit=fit)


@router.get("/api/photos/")
async def s_photo(request: Request, path: str):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)
    if not _in_scope(path, scope_ids):
        raise HTTPException(status_code=404, detail="Not found")
    from api.photos import get_photo
    return await get_photo(path=path)


@router.get("/api/photos/face/{face_id}")
async def s_face_crop(face_id: str, margin: float = 0.5):
    from api.photos import get_face_crop
    return await get_face_crop(face_id=face_id, margin=margin)


@router.get("/api/photos/face_context/{face_id}")
async def s_face_context(face_id: str, zoom: float = 3.0):
    from api.photos import get_face_context
    return await get_face_context(face_id=face_id, zoom=zoom)


@router.get("/api/photos/edits/{content_hash}")
async def s_get_edits(content_hash: str):
    from api.photos import get_edits
    return await get_edits(content_hash=content_hash)


@router.get("/api/photos/video_meta")
async def s_video_meta(request: Request, path: str = ""):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)
    if not _in_scope(path, scope_ids):
        raise HTTPException(status_code=404, detail="Not found")
    from api.video import video_meta
    return await video_meta(path=path)


@router.get("/api/photos/video_stream")
async def s_video_stream(request: Request, path: str = "", t: float = 0):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)
    if not _in_scope(path, scope_ids):
        raise HTTPException(status_code=404, detail="Not found")
    from api.video import video_stream
    return await video_stream(path=path, t=t, request=request)


@router.get("/api/photos/neighbor")
async def s_neighbor(request: Request, date: str, dir: str = "next"):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _neighbor():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        if dir == "next":
            row = db.sqlite.execute(
                f"SELECT photo_id, path, COALESCE(date_utc, manual_date, date) as date, "
                f"camera_make, camera_model, gps_lat, gps_lon, media_type "
                f"FROM photos WHERE COALESCE(date_utc, manual_date, date) > ? "
                f"AND deleted = 0 AND photo_id IN ({ph}) "
                f"ORDER BY COALESCE(date_utc, manual_date, date) ASC LIMIT 1",
                [date] + scope_ids,
            ).fetchone()
        else:
            row = db.sqlite.execute(
                f"SELECT photo_id, path, COALESCE(date_utc, manual_date, date) as date, "
                f"camera_make, camera_model, gps_lat, gps_lon, media_type "
                f"FROM photos WHERE COALESCE(date_utc, manual_date, date) < ? "
                f"AND deleted = 0 AND photo_id IN ({ph}) "
                f"ORDER BY COALESCE(date_utc, manual_date, date) DESC LIMIT 1",
                [date] + scope_ids,
            ).fetchone()
        if not row:
            return None
        return {
            "photo_id": row[0], "path": row[1], "date": row[2],
            "camera": f"{row[3] or ''} {row[4] or ''}".strip(),
            "gps_lat": row[5], "gps_lon": row[6], "media_type": row[7],
            "faces": [],
        }

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _neighbor)
    return result if result else {"photo_id": None}


# --- Albums ---

@router.get("/api/albums/")
async def s_list_albums(request: Request, source: str = ""):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _list():
        db = get_db()
        if not scope_ids:
            return []
        ph = ",".join("?" * len(scope_ids))
        query = (
            f"SELECT DISTINCT a.album_id, a.title, a.description, a.cover_photo_id, "
            f"a.date_start, a.date_end, a.photo_count, a.source, a.created_at, a.updated_at "
            f"FROM albums a "
            f"JOIN album_photos ap ON ap.album_id = a.album_id "
            f"WHERE ap.photo_id IN ({ph})"
        )
        params = list(scope_ids)
        if source in ("auto", "manual"):
            query += " AND a.source = ?"
            params.append(source)
        query += " ORDER BY a.date_start DESC"
        rows = db.sqlite.execute(query, params).fetchall()
        albums = []
        cols = ["album_id", "title", "description", "cover_photo_id",
                "date_start", "date_end", "photo_count", "source",
                "created_at", "updated_at"]
        for r in rows:
            a = dict(zip(cols, r))
            pids = db.get_album_photos(a["album_id"])
            scope_set = set(scope_ids)
            a["photo_ids"] = [p for p in pids if p in scope_set]
            a["photo_count"] = len(a["photo_ids"])
            import random as _r
            cover = a.get("cover_photo_id")
            rest = [p for p in a["photo_ids"] if p != cover]
            if len(rest) > 2:
                rest = _r.sample(rest, 2)
            if cover and cover in scope_set:
                preview = [cover]
            elif a["photo_ids"]:
                preview = [a["photo_ids"][0]]
            else:
                preview = []
            a["preview_photos"] = preview + rest[:2]
            albums.append(a)
        return albums

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _list)


@router.get("/api/albums/{album_id}")
async def s_get_album(album_id: str, request: Request, full: bool = False):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _get():
        db = get_db()
        album = db.get_album(album_id)
        if not album:
            return None
        all_pids = db.get_album_photos(album_id)
        scope_set = set(scope_ids)
        scoped_pids = [p for p in all_pids if p in scope_set]
        album["photo_ids"] = scoped_pids
        album["photo_count"] = len(scoped_pids)
        import random as _r
        cover = album.get("cover_photo_id")
        rest = [p for p in scoped_pids if p != cover]
        if len(rest) > 2:
            rest = _r.sample(rest, 2)
        album["preview_photos"] = ([cover] if cover else (scoped_pids[:1] if scoped_pids else [])) + rest[:3]
        if not album["preview_photos"]:
            album["preview_photos"] = rest[:3]
        if full and scoped_pids:
            from api.albums import _enrich_album_photos
            album["photos"] = _enrich_album_photos(db, scoped_pids)
        elif full:
            album["photos"] = []
        return album

    loop = asyncio.get_event_loop()
    album = await loop.run_in_executor(None, _get)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    return album


@router.get("/api/albums/by_photo/{photo_id}")
async def s_find_album_by_photo(photo_id: str, request: Request):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)
    if photo_id not in scope_ids:
        raise HTTPException(status_code=403, detail="Not in scope")
    from api.albums import find_album_by_photo
    return await find_album_by_photo(photo_id=photo_id)


# --- Persons ---

@router.get("/api/persons/")
async def s_list_persons(request: Request, limit: int = 500, offset: int = 0, named_only: bool = False):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _list():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        face_rows = db.sqlite.execute(
            f"SELECT DISTINCT f.persona_id FROM faces f "
            f"JOIN catalog_files cf ON cf.content_hash = f.content_hash AND cf.is_canonical = 1 "
            f"JOIN photos p ON p.path = cf.abs_path "
            f"WHERE p.photo_id IN ({ph}) AND p.deleted = 0 AND f.persona_id IS NOT NULL",
            scope_ids,
        ).fetchall()
        persona_ids = [r[0] for r in face_rows]
        if not persona_ids:
            return {"total": 0, "persons": []}
        pph = ",".join("?" * len(persona_ids))
        rows = db.sqlite.execute(
            f"SELECT per.persona_id, per.name, per.display_name, per.comment "
            f"FROM personas per WHERE per.persona_id IN ({pph}) "
            + ("AND per.display_name IS NOT NULL " if named_only else "")
            + "ORDER BY per.display_name",
            persona_ids,
        ).fetchall()
        persons = []
        for r in rows:
            pid = r[0]
            cnt = db.sqlite.execute(
                f"SELECT COUNT(DISTINCT f.face_id) FROM faces f "
                f"JOIN catalog_files cf ON cf.content_hash = f.content_hash AND cf.is_canonical = 1 "
                f"JOIN photos p ON p.path = cf.abs_path "
                f"WHERE f.persona_id = ? AND p.photo_id IN ({ph}) AND p.deleted = 0",
                [pid] + scope_ids,
            ).fetchone()[0]
            min_face = db.sqlite.execute(
                "SELECT face_id FROM faces WHERE persona_id = ? LIMIT 1", (pid,)
            ).fetchone()
            persons.append({
                "persona_id": pid, "name": r[1], "display_name": r[2],
                "comment": r[3], "face_count": cnt,
                "face_id": min_face[0] if min_face else None,
            })
        persons.sort(key=lambda x: x.get("face_count", 0), reverse=True)
        total = len(persons)
        persons = persons[offset:offset + limit]
        return {"total": total, "persons": persons}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _list)


@router.get("/api/persons/names")
async def s_person_names(request: Request):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _names():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        rows = db.sqlite.execute(
            f"SELECT DISTINCT per.display_name FROM personas per "
            f"JOIN faces f ON f.persona_id = per.persona_id "
            f"JOIN catalog_files cf ON cf.content_hash = f.content_hash AND cf.is_canonical = 1 "
            f"JOIN photos p ON p.path = cf.abs_path "
            f"WHERE p.photo_id IN ({ph}) AND p.deleted = 0 "
            f"AND per.display_name IS NOT NULL "
            f"ORDER BY per.display_name",
            scope_ids,
        ).fetchall()
        return [r[0] for r in rows]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _names)


@router.get("/api/persons/{persona_id}")
async def s_get_person(persona_id: str, request: Request):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _get():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        row = db.sqlite.execute(
            "SELECT persona_id, name, display_name, comment FROM personas WHERE persona_id = ?",
            (persona_id,),
        ).fetchone()
        if not row:
            return None
        cnt = db.sqlite.execute(
            f"SELECT COUNT(DISTINCT f.face_id) FROM faces f "
            f"JOIN catalog_files cf ON cf.content_hash = f.content_hash AND cf.is_canonical = 1 "
            f"JOIN photos p ON p.path = cf.abs_path "
            f"WHERE f.persona_id = ? AND p.photo_id IN ({ph}) AND p.deleted = 0",
            [persona_id] + scope_ids,
        ).fetchone()[0]
        return {
            "persona_id": row[0], "name": row[1],
            "display_name": row[2], "comment": row[3], "face_count": cnt,
        }

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _get)
    if not result:
        raise HTTPException(status_code=404, detail="Person not found")
    return result


@router.get("/api/persons/{persona_id}/faces")
async def s_person_faces(persona_id: str, request: Request, limit: int = 100, dedupe_by_photo: bool = True):
    scope = request.cookies.get("share_scope", "")
    scope_ids = _require_scope(scope)

    def _faces():
        db = get_db()
        ph = ",".join("?" * len(scope_ids))
        rows = db.sqlite.execute(
            f"SELECT f.face_id, f.photo_id, f.content_hash, f.persona_id, "
            f"f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, f.confidence, "
            f"p.path as photo_path, COALESCE(p.date_utc, p.manual_date, p.date) as date, p.media_type "
            f"FROM faces f "
            f"JOIN catalog_files cf ON cf.content_hash = f.content_hash AND cf.is_canonical = 1 "
            f"JOIN photos p ON p.path = cf.abs_path "
            f"WHERE f.persona_id = ? AND p.photo_id IN ({ph}) AND p.deleted = 0 "
            f"ORDER BY f.confidence DESC",
            [persona_id] + scope_ids,
        ).fetchall()
        faces = []
        seen_photos = set()
        for r in rows:
            d = dict(zip([
                "face_id", "photo_id", "content_hash", "persona_id",
                "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence",
                "photo_path", "date", "media_type"
            ], r))
            if dedupe_by_photo:
                key = d.get("photo_path") or d.get("photo_id")
                if key in seen_photos:
                    continue
                seen_photos.add(key)
            faces.append(d)
            if len(faces) >= limit:
                break
        return faces

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _faces)


@router.get("/api/share/config")
async def s_share_config():
    from database import get_db
    db = get_db()
    base_url = db.get_setting("share_base_url") or ""
    return {"base_url": base_url}


@router.get("/api/albums/{album_id}/members")
async def s_get_album_members(album_id: str, request: Request):
    scope = request.cookies.get("share_scope", "")
    _require_scope(scope)
    from database import get_db

    def _get():
        db = get_db()
        if not db.get_album(album_id):
            return None
        return db.get_album_members(album_id)

    loop = asyncio.get_event_loop()
    members = await loop.run_in_executor(None, _get)
    if members is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return members


# --- All mutations: 403 ---

@router.api_route("/api/{path:path}", methods=["POST", "PUT", "DELETE", "PATCH"])
async def s_reject_mutation(path: str):
    raise HTTPException(status_code=403, detail="Mutations not allowed in shared mode")
