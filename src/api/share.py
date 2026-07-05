"""share.py — публичные read-only страницы для шеринга по ссылке.

Маршруты под /s/ — изолированный мир, nginx проксирует только /s/.
  /s/album/{album_id}       — albums.html в shared mode
  /s/photo/{photo_id}       — gallery.html в shared mode
  /s/photos/thumbnail       — thumbnail (read-only)
  /s/photos/                — полное фото (read-only)
  /s/photos/face/{id}       — кроп лица (read-only)
  /s/photos/edits/{hash}    — правки GET (read-only)
  /s/photos/video_meta      — метаданные видео (read-only)
  /s/albums/{id}            — данные альбома (read-only)
  /s/albums/by_photo/{id}   — альбомы фото (read-only)
  /s/{static}               — CSS/JS/иконки (переписанные пути)

Безопасность: photo_id и album_id — UUID4, неперебираемы.
Нет поиска, нет перечисления, нет мутаций — только конкретные объекты по ID.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from config import PROJECT_ROOT
from database import get_db

router = APIRouter(prefix="/s", tags=["share"])

_WEB = PROJECT_ROOT / "web"

_STATIC_FILES = [
    "shared.css", "shared.js", "viewer.css", "viewer.js",
    "face-modal.css", "face-modal.js", "gallery-common.js",
    "gallery.js", "gallery-detail.js", "gallery-ui.js",
    "favicon-32.png", "favicon.png", "apple-touch-icon.png",
    "logo-dark.png", "logo-light.png",
]

_MIME = {
    ".css": "text/css", ".js": "application/javascript",
    ".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".html": "text/html", ".json": "application/json",
}


def _rewrite_paths(content: str) -> str:
    """Переписать все absolute paths /X → /s/X для изоляции под /s/."""
    for f in _STATIC_FILES:
        content = content.replace(f'"/{f}"', f'"/s/{f}"')
    content = content.replace('"/api"', '"/s"')
    content = content.replace("var API = '/api'", "var API = '/s'")
    content = content.replace('/albums?album=', '/s/album/')
    return content


def _inject_shared(html: str, mode: str, target_id: str, data_json: str = "") -> str:
    """Вставить SHARED_MODE инъекцию + CSS скрытия админки в HTML."""
    injection = (
        f'<script>window.SHARED_MODE="{mode}";'
        f'window.SHARED_ID="{target_id}";</script>\n'
    )
    if data_json:
        injection += f'<script>window.__SHARED_DATA__={data_json};</script>\n'

    shared_css = """
<style>
body.shared-mode .header-sticky { display: none !important; }
body.shared-mode .timeline { display: none !important; }
body.shared-mode .info-bar { display: none !important; }
body.shared-mode .top-sentinel { display: none !important; }
body.shared-mode .scroll-sentinel { display: none !important; }
body.shared-mode .del-mark { display: none !important; }
body.shared-mode .undo-mark { display: none !important; }
body.shared-mode .dp-btn-reprocess,
body.shared-mode .dp-btn-enrich,
body.shared-mode .dp-btn-custom,
body.shared-mode .dp-btn-share,
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
body.shared-mode .dp-alt-path { display: none !important; }
body.shared-mode .tb.gps { display: none !important; }
body.shared-mode .dp-map-link { display: none !important; }
body.shared-mode .grid { padding-top: 10px; }
</style>
<script>
document.addEventListener('DOMContentLoaded',function(){
  document.body.classList.add('shared-mode');
  if (window.SHARED_MODE) {
    var _origOpen = window.open;
    window.open = function(url) {
      if (!url) return null;
      if (url.indexOf('/s/') === 0 || url.indexOf(location.origin + '/s/') === 0) return _origOpen.call(window, url);
      return null;
    };
    document.addEventListener('click', function(e) {
      var a = e.target.closest && e.target.closest('a');
      if (a && a.href) {
        var p = a.getAttribute('href') || '';
        if (p.indexOf('/s/') !== 0 && p.indexOf('#') !== 0) {
          e.preventDefault(); e.stopPropagation();
        }
      }
    }, true);
  }
});
</script>
"""
    html = html.replace("</head>", shared_css + injection + "</head>", 1)

    if mode == "photo" and data_json:
        dosearch_override = """
