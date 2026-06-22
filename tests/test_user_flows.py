"""
E2E tests that mirror the real user experience in gallery.html.
Each test class = a user flow. Each test = a user action + expected result.

Tests hit the LIVE server on localhost:8000 with the REAL database.
Skip if server not running.

GPU tests are in a separate class at the bottom — they need llama-server running.
Run:  pytest tests/test_user_flows.py -v --tb=short
"""
import json
import time
import pytest
import urllib.request
import urllib.parse
import urllib.error

BASE = "http://localhost:8000"


def _skip_if_no_server():
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=3)
    except Exception:
        pytest.skip("uvicorn not running — start: systemctl start gailery")


def _get(path, timeout=15):
    from urllib.parse import quote, urlsplit, urlunsplit
    parts = urlsplit(f"{BASE}{path}")
    encoded_path = quote(parts.path, safe='/%')
    encoded_query = quote(parts.query, safe='=&+%')
    url = urlunsplit((parts.scheme, parts.netloc, encoded_path, encoded_query, parts.fragment))
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        body = resp.read()
        elapsed = time.time() - t0
        return resp.getcode(), body, elapsed
    except urllib.error.HTTPError as e:
        body = e.read()
        elapsed = time.time() - t0
        return e.code, body, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return 0, str(e).encode(), elapsed


def _post(path, data, timeout=15):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        rbody = resp.read()
        elapsed = time.time() - t0
        return resp.getcode(), rbody, elapsed
    except urllib.error.HTTPError as e:
        rbody = e.read()
        elapsed = time.time() - t0
        return e.code, rbody, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return 0, str(e).encode(), elapsed


def _put(path, data, timeout=15):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="PUT")
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        rbody = resp.read()
        elapsed = time.time() - t0
        return resp.getcode(), rbody, elapsed
    except urllib.error.HTTPError as e:
        rbody = e.read()
        elapsed = time.time() - t0
        return e.code, rbody, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return 0, str(e).encode(), elapsed


def _json(body_bytes):
    return json.loads(body_bytes.decode())


@pytest.fixture(autouse=True, scope="module")
def check_server():
    _skip_if_no_server()


def _first_photo_from_search():
    code, body, _ = _get("/api/photos/search?limit=1&sort=date_desc")
    assert code == 200
    data = _json(body)
    assert data["total"] > 0
    assert len(data["photos"]) > 0
    return data["photos"][0]


def _photo_with_faces():
    code, body, _ = _get("/api/photos/search?limit=60&has_faces=true&sort=date_desc")
    assert code == 200
    data = _json(body)
    for p in data["photos"]:
        if p.get("faces") and len(p["faces"]) > 0:
            return p
    pytest.skip("no photos with faces in DB")


def _photo_with_gps():
    code, body, _ = _get("/api/photos/search?limit=60&has_gps=true&sort=date_desc")
    assert code == 200
    data = _json(body)
    for p in data["photos"]:
        if p.get("gps_lat") and p.get("gps_lon"):
            return p
    pytest.skip("no photos with GPS in DB")


def _photo_with_description():
    code, body, _ = _get("/api/photos/search?limit=60&has_description=true&sort=date_desc")
    assert code == 200
    data = _json(body)
    for p in data["photos"]:
        if p.get("description"):
            return p
    pytest.skip("no photos with description in DB")


# ═══════════════════════════════════════════════════════════════
# Flow 1: Browse gallery homepage
# User: opens /gallery → sees timeline, photo grid, thumbnails
# ═══════════════════════════════════════════════════════════════

