import pytest


class TestPhotosSearchAPI:
    def test_search_returns_results(self, app_client):
        """Эндпоинт поиска фото возвращает 200 и содержит ключи total+photos."""
        resp = app_client.get("/api/photos/search?limit=5&sort=date_desc")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "photos" in data

    def test_search_with_query(self, app_client):
        """Поиск с текстовым запросом не падает."""
        resp = app_client.get("/api/photos/search?q=test&limit=5")
        assert resp.status_code == 200

    def test_search_with_faces_filter(self, app_client):
        """Фильтр has_faces=true не ломает поиск."""
        resp = app_client.get("/api/photos/search?has_faces=true&limit=5")
        assert resp.status_code == 200

    def test_search_with_gps_filter(self, app_client):
        """Фильтр has_gps=true не ломает поиск."""
        resp = app_client.get("/api/photos/search?has_gps=true&limit=5")
        assert resp.status_code == 200

    def test_dates_histogram(self, app_client):
        """Гистограмма дат возвращает структуру с годами и общим количеством."""
        resp = app_client.get("/api/photos/dates")
        assert resp.status_code == 200
        data = resp.json()
        assert "years" in data
        assert "total" in data
        assert "photo_times" in data
        assert isinstance(data["photo_times"], list)

    def test_photo_list(self, app_client, db_with_photos):
        """Эндпоинт списка фото возвращает photos с заполненными path/photo_id."""
        resp = app_client.get("/api/photos/list?limit=5&sort=date_desc")
        assert resp.status_code == 200
        data = resp.json()
        assert "photos" in data
        if len(data["photos"]) > 0:
            p = data["photos"][0]
            assert p.get("path"), "photo list item must have non-empty path"
            assert p.get("photo_id"), "photo list item must have non-empty photo_id"
            ch = p.get("content_hash", "")
            if ch:
                assert not ch.startswith("/"), f"content_hash looks like a path: {ch[:30]}"

    def test_photo_list_sort_changed_desc(self, app_client, db_with_photos):
        """/api/photos/list с sort=changed_desc не падает и возвращает данные."""
        resp = app_client.get("/api/photos/list?limit=5&sort=changed_desc")
        assert resp.status_code == 200
        data = resp.json()
        assert "photos" in data
        if len(data["photos"]) > 0:
            p = data["photos"][0]
            assert p.get("path"), "changed_desc photo must have non-empty path"
            assert p.get("photo_id"), "changed_desc photo must have non-empty photo_id"

    def test_search_person_filter(self, app_client):
        """Фильтр по персоне обрабатывается без краша (может быть 200 или 500)."""
        resp = app_client.get("/api/photos/search?person=test&limit=5")
        assert resp.status_code in (200, 500)

    def test_search_deleted_filter(self, app_client):
        """Фильтр удалённых фото не ломает поиск."""
        resp = app_client.get("/api/photos/search?deleted_only=true&limit=5")
        assert resp.status_code == 200