<script>
if (window.SHARED_MODE === 'photo' && window.__SHARED_DATA__) {
  doSearch = function() {
    currentPhotos = window.__SHARED_DATA__.photos || [];
    totalResults = currentPhotos.length;
    _canLoadMore = false;
    _canLoadPrev = false;
    document.getElementById('grid').innerHTML = '';
    if (currentPhotos.length > 0) appendGrid(currentPhotos, 0);
    updateInfo();
    if (currentPhotos.length > 0) {
      var idx = currentPhotos.findIndex(function(p) {
        return p.photo_id === window.SHARED_ID || p.db_id === window.SHARED_ID;
      });
      if (idx >= 0) setTimeout(function() { Viewer.open(currentPhotos, idx); }, 300);
    }
  };
}
</script>
"""
        html = html.replace(
            '<script src="/gallery-ui.js"></script>',
            dosearch_override + '<script src="/gallery-ui.js"></script>',
            1,
        )

    return html


# ─── HTML страницы ───────────────────────────────────────────

@router.get("/album/{album_id}")
async def share_album(album_id: str):
    def _check():
        db = get_db()
        return db.get_album(album_id) is not None

    loop = asyncio.get_event_loop()
    exists = await loop.run_in_executor(None, _check)
    if not exists:
        raise HTTPException(status_code=404, detail="Album not found")

    p = _WEB / "albums.html"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    html = p.read_text(encoding="utf-8")
    html = _inject_shared(html, "album", album_id)
    html = _rewrite_paths(html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/photo/{photo_id}")
async def share_photo(photo_id: str):
    def _build():
        db = get_db()
        row = db.sqlite.execute(
            "SELECT 1 FROM photos WHERE photo_id = ? AND deleted = 0",
            (photo_id,)
        ).fetchone()
        if not row:
            return None

        from api.albums import _enrich_album_photos
        photos = _enrich_album_photos(db, [photo_id])
        if not photos:
            return None

        import json
        return json.dumps({"total": 1, "photos": photos}, ensure_ascii=False)

    loop = asyncio.get_event_loop()
    data_json = await loop.run_in_executor(None, _build)
    if not data_json:
        raise HTTPException(status_code=404, detail="Photo not found")

    p = _WEB / "gallery.html"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    html = p.read_text(encoding="utf-8")
    html = _inject_shared(html, "photo", photo_id, data_json)
    html = _rewrite_paths(html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# ─── Статические ресурсы под /s/ ─────────────────────────────

@router.get("/{filename}")
async def serve_static(filename: str):
    if filename not in _STATIC_FILES:
        raise HTTPException(status_code=404, detail="Not found")
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


# ─── Read-only API под /s/ ───────────────────────────────────
# Переиспользуют логику из photos.py, albums.py, video.py

@router.get("/photos/thumbnail")
async def s_thumbnail(path: str = "", size: str = "sm", fit: bool = False, abs_path: str = ""):
    from api.photos import get_thumbnail
    return await get_thumbnail(path=path, size=size, fit=fit, abs_path=abs_path)


@router.get("/photos/")
async def s_photo(path: str):
    from api.photos import get_photo
    return await get_photo(path=path)


@router.get("/photos/face/{face_id}")
async def s_face_crop(face_id: str, margin: float = 0.5):
    from api.photos import get_face_crop
    return await get_face_crop(face_id=face_id, margin=margin)


@router.get("/photos/edits/{content_hash}")
async def s_get_edits(content_hash: str):
    from api.photos import get_edits
    return await get_edits(content_hash=content_hash)


@router.get("/photos/video_meta")
async def s_video_meta(path: str = ""):
    from api.video import video_meta
    return await video_meta(path=path)


@router.get("/photos/video_stream")
async def s_video_stream(path: str = "", t: float = 0, request: Request = None):
    from api.video import video_stream
    return await video_stream(path=path, t=t, request=request)


@router.get("/albums/{album_id}")
async def s_get_album(album_id: str, full: bool = False):
    from api.albums import get_album
    return await get_album(album_id=album_id, full=full)


@router.get("/albums/by_photo/{photo_id}")
async def s_find_album_by_photo(photo_id: str):
    from api.albums import find_album_by_photo
    return await find_album_by_photo(photo_id=photo_id)