class TestBrowseGallery:
    def test_gallery_page_loads(self):
        code, body, elapsed = _get("/gallery")
        assert code == 200
        assert b"gallery" in body.lower() or "Галерея".encode() in body
        assert elapsed < 1.0, f"gallery page took {elapsed:.2f}s — must be instant"

    def test_timeline_loads(self):
        code, body, elapsed = _get("/api/photos/dates")
        assert code == 200
        data = _json(body)
        assert "years" in data
        years = data["years"]
        assert len(years) > 0, "timeline must have years"
        total = sum(years.values())
        assert total > 1000, f"timeline shows only {total} photos — too few"

    def test_first_page_of_photos(self):
        code, body, elapsed = _get("/api/photos/search?limit=60&sort=date_desc")
        assert code == 200
        data = _json(body)
        assert data["total"] > 1000
        assert len(data["photos"]) == 60
        assert elapsed < 2.0, f"search first page took {elapsed:.2f}s"

    def test_photo_card_fields(self):
        photo = _first_photo_from_search()
        required = ["photo_id", "path", "description", "date", "faces_present",
                     "deleted", "content_hash", "personas", "faces", "is_canonical",
                     "embedded", "exif_checked"]
        for f in required:
            assert f in photo, f"card missing field '{f}' — frontend needs it"

    def test_thumbnail_loads(self):
        photo = _first_photo_from_search()
        pid = urllib.parse.quote(photo["photo_id"], safe="")
        code, body, elapsed = _get(f"/api/photos/thumbnail?path={pid}&size=sm", timeout=10)
        assert code == 200, f"thumbnail returned {code} for {pid}"
        assert len(body) > 100, "thumbnail too small — probably broken"
        assert elapsed < 3.0, f"thumbnail took {elapsed:.2f}s"

    def test_infinite_scroll_next_page(self):
        code, body, _ = _get("/api/photos/search?limit=60&sort=date_desc")
        data = _json(body)
        last_photo = data["photos"][-1]
        last_date = last_photo.get("date", "")
        last_path = urllib.parse.quote(last_photo.get("path", ""), safe="")
        code2, body2, _ = _get(
            f"/api/photos/search?limit=60&sort=date_desc"
            f"&date_after={urllib.parse.quote(last_date, safe='')}"
            f"&path_after={last_path}"
        )
        assert code2 == 200
        data2 = _json(body2)
        assert len(data2["photos"]) > 0, "scrolling must load more photos"

    def test_status_polling(self):
        code, body, elapsed = _get("/api/status")
        assert code == 200
        data = _json(body)
        for k in ["photos_total", "pct_described", "pct_exif", "current_step"]:
            assert k in data, f"status missing key '{k}'"
        assert data["photos_total"] > 1000

    def test_status_cached_second_call(self):
        _get("/api/status")
        code, body, elapsed = _get("/api/status")
        assert code == 200
        assert elapsed < 0.5, f"cached status took {elapsed:.3f}s — cache not working"


# ═══════════════════════════════════════════════════════════════
# Flow 2: View photo detail (click card → detail panel)
# User: clicks card → sees description, faces, date, camera, GPS
# ═══════════════════════════════════════════════════════════════