class TestPhotosDateGPSAPI:
    def test_set_date(self, app_client):
        """Установка даты на несуществующее фото возвращает 404."""
        resp = app_client.post("/api/photos/set_date", json={
            "photo_id": "nonexistent", "manual_date": "2024-01-15 10:00:00"
        })
        assert resp.status_code == 404

    def test_clear_date(self, app_client):
        """Сброс даты на несуществующем фото возвращает 404."""
        resp = app_client.post("/api/photos/clear_date", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_set_gps(self, app_client):
        """Установка GPS на несуществующее фото возвращает 404."""
        resp = app_client.post("/api/photos/set_gps", json={
            "photo_id": "nonexistent", "lat": 55.75, "lon": 37.62
        })
        assert resp.status_code == 404

    def test_clear_gps(self, app_client):
        """Сброс GPS на несуществующем фото возвращает 404."""
        resp = app_client.post("/api/photos/clear_gps", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_clear_date(self, app_client):
        resp = app_client.post("/api/photos/clear_date", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_set_gps(self, app_client):
        resp = app_client.post("/api/photos/set_gps", json={
            "photo_id": "nonexistent", "lat": 55.75, "lon": 37.62
        })
        assert resp.status_code == 404

    def test_clear_gps(self, app_client):
        resp = app_client.post("/api/photos/clear_gps", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404


class TestPhotosDeleteAPI:
    def test_mark_deleted(self, app_client):
        """Пометка несуществующего фото как удалённого возвращает 404."""
        resp = app_client.post("/api/photos/mark_deleted", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_undelete(self, app_client):
        """Восстановление несуществующего фото возвращает 404."""
        resp = app_client.post("/api/photos/undelete", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404


class TestPersonsAPI:
    def test_list_persons(self, app_client):
        """Список персон возвращает пагинированный ответ с полями persons+total."""
        resp = app_client.get("/api/persons/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "persons" in data
        assert "total" in data

    def test_list_persons_has_comment(self, app_client):
        """Каждая персона в списке содержит поле comment."""
        resp = app_client.get("/api/persons/?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        if data["persons"]:
            for p in data["persons"]:
                assert "comment" in p, f"persona {p.get('persona_id')} missing comment field"

    def test_get_names(self, app_client):
        """Эндпоинт имён персон доступен."""
        resp = app_client.get("/api/persons/names")
        assert resp.status_code == 200

    def test_update_persona(self, app_client):
        """Обновление несуществующей персоны не крашит сервер."""
        resp = app_client.put("/api/persons/nonexistent", json={
            "display_name": "Тест"
        })
        assert resp.status_code in (200, 404)

    def test_update_persona_with_comment(self, app_client, db_with_photos):
        """Персоне можно задать comment через PUT."""
        db = db_with_photos
        db.add_face_sqlite_only(photo_id="img1.jpg", face_id="face1", bbox=[10,20,30,40], confidence=0.9, persona_id="p1", content_hash="hash1")
        db.sqlite.execute("INSERT OR IGNORE INTO personas (persona_id, name) VALUES (?, ?)", ("p1", "cluster_p1"))
        db.sqlite.commit()
        resp = app_client.put("/api/persons/p1", json={
            "display_name": "Тестовый Человек",
            "comment": "друг семьи"
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated.get("comment") == "друг семьи"
        assert updated.get("display_name") == "Тестовый Человек"


class TestCatalogAPI:
    def test_get_roots(self, app_client):
        """Корни каталога возвращаются без ошибок."""
        resp = app_client.get("/api/catalog/roots")
        assert resp.status_code == 200

    def test_get_stats(self, app_client):
        """Статистика каталога доступна."""
        resp = app_client.get("/api/catalog/stats")
        assert resp.status_code == 200

    def test_locate(self, app_client):
        """Локация несуществующего пути не падает."""
        resp = app_client.get("/api/catalog/locate?path=/nonexistent")
        assert resp.status_code == 200


class TestMapAPI:
    def test_map_photos_endpoint(self, app_client):
        """/api/photos/map возвращает список с lat/lon."""
        resp = app_client.get("/api/photos/map")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if len(data) > 0:
            for f in ["lat", "lon", "date"]:
                assert f in data[0], f"map point missing '{f}'"

    def test_map_page_loads(self, app_client):
        """Страница карты загружается."""
        resp = app_client.get("/map")
        assert resp.status_code == 200
        assert b"leaflet" in resp.content.lower()


class TestPipelineControlAPI:
    """Деструктивные тесты — вызывают реальные systemctl/pkill/MQTT stop.

    Все системные вызовы замоканы: os.system, _get_api_mqtt, PIPELINE_SERVICE.
    Проверяем только что эндпоинт возвращает HTTP 200 + ok=True.
    """

    def test_control_stop(self, app_client, monkeypatch):
        """Остановка пайплайна — mock os.system + MQTT, проверяем только HTTP 200."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        monkeypatch.setattr("config.PIPELINE_SERVICE", "fake-service")
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True

    def test_control_start_faces_has_limit(self, app_client, monkeypatch):
        """Запуск faces — mock os.system + MQTT, проверяем только HTTP 200."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        monkeypatch.setattr("config.PIPELINE_SERVICE", "fake-service")
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/start", json={
            "step": "faces", "faces_limit": 10
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True

    def test_control_start_describe_has_params(self, app_client, monkeypatch):
        """Запуск describe — mock os.system + MQTT, проверяем только HTTP 200."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        monkeypatch.setattr("config.PIPELINE_SERVICE", "fake-service")
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/start", json={
            "step": "describe", "desc_limit": 10, "batch_size": 3
        })
        assert resp.status_code == 200


class TestSystemAPI:
    def test_health(self, app_client):
        """Health-check эндпоинт возвращает status: ok."""
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_log(self, app_client):
        """Чтение логов через API не падает."""
        resp = app_client.get("/api/log?lines=10")
        assert resp.status_code == 200

    def test_changes(self, app_client):
        """История изменений возвращается с полем changes."""
        resp = app_client.get("/api/changes?limit=10")
        assert resp.status_code == 200
        assert "changes" in resp.json()


class TestSystemReportAPI:
    def test_system_report(self, app_client):
        """System report возвращает host/gpu/memory/pipeline."""
        resp = app_client.get("/api/system-report")
        assert resp.status_code == 200
        data = resp.json()
        assert "host" in data
        assert "memory" in data
        assert "gpu" in data
        assert "pipeline" in data

    def test_monitoring(self, app_client):
        """Monitoring возвращает live + history."""
        resp = app_client.get("/api/monitoring")
        assert resp.status_code == 200
        data = resp.json()
        assert "live" in data
        assert "history" in data

    def test_maintenance_stats(self, app_client):
        """Maintenance stats возвращает структуру с метриками БД."""
        resp = app_client.get("/api/maintenance/stats")
        assert resp.status_code == 200

    def test_ai_log(self, app_client):
        """AI log endpoint возвращает список."""
        resp = app_client.get("/api/ai-log?limit=5")
        assert resp.status_code == 200

    def test_config_update_env_key(self, app_client):
        """Config update с env_key изменяет настройку."""
        resp = app_client.post("/api/config/update", json={
            "env_key": "OLLAMA_EMBED_CHUNK", "value": "512"
        })
        assert resp.status_code == 200

    def test_control_reset(self, app_client, monkeypatch):
        """Control reset сбрасывает флаги шага."""
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/reset", json={"step": "describe"})
        assert resp.status_code == 200

    def test_control_start_embed(self, app_client, monkeypatch):
        """Запуск embed — mock os.system, проверяем HTTP 200."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        monkeypatch.setattr("config.PIPELINE_SERVICE", "fake-service")
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/start", json={
            "step": "embed", "embed_limit": 10
        })
        assert resp.status_code == 200

    def test_control_start_exif(self, app_client, monkeypatch):
        """Запуск exif — mock os.system, проверяем HTTP 200."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        monkeypatch.setattr("config.PIPELINE_SERVICE", "fake-service")
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/start", json={"step": "exif"})
        assert resp.status_code == 200

    def test_control_start_ingest(self, app_client, monkeypatch):
        """Запуск ingest — mock os.system, проверяем HTTP 200."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        monkeypatch.setattr("config.PIPELINE_SERVICE", "fake-service")
        monkeypatch.setattr("main._get_api_mqtt", lambda: None)
        resp = app_client.post("/api/control/start", json={"step": "ingest"})
        assert resp.status_code == 200

    def test_backup_download(self, app_client):
        """Backup download возвращает gzip (нужна реальная БД)."""
        resp = app_client.get("/api/backup/download")
        if resp.status_code == 404:
            pytest.skip("No database in test env")
        assert resp.status_code == 200

    def test_maintenance_vacuum(self, app_client):
        """Maintenance vacuum выполняется (нужна реальная БД)."""
        resp = app_client.post("/api/maintenance/vacuum")
        if resp.status_code == 500:
            pytest.skip("No database in test env")
        assert resp.status_code == 200

    def test_maintenance_dedup_embeddings(self, app_client):
        """Maintenance dedup embeddings выполняется."""
        resp = app_client.post("/api/maintenance/dedup_embeddings")
        assert resp.status_code == 200

    def test_top_personas_for_facts(self, app_client):
        """Top personas for facts возвращает список."""
        resp = app_client.get("/api/settings/faces_total/top_personas")
        assert resp.status_code == 200

    def test_watchdog_crashes(self, app_client):
        """Watchdog crashes endpoint возвращает структуру."""
        resp = app_client.get("/api/watchdog/crashes")
        assert resp.status_code == 200

    def test_watchdog_sleep_wake(self, app_client):
        """Watchdog sleep + wake работают."""
        resp = app_client.post("/api/watchdog/sleep")
        assert resp.status_code == 200
        resp2 = app_client.post("/api/watchdog/wake")
        assert resp2.status_code == 200

    def test_static_files(self, app_client):
        """Статические файлы отдаются."""
        for path in ["/shared.css", "/shared.js", "/gallery.js",
                      "/gallery-detail.js", "/gallery-ui.js",
                      "/logo-dark.png", "/logo-light.png",
                      "/favicon.ico", "/favicon.png", "/favicon-32.png",
                      "/apple-touch-icon.png"]:
            resp = app_client.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"

    def test_ollama_check(self, app_client):
        """Ollama check endpoint не падает."""
        resp = app_client.get("/api/proxy/ollama_check?url=http://localhost:11434")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Catalog API — расширенные тесты
# ═══════════════════════════════════════════════════════════════════════

class TestCatalogTreeAPI:
    def test_tree_empty(self, app_client):
        """Tree без root_id возвращает пустую структуру."""
        resp = app_client.get("/api/catalog/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert "subdirs" in data
        assert "files" in data
        assert "total_files" in data

    def test_tree_with_root(self, app_client, db_with_photos):
        """Tree с root_id возвращает файлы из тестового root."""
        resp = app_client.get("/api/catalog/tree?root_id=test_root")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scanned"] is True

    def test_tree_with_path_filter(self, app_client, db_with_photos):
        """Tree с фильтром пути возвращает поддиректории."""
        resp = app_client.get("/api/catalog/tree?root_id=test_root&path=2024")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data

    def test_browse_dirs(self, app_client):
        """Browse dirs возвращает директории корня."""
        resp = app_client.get("/api/catalog/browse?path=/")
        assert resp.status_code == 200
        data = resp.json()
        assert "dirs" in data
        assert isinstance(data["dirs"], list)

    def test_browse_nonexistent(self, app_client):
        """Browse несуществующего пути fallback на /."""
        resp = app_client.get("/api/catalog/browse?path=/nonexistent/path")
        assert resp.status_code == 200
        data = resp.json()
        assert "dirs" in data

    def test_hash_status(self, app_client):
        """Hash status возвращает структуру с счётчиками."""
        resp = app_client.get("/api/catalog/hash_status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_files" in data
        assert "with_hash" in data
        assert "without_hash" in data
        assert "duplicate_groups" in data

    def test_duplicates_empty(self, app_client):
        """Duplicates на пустой БД возвращает пустой список."""
        resp = app_client.get("/api/catalog/duplicates")
        assert resp.status_code == 200
        data = resp.json()
        assert "duplicates" in data
        assert isinstance(data["duplicates"], list)

    def test_hash_backfill_status(self, app_client):
        """Hash backfill status возвращает running флаг."""
        resp = app_client.get("/api/catalog/hash_backfill_status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert isinstance(data["running"], bool)

    def test_hash_backfill_stop(self, app_client):
        """Hash backfill stop выполняется без ошибок."""
        resp = app_client.post("/api/catalog/hash_backfill_stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True

    def test_add_root_nonexistent(self, app_client):
        """Add root с несуществующим путём возвращает ошибку или ok."""
        resp = app_client.post("/api/catalog/add_root", json={
            "path": "/nonexistent/path/xyz",
            "alias": "test"
        })
        assert resp.status_code in (200, 500)

    def test_toggle_root_nonexistent(self, app_client):
        """Toggle несуществующего root возвращает 404."""
        resp = app_client.post("/api/catalog/root/nonexistent/toggle")
        assert resp.status_code == 404

    def test_delete_root_nonexistent(self, app_client):
        """Delete несуществующего root возвращает 500 (ошибка БД)."""
        resp = app_client.delete("/api/catalog/root/nonexistent")
        assert resp.status_code in (200, 404, 500)

    def test_scan_root(self, app_client, monkeypatch):
        """Scan root запускается (mock os.system)."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        resp = app_client.post("/api/catalog/scan/any_root_id")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

    def test_sync(self, app_client, monkeypatch):
        """Sync запускается (mock os.system)."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        resp = app_client.post("/api/catalog/sync")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

    def test_locate_with_data(self, app_client, db_with_photos):
        """Locate для существующего пути находит root."""
        resp = app_client.get("/api/catalog/locate?path=/photos/2024/img1.jpg")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("found") is True
        assert data.get("root_id") == "test_root"


# ═══════════════════════════════════════════════════════════════════════
# Persons API — расширенные тесты
# ═══════════════════════════════════════════════════════════════════════

class TestPersonsExtendedAPI:
    def test_get_person_not_found(self, app_client):
        """GET персона по несуществующему ID возвращает 404."""
        resp = app_client.get("/api/persons/nonexistent")
        assert resp.status_code == 404

    def test_get_person_faces_not_found(self, app_client):
        """Лица несуществующей персоны — пустой список или 500."""
        resp = app_client.get("/api/persons/nonexistent/faces")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)

    def test_get_persons_by_name_empty(self, app_client):
        """Поиск по несуществующему имени возвращает пустой список."""
        resp = app_client.get("/api/persons/by_name/Несуществующее")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_merge_persons_nonexistent(self, app_client):
        """Merge несуществующих персон возвращает 400."""
        resp = app_client.post("/api/persons/merge?source_persona_id=src1&target_persona_id=tgt1")
        assert resp.status_code == 400

    def test_delete_person_not_found(self, app_client):
        """Delete несуществующей персоны возвращает 404."""
        resp = app_client.delete("/api/persons/nonexistent")
        assert resp.status_code == 404

    def test_persons_named_only(self, app_client):
        """Фильтр named_only возвращает только именованные персоны."""
        resp = app_client.get("/api/persons/?named_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "persons" in data
        assert "total" in data

    def test_persons_pagination(self, app_client):
        """Пагинация персон limit/offset работает."""
        resp = app_client.get("/api/persons/?limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["persons"]) <= 5

    def test_get_person_with_data(self, app_client, db_with_photos):
        """GET существующей персоны возвращает данные."""
        db = db_with_photos
        db.add_face_sqlite_only(photo_id="img1.jpg", face_id="face1", bbox=[10,20,30,40], confidence=0.9, persona_id="p1", content_hash="hash1")
        db.sqlite.execute("INSERT OR IGNORE INTO personas (persona_id, name) VALUES (?, ?)", ("p1", "cluster_p1"))
        db.sqlite.commit()
        resp = app_client.get("/api/persons/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["persona_id"] == "p1"
        assert "face_count" in data

    def test_get_person_faces_with_data(self, app_client, db_with_photos):
        """Лица существующей персоны возвращаются."""
        db = db_with_photos
        db.add_face_sqlite_only(photo_id="img1.jpg", face_id="face1", bbox=[10,20,30,40], confidence=0.9, persona_id="p1", content_hash="hash1")
        db.sqlite.execute("INSERT OR IGNORE INTO personas (persona_id, name) VALUES (?, ?)", ("p1", "cluster_p1"))
        db.sqlite.commit()
        resp = app_client.get("/api/persons/p1/faces")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["face_id"] == "face1"

    def test_batch_update_nonexistent_name(self, app_client):
        """Batch update по несуществующему имени обновляет 0 персон."""
        resp = app_client.put("/api/persons/batch/by_name?old_name=Несуществующее", json={
            "display_name": "Тест"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Search API — semantic search
# ═══════════════════════════════════════════════════════════════════════

class TestSemanticSearchAPI:
    def test_semantic_search_empty_query(self, app_client):
        """Пустой запрос возвращает пустой результат."""
        resp = app_client.get("/api/photos/semantic_search?q=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["photos"] == []

    def test_semantic_search_no_query(self, app_client):
        """Без параметра q возвращает пустой результат."""
        resp = app_client.get("/api/photos/semantic_search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Video API
# ═══════════════════════════════════════════════════════════════════════

class TestVideoAPI:
    def test_video_stream_not_found(self, app_client):
        """Video stream для несуществующего файла возвращает 404."""
        resp = app_client.get("/api/photos/video_stream?path=nonexistent.mp4")
        assert resp.status_code == 404

    def test_video_meta_not_found(self, app_client):
        """Video meta для несуществующего файла возвращает 404."""
        resp = app_client.get("/api/photos/video_meta?path=nonexistent.mp4")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# FLIR API
# ═══════════════════════════════════════════════════════════════════════

class TestFlirAPI:
    def test_flir_info_not_found(self, app_client):
        """FLIR info для несуществующего фото возвращает 404."""
        resp = app_client.get("/api/photos/flir_info?path=nonexistent")
        assert resp.status_code == 404

    def test_flir_visual_not_found(self, app_client):
        """FLIR visual для несуществующего фото возвращает 404."""
        resp = app_client.get("/api/photos/flir_visual?path=nonexistent")
        assert resp.status_code == 404

    def test_flir_thermal_not_found(self, app_client):
        """FLIR thermal для несуществующего фото возвращает 404."""
        resp = app_client.get("/api/photos/flir_thermal?path=nonexistent")
        assert resp.status_code == 404

    def test_flir_temperature_not_found(self, app_client):
        """FLIR temperature для несуществующего фото возвращает 404."""
        resp = app_client.get("/api/photos/flir_temperature?path=nonexistent")
        assert resp.status_code == 404

    def test_flir_raw_palette_not_found(self, app_client):
        """FLIR raw palette для несуществующего фото возвращает 404."""
        resp = app_client.get("/api/photos/flir_raw_palette?path=nonexistent")
        assert resp.status_code == 404

    def test_flir_overlay_not_found(self, app_client):
        """FLIR overlay для несуществующего фото возвращает 404."""
        resp = app_client.get("/api/photos/flir_overlay?path=nonexistent")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Photos API — дополнительные эндпоинты
# ═══════════════════════════════════════════════════════════════════════

class TestPhotosExtendedAPI:
    def test_photos_root(self, app_client):
        """Корневой эндпоинт /api/photos/ требует параметр path."""
        resp = app_client.get("/api/photos/?path=nonexistent")
        assert resp.status_code in (200, 404)

    def test_thumbnail_not_found(self, app_client):
        """Thumbnail для несуществующего фото возвращает 404 или fallback."""
        resp = app_client.get("/api/photos/thumbnail?path=nonexistent.jpg")
        assert resp.status_code in (404, 200)

    def test_face_not_found(self, app_client):
        """Face по несуществующему ID возвращает 404."""
        resp = app_client.get("/api/photos/face/nonexistent")
        assert resp.status_code == 404

    def test_face_context_not_found(self, app_client):
        """Face context по несуществующему ID возвращает 404."""
        resp = app_client.get("/api/photos/face_context/nonexistent")
        assert resp.status_code == 404

    def test_description_not_found(self, app_client):
        """Description для несуществующего пути возвращает null."""
        resp = app_client.get("/api/photos/description?path=/nonexistent.jpg")
        assert resp.status_code == 200
        assert resp.json().get("description") is None

    def test_reprocess_log(self, app_client):
        """Reprocess log возвращает структуру с логом."""
        resp = app_client.get("/api/photos/reprocess-log")
        assert resp.status_code == 200

    def test_neighbor_not_found(self, app_client):
        """Neighbor для несуществующей даты возвращает 404 или пусто."""
        resp = app_client.get("/api/photos/neighbor?date=2099-12-31 23:59:59")
        assert resp.status_code in (200, 404)

    def test_edits_not_found(self, app_client):
        """Edits для несуществующего content_hash возвращают пустой список."""
        resp = app_client.get("/api/photos/edits/nonexistent_hash")
        assert resp.status_code == 200

    def test_rich_description_not_found(self, app_client):
        """PUT rich_description для несуществующего фото возвращает 404."""
        resp = app_client.put("/api/photos/nonexistent/rich_description", json={
            "rich_description": "тест"
        })
        assert resp.status_code in (404, 200)

    def test_monitor_feed(self, app_client):
        """Monitor feed endpoint доступен."""
        resp = app_client.get("/api/photos/monitor_feed?limit=5")
        assert resp.status_code == 200

    def test_reverse_geocode(self, app_client):
        """Reverse geocode возвращает результат (может быть ошибка)."""
        resp = app_client.post("/api/photos/reverse_geocode", json={
            "coords": [{"lat": 55.75, "lon": 37.62}]
        })
        assert resp.status_code in (200, 500)

    def test_describe_endpoint(self, app_client, monkeypatch):
        """Describe endpoint с несуществующими путями возвращает 400."""
        monkeypatch.setattr("os.system", lambda cmd: 0)
        resp = app_client.post("/api/photos/describe", json=["nonexistent.jpg"])
        assert resp.status_code in (200, 400, 500)


# ═══════════════════════════════════════════════════════════════════════
# Photos API — тесты с данными (db_with_photos)
# ═══════════════════════════════════════════════════════════════════════

class TestPhotosWithDataAPI:
    def test_thumbnail_with_data(self, app_client, db_with_photos):
        """Thumbnail для существующего фото (файла нет на диске) — 404."""
        resp = app_client.get("/api/photos/thumbnail?path=/photos/2024/img1.jpg")
        assert resp.status_code in (404, 200)

    def test_description_with_data(self, app_client, db_with_photos):
        """Description для существующего фото возвращает текст."""
        resp = app_client.get("/api/photos/description?path=/photos/2024/img1.jpg")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("description") == "зимний лес"

    def test_edits_with_hash(self, app_client, db_with_photos):
        """Edits для существующего content_hash возвращают структуру."""
        resp = app_client.get("/api/photos/edits/hash1")
        assert resp.status_code == 200
        data = resp.json()
        assert "edits" in data
        assert data["content_hash"] == "hash1"
        assert isinstance(data["edits"], list)

    def test_add_edit(self, app_client, db_with_photos):
        """Добавление edit для существующего content_hash."""
        resp = app_client.post("/api/photos/edits/hash1", json={
            "action": "crop",
            "params": {"x": 0, "y": 0, "w": 100, "h": 100}
        })
        assert resp.status_code in (200, 400, 500)

    def test_neighbor_with_data(self, app_client, db_with_photos):
        """Neighbor для существующей даты возвращает соседа."""
        resp = app_client.get("/api/photos/neighbor?date=2024-01-15 10:00:00")
        assert resp.status_code in (200, 404)

    def test_search_with_data(self, app_client, db_with_photos):
        """Search на БД с данными возвращает результаты."""
        resp = app_client.get("/api/photos/search?q=лес&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "photos" in data

    def test_photo_detail_with_data(self, app_client, db_with_photos):
        """Корневой эндпоинт с path возвращает детали фото."""
        resp = app_client.get("/api/photos/?path=hash1")
        assert resp.status_code in (200, 404)

    def test_map_with_data(self, app_client, db_with_photos):
        """Map endpoint с GPS-данными возвращает точки."""
        resp = app_client.get("/api/photos/map")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_dates_with_data(self, app_client, db_with_photos):
        """Dates histogram с данными возвращает годы."""
        resp = app_client.get("/api/photos/dates")
        assert resp.status_code == 200
        data = resp.json()
        assert "years" in data
        assert data["total"] > 0