class TestViewPhotoDetail:
    def test_detail_opens_on_click(self):
        photo = _photo_with_faces()
        ch = photo.get("content_hash", "")
        if not ch:
            pytest.skip("photo has no content_hash")
        code, body, _ = _get(f"/api/photos/edits/{ch}")
        assert code in (200, 404), f"edits endpoint returned {code}"

    def test_detail_shows_description(self):
        photo = _photo_with_description()
        assert photo.get("description"), "photo must have description"

    def test_detail_shows_faces(self):
        photo = _photo_with_faces()
        assert len(photo.get("faces", [])) > 0
        face = photo["faces"][0]
        for f in ["face_id", "persona_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]:
            assert f in face, f"face missing field '{f}'"

    def test_detail_shows_personas(self):
        photo = _photo_with_faces()
        personas = photo.get("personas", [])
        if len(personas) == 0:
            return
        p = personas[0]
        for f in ["persona_id", "name", "display_name", "face_count"]:
            assert f in p, f"persona missing field '{f}'"

    def test_face_crop_endpoint(self):
        photo = _photo_with_faces()
        face = photo["faces"][0]
        fid = face["face_id"]
        code, body, elapsed = _get(f"/api/photos/face/{fid}?margin=0.5", timeout=10)
        assert code == 200, f"face crop returned {code}"
        assert len(body) > 50, "face crop image too small"
        assert elapsed < 5.0, f"face crop took {elapsed:.2f}s"

    def test_face_context_endpoint(self):
        photo = _photo_with_faces()
        face = photo["faces"][0]
        fid = face["face_id"]
        code, body, elapsed = _get(f"/api/photos/face_context/{fid}?zoom=3.0", timeout=10)
        assert code == 200, f"face context returned {code}"
        assert len(body) > 100

    def test_full_photo_endpoint(self):
        photo = _first_photo_from_search()
        pid = urllib.parse.quote(photo["photo_id"], safe="")
        code, body, elapsed = _get(f"/api/photos/?path={pid}", timeout=20)
        assert code == 200, f"full photo returned {code}"
        assert len(body) > 1000

    def test_neighbor_next(self):
        photo = _first_photo_from_search()
        date = photo.get("date", "")
        code, body, _ = _get(f"/api/photos/neighbor?date={urllib.parse.quote(date, safe='')}&dir=next")
        assert code == 200

    def test_neighbor_prev(self):
        photo = _first_photo_from_search()
        date = photo.get("date", "")
        code, body, _ = _get(f"/api/photos/neighbor?date={urllib.parse.quote(date, safe='')}&dir=prev")
        assert code == 200


# ═══════════════════════════════════════════════════════════════
# Flow 3: Search with filters
# User: types query, checks checkboxes, selects person filter
# ═══════════════════════════════════════════════════════════════

class TestSearchWithFilters:
    def test_text_search(self):
        q = urllib.parse.quote("лес", safe="")
        code, body, _ = _get(f"/api/photos/search?q={q}&limit=20")
        assert code == 200, f"search returned {code}"
        data = _json(body)
        assert data["total"] >= 1, "text search must find something"

    def test_person_filter(self):
        code, body, _ = _get("/api/persons/")
        assert code == 200
        persons = _json(body).get("persons", _json(body))
        if not persons:
            pytest.skip("no personas in DB")
        name = persons[0].get("display_name") or persons[0].get("name")
        if not name:
            pytest.skip("persona has no name")
        code2, body2, _ = _get(f"/api/photos/search?person={urllib.parse.quote(name, safe='')}&limit=20")
        assert code2 == 200
        data = _json(body2)
        assert data["total"] >= 1

    def test_has_faces_filter(self):
        code, body, _ = _get("/api/photos/search?has_faces=true&limit=20")
        assert code == 200
        data = _json(body)
        for p in data["photos"]:
            assert p["faces_present"] is True

    def test_has_description_filter(self):
        code, body, _ = _get("/api/photos/search?has_description=true&limit=20")
        assert code == 200
        data = _json(body)
        for p in data["photos"]:
            assert p.get("description"), "has_description filter broken"

    def test_has_gps_filter(self):
        code, body, _ = _get("/api/photos/search?has_gps=true&limit=20")
        assert code == 200
        data = _json(body)
        for p in data["photos"]:
            assert p.get("gps_lat") is not None

    def test_date_range_filter(self):
        code, body, _ = _get("/api/photos/search?date_from=2020-01-01&date_to=2020-12-31&limit=20")
        assert code == 200
        data = _json(body)
        for p in data["photos"]:
            d = p.get("date", "")
            if d:
                assert d.startswith("2020"), f"date range filter broken: got {d}"

    def test_deleted_filter(self):
        code, body, _ = _get("/api/photos/search?deleted_only=true&limit=20")
        assert code == 200
        data = _json(body)
        if data["total"] > 0:
            for p in data["photos"]:
                assert p.get("deleted") is True

    def test_sort_date_asc(self):
        code, body, _ = _get("/api/photos/search?limit=10&sort=date_asc")
        assert code == 200
        data = _json(body)
        dates = [p.get("date", "") for p in data["photos"] if p.get("date")]
        assert dates == sorted(dates), "date_asc sort broken"

    def test_sort_date_desc(self):
        code, body, _ = _get("/api/photos/search?limit=10&sort=date_desc")
        assert code == 200
        data = _json(body)
        dates = [p.get("date", "") for p in data["photos"] if p.get("date")]
        assert dates == sorted(dates, reverse=True), "date_desc sort broken"

    def test_search_results_include_faces(self):
        photo = _photo_with_faces()
        assert len(photo.get("faces", [])) > 0, "search results must include face data"

    def test_search_by_content_hash(self):
        photo = _first_photo_from_search()
        ch = photo.get("content_hash", "")
        if not ch or len(ch) < 4:
            pytest.skip("no content_hash to search by")
        code, body, _ = _get(f"/api/photos/search?q={ch}&limit=5")
        assert code == 200
        data = _json(body)
        assert data["total"] >= 1

    def test_person_filter_panel_loads(self):
        code, body, _ = _get("/api/persons/")
        assert code == 200
        persons = _json(body).get("persons", _json(body))
        assert isinstance(persons, list)
        if len(persons) > 0:
            p = persons[0]
            for f in ["persona_id", "name", "face_count"]:
                assert f in p, f"person list item missing '{f}'"

    def test_person_names_autocomplete(self):
        code, body, _ = _get("/api/persons/names")
        assert code == 200
        names = _json(body)
        assert isinstance(names, list)


# ═══════════════════════════════════════════════════════════════
# Flow 4: Person management (face modal)
# User: clicks face → sees context image → renames → saves
# ═══════════════════════════════════════════════════════════════

class TestPersonManagement:
    def test_open_face_modal(self):
        code, body, _ = _get("/api/persons/")
        persons = _json(body).get("persons", _json(body))
        if not persons:
            pytest.skip("no personas")
        pid = persons[0]["persona_id"]
        code2, body2, _ = _get(f"/api/persons/{pid}")
        assert code2 == 200
        persona = _json(body2)
        assert persona["persona_id"] == pid
        for f in ["name", "display_name", "face_count"]:
            assert f in persona

    def test_person_faces_list(self):
        code, body, _ = _get("/api/persons/")
        persons = _json(body).get("persons", _json(body))
        if not persons:
            pytest.skip("no personas")
        pid = persons[0]["persona_id"]
        code2, body2, _ = _get(f"/api/persons/{pid}/faces?limit=5")
        assert code2 == 200
        faces = _json(body2)
        assert isinstance(faces, list)
        if len(faces) > 0:
            for f in ["face_id", "photo_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]:
                assert f in faces[0], f"face in persona list missing '{f}'"

    def test_person_by_name(self):
        code, body, _ = _get("/api/persons/names")
        names = _json(body)
        if not names:
            pytest.skip("no named personas")
        name = names[0]
        code2, body2, _ = _get(f"/api/persons/by_name/{urllib.parse.quote(name, safe='')}")
        assert code2 == 200
        result = _json(body2)
        assert isinstance(result, list)
        assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════
# Flow 5: Photo operations (date, GPS, delete, undelete)
# User: edits date, sets GPS, hides/restores photo
# ═══════════════════════════════════════════════════════════════

@pytest.mark.write
class TestPhotoOperations:
    """Операции с фото — на миникопии БД.

    Использует minidb фикстуру (копия реальной БД с ограниченным
    набором данных), НЕ трогает продакшен.
    """

    def test_set_date(self, minidb):
        """Ручная дата устанавливается через API."""
        photo = minidb["db"].sqlite.execute(
            "SELECT photo_id FROM photos WHERE deleted=0 LIMIT 1").fetchone()
        pid = photo[0]
        r = minidb["client"].post("/api/photos/set_date", json={
            "photo_id": pid, "manual_date": "2024-05-01 12:00:00",
        })
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_clear_date(self, minidb):
        """Ручная дата очищается через API."""
        photo = minidb["db"].sqlite.execute(
            "SELECT photo_id FROM photos WHERE deleted=0 LIMIT 1").fetchone()
        pid = photo[0]
        minidb["client"].post("/api/photos/set_date", json={
            "photo_id": pid, "manual_date": "2024-05-01 12:00:00",
        })
        r = minidb["client"].post("/api/photos/clear_date", json={"photo_id": pid})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_set_gps(self, minidb):
        """GPS координаты устанавливаются через API."""
        photo = minidb["db"].sqlite.execute(
            "SELECT photo_id FROM photos WHERE deleted=0 LIMIT 1").fetchone()
        pid = photo[0]
        r = minidb["client"].post("/api/photos/set_gps", json={
            "photo_id": pid, "lat": 55.75, "lon": 37.62,
        })
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_clear_gps(self, minidb):
        """GPS координаты очищаются через API."""
        photo = minidb["db"].sqlite.execute(
            "SELECT photo_id FROM photos WHERE deleted=0 LIMIT 1").fetchone()
        pid = photo[0]
        minidb["client"].post("/api/photos/set_gps", json={
            "photo_id": pid, "lat": 55.75, "lon": 37.62,
        })
        r = minidb["client"].post("/api/photos/clear_gps", json={"photo_id": pid})
        assert r.status_code == 200

    def test_delete_and_undelete(self, minidb):
        """Мягкое удаление и восстановление через API."""
        photo = minidb["db"].sqlite.execute(
            "SELECT photo_id FROM photos WHERE deleted=0 LIMIT 1").fetchone()
        pid = photo[0]
        r1 = minidb["client"].post("/api/photos/mark_deleted", json={"photo_id": pid})
        assert r1.status_code == 200
        r2 = minidb["client"].post("/api/photos/undelete", json={"photo_id": pid})
        assert r2.status_code == 200
        assert r2.json()["success"] is True

    def test_rotate_photo(self, minidb):
        """Поворот фото через API edits — файл должен существовать."""
        row = minidb["db"].sqlite.execute(
            "SELECT content_hash FROM catalog_files WHERE content_hash IS NOT NULL LIMIT 1"
        ).fetchone()
        if not row:
            pytest.skip("no content_hash")
        ch = row[0]
        r = minidb["client"].post(f"/api/photos/edits/{ch}", json={
            "action": "rotate", "params": {"angle": 90}, "replace": True,
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_get_edits(self, minidb):
        """Чтение правок: content_hash есть в minidb."""
        row = minidb["db"].sqlite.execute(
            "SELECT content_hash FROM catalog_files WHERE content_hash IS NOT NULL LIMIT 1"
        ).fetchone()
        if not row:
            pytest.skip("no content_hash")
        r = minidb["client"].get(f"/api/photos/edits/{row[0]}")
        assert r.status_code == 200
        assert "edits" in r.json()


# ═══════════════════════════════════════════════════════════════
# Flow 6: Map view
# User: opens /map → sees photo pins
# ═══════════════════════════════════════════════════════════════

class TestMapView:
    def test_map_photos(self):
        code, body, _ = _get("/api/photos/map")
        assert code == 200
        data = _json(body)
        assert isinstance(data, list)
        if len(data) > 0:
            for f in ["photo_id", "lat", "lon", "date"]:
                assert f in data[0], f"map point missing '{f}'"

    def test_map_page_loads(self):
        code, body, elapsed = _get("/map")
        assert code == 200
        assert b"map" in body.lower()


# ═══════════════════════════════════════════════════════════════
# Flow 7: Catalog page
# User: opens /catalog → sees roots and stats
# ═══════════════════════════════════════════════════════════════

class TestCatalogPage:
    def test_catalog_roots(self):
        code, body, _ = _get("/api/catalog/roots")
        assert code == 200

    def test_catalog_stats(self):
        code, body, _ = _get("/api/catalog/stats")
        assert code == 200

    def test_catalog_page_loads(self):
        code, body, elapsed = _get("/catalog")
        assert code == 200


# ═══════════════════════════════════════════════════════════════
# Flow 8: Config & control
# User: opens control page, sees config, starts/stops pipeline
# ═══════════════════════════════════════════════════════════════

class TestConfigAndControl:
    def test_config_page(self):
        code, body, _ = _get("/api/config")
        assert code == 200
        data = _json(body)
        assert "groups" in data
        group_names = [g["name"] for g in data["groups"]]
        assert "Пути" in group_names
        assert "Модели" in group_names

    def test_admin_page_loads(self):
        code, body, elapsed = _get("/admin")
        assert code == 200

    def test_watchdog_crashes(self):
        code, body, _ = _get("/api/watchdog/crashes")
        assert code == 200
        data = _json(body)
        assert "crashes" in data
        assert "mode" in data


# ═══════════════════════════════════════════════════════════════
# Flow 9: Navigation between pages
# User: uses top nav to switch between gallery/map/persons
# ═══════════════════════════════════════════════════════════════

class TestPageNavigation:
    @pytest.mark.parametrize("page", ["/gallery", "/map", "/catalog", "/persons", "/admin", "/log"])
    def test_page_loads(self, page):
        code, body, elapsed = _get(page)
        assert code == 200, f"page {page} returned {code}"
        assert elapsed < 2.0, f"page {page} took {elapsed:.2f}s"


# ═══════════════════════════════════════════════════════════════
# Flow 10: Enrich description (GPU required)
# User: clicks "Обогатить описание" → LLM generates rich_description
# ═══════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="Пишет rich_description в живую БД + требует GPU")
@pytest.mark.gpu
class TestEnrichDescription:
    def test_enrich_photo(self):
        photo = _photo_with_description()
        pid = photo["db_id"]
        code, body, elapsed = _post(f"/api/photos/{urllib.parse.quote(pid, safe='')}/enrich", {}, timeout=300)
        assert code == 200, f"enrich returned {code}: {body[:200]}"
        data = _json(body)
        assert data.get("ok") is True, f"enrich failed: {data}"
        assert data.get("rich_description"), "enrich returned no rich_description"

    def test_save_rich_description(self):
        photo = _photo_with_description()
        pid = photo["db_id"]
        code, body, _ = _put(f"/api/photos/{urllib.parse.quote(pid, safe='')}/rich_description", {
            "rich_description": "Тестовое обогащённое описание",
        })
        assert code == 200
        data = _json(body)
        assert data.get("ok") is True


# ═══════════════════════════════════════════════════════════════
# Flow 11: Semantic search (GPU required)
# User: switches to semantic mode → types query → AI finds by meaning
# ═══════════════════════════════════════════════════════════════

@pytest.mark.gpu
class TestSemanticSearch:
    """GPU required — needs llama-server for embedding + LanceDB."""

    def test_semantic_search_basic(self):
        code, body, elapsed = _get("/api/photos/semantic_search?q=летний+день+на+природе&limit=10", timeout=300)
        assert code == 200, f"semantic search returned {code}"
        data = _json(body)
        assert "photos" in data
        assert "total" in data
        if data["total"] > 0:
            photo = data["photos"][0]
            assert "score" in photo, "semantic results must have score"
            assert photo.get("score") is not None

    def test_semantic_search_no_query(self):
        code, body, _ = _get("/api/photos/semantic_search?q=&limit=10")
        assert code == 200
        data = _json(body)
        assert data["total"] == 0


# ═══════════════════════════════════════════════════════════════
# Flow 12: Reverse geocode
# User: clicks GPS badge → sees location name
# ═══════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="Пишет в живую БД — POST reverse_geocode + внешний сервис")
class TestReverseGeocode:
    def test_reverse_geocode(self, minidb):
        r = minidb["client"].post("/api/photos/reverse_geocode", json={
            "coords": [{"lat": 55.75, "lon": 37.62}]
        })
        assert r.status_code in (200, 500), f"reverse_geocode returned {r.status_code}"
        if r.status_code == 500:
            return
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(w in data[0] for w in ["Москва", "Russia", "Россия"])


# ═══════════════════════════════════════════════════════════════
# Flow 13: Backup
# User: downloads/restores database backup
# ═══════════════════════════════════════════════════════════════

class TestBackup:
    def test_download_backup(self):
        code, body, elapsed = _get("/api/backup/download", timeout=60)
        assert code == 200
        assert len(body) > 10000, "backup too small — probably broken"

    def test_maintenance_stats(self):
        code, body, _ = _get("/api/maintenance/stats")
        assert code == 200
        data = _json(body)
        assert "data_total" in data


# ═══════════════════════════════════════════════════════════════
# Flow 14: Settings
# User: reads/writes settings (e.g. enrich prompt)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.write
class TestSettings:
    def test_get_setting(self):
        code, body, _ = _get("/api/settings/test_key")
        assert code == 200
        data = _json(body)
        assert "key" in data

    def test_set_and_read_setting(self, minidb):
        """Запись и чтение setting через API — на миникопии БД."""
        r = minidb["client"].put("/api/settings/test_e2e", json={
            "value": "test_value_123"
        })
        assert r.status_code == 200
        r2 = minidb["client"].get("/api/settings/test_e2e")
        assert r2.status_code == 200
        assert r2.json().get("value") == "test_value_123"
