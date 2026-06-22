import pytest


class TestDatabaseInit:
    def test_creates_tables(self, db):
        """При инициализации создаются все необходимые таблицы."""
        cur = db.sqlite.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        assert "photos" in tables
        assert "faces" in tables
        assert "personas" in tables
        assert "catalog_roots" in tables
        assert "catalog_files" in tables
        assert "changes" in tables

    def test_migrations_applied(self, db):
        """Миграции добавили колонки manual_gps, manual_date, deleted."""
        cur = db.sqlite.cursor()
        cur.execute("PRAGMA table_info(photos)")
        columns = {row[1] for row in cur.fetchall()}
        assert "manual_gps" in columns
        assert "manual_date" in columns
        assert "deleted" in columns


class TestPhotoCRUD:
    def test_add_photo(self, db):
        """Добавление фото сохраняет путь и описание."""
        pid = db.add_photo("/test/photo.jpg", date="2024-01-01 12:00:00",
                           description="тест")
        assert pid
        photo = db.get_photo(pid)
        assert photo is not None
        assert photo["path"] == "/test/photo.jpg"
        assert photo["description"] == "тест"

    def test_add_photo_with_gps(self, db):
        """Добавление фото с GPS сохраняет координаты."""
        pid = db.add_photo("/gps.jpg", gps={"lat": 55.75, "lon": 37.62})
        photo = db.get_photo(pid)
        assert abs(photo["gps_lat"] - 55.75) < 0.01

    def test_add_photo_with_camera(self, db):
        """Добавление фото с информацией о камере сохраняет марку."""
        pid = db.add_photo("/cam.jpg", camera={"make": "Nikon", "model": "D850"})
        photo = db.get_photo(pid)
        assert photo["camera_make"] == "Nikon"

    def test_get_photo_nonexistent(self, db):
        """Запрос несуществующего фото возвращает None без ошибок."""
        assert db.get_photo("nonexistent-id") is None

    def test_get_photo_by_path(self, db):
        """Поиск фото по пути находит только что добавленное."""
        db.add_photo("/unique/path.jpg", date="2024-01-01")
        photo = db.get_photo_by_path("/unique/path.jpg")
        assert photo is not None

    def test_count_photos(self, db):
        """Счётчик фото правильно считает добавленные записи."""
        db.add_photo("/1.jpg")
        db.add_photo("/2.jpg")
        assert db.count_photos() == 2

    def test_get_all_photos(self, db):
        """get_all_photos возвращает только canonical файлы из catalog."""
        db.add_catalog_root("r1", "/test", alias="test")
        db.add_catalog_files_batch([
            {"file_id": "f1", "root_id": "r1", "rel_path": "a.jpg", "abs_path": "/a.jpg", "ext": ".jpg", "is_canonical": 1},
            {"file_id": "f2", "root_id": "r1", "rel_path": "b.jpg", "abs_path": "/b.jpg", "ext": ".jpg", "is_canonical": 1},
        ])
        db.add_photo("/a.jpg")
        db.add_photo("/b.jpg")
        all_photos = db.get_all_photos()
        assert len(all_photos) == 2


class TestPhotoSearch:
    def test_search_basic(self, db_with_photos):
        """Базовый поиск возвращает фото и корректный total."""
        total, photos = db_with_photos.search_photos(limit=10)
        assert total >= 3
        assert len(photos) >= 1

    def test_search_by_text(self, db_with_photos):
        """Поиск по тексту находит фото с указанным словом в описании."""
        total, photos = db_with_photos.search_photos(q="зимний")
        assert total >= 1
        assert "зимний" in photos[0]["description"]

    def test_search_with_faces_filter(self, db_with_photos):
        """Фильтр has_faces=True возвращает только фото с лицами."""
        total, photos = db_with_photos.search_photos(has_faces=True)
        assert total >= 1
        for p in photos:
            assert p["faces_present"] == 1

    def test_search_with_gps_filter(self, db_with_photos):
        """Фильтр has_gps=True находит фото с координатами."""
        total, photos = db_with_photos.search_photos(has_gps=True)
        assert total >= 1

    def test_search_date_range(self, db_with_photos):
        """Фильтр по диапазону дат ограничивает результаты."""
        total, photos = db_with_photos.search_photos(
            date_from="2024-01-01", date_to="2024-12-31")
        assert total >= 1

    def test_search_sort_asc(self, db_with_photos):
        """Сортировка date_asc: более ранние фото идут первыми."""
        total, photos = db_with_photos.search_photos(sort="date_asc", limit=10)
        if len(photos) >= 2:
            assert photos[0]["date"] <= photos[1]["date"]

    def test_search_sort_desc(self, db_with_photos):
        """Сортировка date_desc: более поздние фото идут первыми."""
        total, photos = db_with_photos.search_photos(sort="date_desc", limit=10)
        if len(photos) >= 2:
            assert photos[0]["date"] >= photos[1]["date"]

    def test_search_by_person(self, db_with_photos):
        """Поиск по имени персоны находит фото с этим человеком."""
        db_with_photos.add_persona("p1", "cluster_1", display_name="Анна")
        db_with_photos.add_face_sqlite_only(
            "/photos/2024/img1.jpg", [100, 200, 300, 400], 0.95, persona_id="p1")
        total, photos = db_with_photos.search_photos(person="Анна")
        assert total >= 1


class TestDateHistogram:
    def test_histogram(self, db_with_photos):
        """Гистограмма дат содержит структуру years+months и корректный total."""
        hist = db_with_photos.get_date_histogram()
        assert "years" in hist
        assert "months" in hist
        assert "total" in hist
        assert hist["total"] >= 3


class TestPhotoUpdate:
    def test_update_description(self, db):
        """Обновление description меняет значение в базе."""
        pid = db.add_photo("/up.jpg", description="старое")
        db.update_photo(pid, description="новое")
        photo = db.get_photo(pid)
        assert photo["description"] == "новое"

    def test_update_rich_description(self, db):
        """Обновление rich_description отдельно от обычного."""
        pid = db.add_photo("/rich.jpg")
        db.update_photo(pid, rich_description="обогащённое описание")
        photo = db.get_photo(pid)
        assert photo["rich_description"] == "обогащённое описание"

    def test_soft_delete(self, db):
        """Мягкое удаление: deleted=1, запись остаётся."""
        pid = db.add_photo("/del.jpg")
        db.update_photo(pid, deleted=1)
        photo = db.get_photo(pid)
        assert photo["deleted"] == 1

    def test_update_manual_date(self, db):
        """Ручная дата сохраняется отдельно от автоматической."""
        pid = db.add_photo("/md.jpg", date="2024-01-01 12:00:00")
        db.update_photo(pid, manual_date="2023-06-15 10:00:00")
        photo = db.get_photo(pid)
        assert photo["manual_date"] == "2023-06-15 10:00:00"


class TestFaceCRUD:
    def test_add_face(self, db):
        """Добавление лица к фото возвращает face_id."""
        pid = db.add_photo("/face_test.jpg")
        fid, inserted = db.add_face_sqlite_only(
            pid, [100, 200, 300, 400], 0.9, persona_id="p1")
        assert fid
        assert inserted

    def test_add_face_duplicate_ignored(self, db):
        """Повторное добавление того же face_id игнорируется."""
        pid = db.add_photo("/face_dup.jpg")
        fid1, ins1 = db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.8, face_id="face123")
        fid2, ins2 = db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.8, face_id="face123")
        assert ins1 is True
        assert ins2 is False

    def test_get_face(self, db):
        """Получение лица по id возвращает корректную confidence."""
        pid = db.add_photo("/gf.jpg")
        fid, _ = db.add_face_sqlite_only(pid, [50, 60, 150, 200], 0.95)
        face = db.get_face(fid)
        assert face is not None
        assert face["confidence"] == 0.95

    def test_get_faces_for_photo(self, db):
        """Все лица одного фото возвращаются одним запросом."""
        pid = db.add_photo("/fph.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9)
        db.add_face_sqlite_only(pid, [100, 200, 300, 400], 0.85)
        faces = db.get_faces_for_photo(pid)
        assert len(faces) == 2

    def test_count_faces(self, db):
        """Счётчик лиц корректно учитывает добавленные записи."""
        pid = db.add_photo("/cf.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9)
        assert db.count_faces() >= 1


class TestPersonaCRUD:
    def test_add_persona(self, db):
        """Добавление персоны с именем успешно."""
        ok = db.add_persona("p1", "cluster_1", display_name="Иван")
        assert ok

    def test_add_persona_duplicate_ignored(self, db):
        """Дубликат persona_id не создаёт вторую запись."""
        db.add_persona("p1", "cluster_1", display_name="Иван")
        db.add_persona("p1", "cluster_1", display_name="Иван")
        all_p = db.get_all_personas()
        assert sum(1 for p in all_p if p["persona_id"] == "p1") == 1

    def test_get_persona(self, db):
        """Получение персоны по id возвращает display_name."""
        db.add_persona("p2", "cluster_2", display_name="Мария")
        p = db.get_persona("p2")
        assert p["display_name"] == "Мария"

    def test_get_all_personas(self, db):
        """Все персоны возвращаются списком."""
        db.add_persona("p3", "cluster_3")
        db.add_persona("p4", "cluster_4")
        all_p = db.get_all_personas()
        assert len(all_p) >= 2

    def test_update_persona(self, db):
        """Обновление display_name и comment персоны."""
        db.add_persona("p5", "cluster_5")
        result = db.update_persona("p5", display_name="Пётр", comment="друг")
        assert result["display_name"] == "Пётр"
        assert result["comment"] == "друг"

    def test_update_persona_clear_name(self, db):
        """Очистка display_name через clear_display_name=True."""
        db.add_persona("p6", "cluster_6", display_name="Старое")
        result = db.update_persona("p6", clear_display_name=True)
        assert result["display_name"] is None

    def test_get_display_names(self, db):
        """Список имён содержит display_name всех персон."""
        db.add_persona("p7", "cluster_7", display_name="Анна")
        db.add_persona("p8", "cluster_8", display_name="Борис")
        names = db.get_display_names()
        assert "Анна" in names
        assert "Борис" in names

    def test_get_personas_by_name(self, db):
        """Поиск персон по имени находит все с одинаковым именем."""
        db.add_persona("p9", "cluster_9", display_name="Общее имя")
        db.add_persona("p10", "cluster_10", display_name="Общее имя")
        result = db.get_personas_by_name("Общее имя")
        assert len(result) == 2

    def test_merge_personas(self, db):
        """Слияние переносит лица из source в target, source удаляется."""
        db.add_persona("src", "src_cluster", display_name="Старое")
        db.add_persona("tgt", "tgt_cluster", display_name="Новое")
        pid = db.add_photo("/merge.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9, persona_id="src")
        ok = db.merge_personas("src", "tgt")
        assert ok
        assert db.get_persona("src") is None
        faces = db.get_faces_for_persona("tgt")
        assert len(faces) >= 1

    def test_face_count_map(self, db):
        """face_count_map возвращает количество лиц по persona_id."""
        db.add_persona("fc1", "fc_cluster1")
        pid = db.add_photo("/fc.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9, persona_id="fc1")
        db.add_face_sqlite_only(pid, [100, 200, 300, 400], 0.8, persona_id="fc1")
        m = db.face_count_map()
        assert m.get("fc1") == 2


class TestCatalogCRUD:
    def test_add_root(self, db):
        """Добавление корня каталога с alias."""
        db.add_catalog_root("r1", "/mnt/photos", alias="Фотки")
        root = db.get_catalog_root("r1")
        assert root["alias"] == "Фотки"

    def test_get_roots(self, db):
        """Список корней возвращает все добавленные."""
        db.add_catalog_root("r2", "/mnt/photos2")
        roots = db.get_catalog_roots()
        assert len(roots) >= 1

    def test_delete_root(self, db):
        """Удаление корня: после удаления get возвращает None."""
        db.add_catalog_root("r3", "/tmp/x")
        db.delete_catalog_root("r3")
        assert db.get_catalog_root("r3") is None

    def test_add_catalog_files_batch(self, db):
        """Пакетное добавление файлов каталога."""
        db.add_catalog_root("r4", "/mnt/test")
        db.add_catalog_files_batch([
            {"file_id": "f1", "root_id": "r4", "rel_path": "img.jpg",
             "abs_path": "/mnt/test/img.jpg", "parent_dir": "/mnt/test",
             "ext": ".jpg", "size": 1000}
        ])
        files = db.get_catalog_files(root_id="r4")
        assert len(files) == 1

    def test_count_catalog_files(self, db):
        """Счётчик файлов с WHERE-условием."""
        db.add_catalog_root("r5", "/mnt/count")
        db.add_catalog_files_batch([
            {"file_id": "f2", "root_id": "r5", "rel_path": "a.jpg",
             "abs_path": "/mnt/count/a.jpg", "parent_dir": "/mnt/count",
             "ext": ".jpg", "size": 500},
            {"file_id": "f3", "root_id": "r5", "rel_path": "b.jpg",
             "abs_path": "/mnt/count/b.jpg", "parent_dir": "/mnt/count",
             "ext": ".jpg", "size": 600},
        ])
        assert db.count_catalog_files(where="root_id='r5'") == 2


class TestCatalogExtended:
    def test_update_catalog_root(self, db):
        """Обновление root: alias и enabled."""
        db.add_catalog_root("r10", "/mnt/upd", alias="старый")
        db.update_catalog_root("r10", alias="новый", enabled=0)
        root = db.get_catalog_root("r10")
        assert root["alias"] == "новый"
        assert root["enabled"] == 0

    def test_update_catalog_file(self, db):
        """Обновление файла каталога по file_id."""
        db.add_catalog_root("r11", "/mnt/updf")
        db.add_catalog_files_batch([
            {"file_id": "f10", "root_id": "r11", "rel_path": "x.jpg",
             "abs_path": "/mnt/updf/x.jpg", "ext": ".jpg"}
        ])
        db.update_catalog_file("f10", described=1, exif_done=1)
        files = db.get_catalog_files(root_id="r11")
        assert files[0]["described"] == 1
        assert files[0]["exif_done"] == 1

    def test_update_catalog_file_by_path(self, db):
        """Обновление файла каталога по abs_path."""
        db.add_catalog_root("r12", "/mnt/updp")
        db.add_catalog_files_batch([
            {"file_id": "f11", "root_id": "r12", "rel_path": "y.jpg",
             "abs_path": "/mnt/updp/y.jpg", "ext": ".jpg"}
        ])
        db.update_catalog_file_by_path("/mnt/updp/y.jpg", embedded=1)
        files = db.get_catalog_files(root_id="r12")
        assert files[0]["embedded"] == 1

    def test_delete_catalog_file(self, db):
        """Удаление файла каталога по file_id."""
        db.add_catalog_root("r13", "/mnt/del")
        db.add_catalog_files_batch([
            {"file_id": "f12", "root_id": "r13", "rel_path": "z.jpg",
             "abs_path": "/mnt/del/z.jpg", "ext": ".jpg"}
        ])
        db.delete_catalog_file("f12")
        assert db.count_catalog_files(where="root_id='r13'") == 0

    def test_delete_catalog_files_by_root(self, db):
        """Удаление всех файлов root."""
        db.add_catalog_root("r14", "/mnt/delr")
        db.add_catalog_files_batch([
            {"file_id": "f13", "root_id": "r14", "rel_path": "a.jpg",
             "abs_path": "/mnt/delr/a.jpg", "ext": ".jpg"},
            {"file_id": "f14", "root_id": "r14", "rel_path": "b.jpg",
             "abs_path": "/mnt/delr/b.jpg", "ext": ".jpg"},
        ])
        db.delete_catalog_files_by_root("r14")
        assert db.count_catalog_files(where="root_id='r14'") == 0

    def test_get_catalog_file_by_path(self, db):
        """Поиск файла каталога по abs_path."""
        db.add_catalog_root("r15", "/mnt/find")
        db.add_catalog_files_batch([
            {"file_id": "f15", "root_id": "r15", "rel_path": "found.jpg",
             "abs_path": "/mnt/find/found.jpg", "ext": ".jpg", "content_hash": "h1"}
        ])
        f = db.get_catalog_file_by_path("/mnt/find/found.jpg")
        assert f is not None
        assert f["content_hash"] == "h1"

    def test_get_catalog_file_by_path_not_found(self, db):
        """Поиск несуществущего пути возвращает None."""
        assert db.get_catalog_file_by_path("/nonexistent") is None

    def test_add_photos_batch(self, db):
        """Пакетное добавление фото."""
        db.add_photos_batch([
            {"path": "/batch1.jpg", "date": "2024-01-01", "description": "первое"},
            {"path": "/batch2.jpg", "date": "2024-02-01", "description": "второе"},
        ])
        assert db.get_photo_by_path("/batch1.jpg") is not None
        assert db.get_photo_by_path("/batch2.jpg") is not None


class TestEditsCRUD:
    def test_add_and_get_edits(self, db):
        """Добавление edit и получение по content_hash."""
        db.add_edit("hash_edit1", "crop", {"x": 10, "y": 20, "w": 100, "h": 100})
        edits = db.get_edits("hash_edit1")
        assert len(edits) == 1
        assert edits[0]["action"] == "crop"

    def test_add_multiple_edits(self, db):
        """Несколько edits для одного content_hash."""
        db.add_edit("hash_edit2", "crop", {"x": 0})
        db.add_edit("hash_edit2", "rotate", {"angle": 90})
        edits = db.get_edits("hash_edit2")
        assert len(edits) == 2

    def test_remove_edit(self, db):
        """Удаление edit по edit_id."""
        eid = db.add_edit("hash_edit3", "crop", {"x": 5})
        db.remove_edit(eid)
        edits = db.get_edits("hash_edit3")
        assert len(edits) == 0

    def test_clear_edits_by_action(self, db):
        """Очистка edits по action."""
        db.add_edit("hash_edit4", "crop", {"x": 1})
        db.add_edit("hash_edit4", "rotate", {"angle": 90})
        db.clear_edits("hash_edit4", "crop")
        edits = db.get_edits("hash_edit4")
        assert len(edits) == 1
        assert edits[0]["action"] == "rotate"

    def test_clear_all_edits(self, db):
        """Очистка всех edits для content_hash."""
        db.add_edit("hash_edit5", "crop", {"x": 1})
        db.add_edit("hash_edit5", "rotate", {"angle": 90})
        db.clear_edits("hash_edit5")
        assert len(db.get_edits("hash_edit5")) == 0

    def test_get_edits_empty(self, db):
        """Пустой список для несуществующего content_hash."""
        assert db.get_edits("nonexistent") == []


class TestSettings:
    def test_set_and_get_setting(self, db):
        """Установка и получение настройки."""
        db.set_setting("test_key", "test_value")
        assert db.get_setting("test_key") == "test_value"

    def test_get_setting_default(self, db):
        """Получение несуществующей настройки возвращает default."""
        assert db.get_setting("nonexistent", "default") == "default"

    def test_set_setting_overwrite(self, db):
        """Перезапись существующей настройки."""
        db.set_setting("key1", "val1")
        db.set_setting("key1", "val2")
        assert db.get_setting("key1") == "val2"


class TestSystemMetrics:
    def test_insert_and_get_metrics(self, db):
        """Вставка и получение системных метрик."""
        from datetime import datetime
        ts = datetime.now().isoformat()
        db.insert_system_metric({
            "timestamp": ts,
            "cpu_percent": 45.0, "cpu_temp_max": 60.0,
            "mem_percent": 70.0, "mem_avail_gb": 4.0,
            "gpu_load": 80.0, "gpu_vram_mb": 2048, "gpu_temp": 70, "gpu_power_w": 100, "gpu_fan": 50,
            "disk_root": 50.0, "disk_share": 60.0,
            "load1": 1.0, "load5": 0.8, "load15": 0.5,
            "net_rx_gb": 10.0, "net_tx_gb": 5.0,
        })
        metrics = db.get_system_metrics(limit=10)
        assert len(metrics) >= 1
        assert metrics[0]["cpu_percent"] == 45.0


class TestCanonicalDuplicates:
    def test_mark_canonical_no_dupes(self, db):
        """mark_canonical_duplicates без дублей возвращает (0, 0)."""
        db.add_catalog_root("r20", "/mnt/nodupes")
        db.add_catalog_files_batch([
            {"file_id": "f20", "root_id": "r20", "rel_path": "a.jpg",
             "abs_path": "/mnt/nodupes/a.jpg", "ext": ".jpg", "content_hash": "unique1"},
        ])
        groups, copies = db.mark_canonical_duplicates()
        assert groups == 0
        assert copies == 0

    def test_mark_canonical_with_dupes(self, db):
        """mark_canonical_duplicates помечает дубли как is_canonical=0."""
        db.add_catalog_root("r21", "/mnt/dupes")
        db.add_catalog_files_batch([
            {"file_id": "f21", "root_id": "r21", "rel_path": "orig.jpg",
             "abs_path": "/mnt/dupes/orig.jpg", "ext": ".jpg", "content_hash": "dup_hash"},
            {"file_id": "f22", "root_id": "r21", "rel_path": "copy.jpg",
             "abs_path": "/mnt/dupes/copy.jpg", "ext": ".jpg", "content_hash": "dup_hash"},
        ])
        groups, copies = db.mark_canonical_duplicates()
        assert groups == 1
        assert copies == 1
        files = db.get_catalog_files(root_id="r21")
        canonical = [f for f in files if f["is_canonical"] == 1]
        non_canonical = [f for f in files if f["is_canonical"] == 0]
        assert len(canonical) == 1
        assert len(non_canonical) == 1

    def test_get_duplicate_paths(self, db):
        """get_duplicate_paths возвращает пути не-canonical копий."""
        db.add_catalog_root("r22", "/mnt/dupaths")
        db.add_catalog_files_batch([
            {"file_id": "f30", "root_id": "r22", "rel_path": "orig.jpg",
             "abs_path": "/mnt/dupaths/orig.jpg", "ext": ".jpg", "content_hash": "dh1",
             "is_canonical": 1},
            {"file_id": "f31", "root_id": "r22", "rel_path": "copy.jpg",
             "abs_path": "/mnt/dupaths/copy.jpg", "ext": ".jpg", "content_hash": "dh1",
             "is_canonical": 0},
        ])
        dupes = db.get_duplicate_paths("dh1")
        assert "/mnt/dupaths/copy.jpg" in dupes

    def test_is_path_canonical(self, db):
        """is_path_canonical кэширует и возвращает статус."""
        db.add_catalog_root("r23", "/mnt/canonical")
        db.add_catalog_files_batch([
            {"file_id": "f40", "root_id": "r23", "rel_path": "canon.jpg",
             "abs_path": "/mnt/canonical/canon.jpg", "ext": ".jpg", "content_hash": "ch1",
             "is_canonical": 1},
        ])
        assert db.is_path_canonical("/mnt/canonical/canon.jpg") is True

    def test_invalidate_canonical_cache(self, db):
        """invalidate_canonical_cache сбрасывает кэш."""
        db.add_catalog_root("r24", "/mnt/cache")
        db.add_catalog_files_batch([
            {"file_id": "f50", "root_id": "r24", "rel_path": "c.jpg",
             "abs_path": "/mnt/cache/c.jpg", "ext": ".jpg", "content_hash": "ch2",
             "is_canonical": 1},
        ])
        db.is_path_canonical("/mnt/cache/c.jpg")
        db.invalidate_canonical_cache()
        # После инвалидации кэш перезагрузится
        assert db.is_path_canonical("/mnt/cache/c.jpg") is True


class TestGetStatus:
    def test_status_empty_db(self, db):
        """get_status на пустой БД возвращает нули."""
        status = db.get_status()
        assert status["photos_total"] == 0
        assert status["faces_total"] == 0

    def test_status_with_data(self, db_with_photos):
        """get_status с данными возвращает ненулевые счётчики."""
        db = db_with_photos
        db.update_catalog_root("test_root", enabled=1)
        db.sqlite.execute("UPDATE photos SET root_id='test_root' WHERE root_id IS NULL")
        db.sqlite.commit()
        status = db.get_status()
        assert status["photos_total"] >= 3
        assert "per_root" in status
        assert "videos" in status


class TestInvalidateForPersona:
    def test_invalidate_resets_flags(self, db_with_photos):
        """invalidate_for_persona сбрасывает described, embedded для затронутых фото."""
        db = db_with_photos
        db.add_persona("p_inv", "cluster_inv", display_name="Тест")
        db.add_face_sqlite_only("/photos/2024/img1.jpg", [10, 20, 30, 40], 0.9,
                                persona_id="p_inv", content_hash="hash1")
        db.update_catalog_file_by_path("/photos/2024/img1.jpg", described=1, embedded=1)
        db.invalidate_for_persona("p_inv")
        f = db.get_catalog_file_by_path("/photos/2024/img1.jpg")
        assert f["described"] == 0
        assert f["embedded"] == 0


class TestFaceExtended:
    def test_get_all_faces(self, db):
        """get_all_faces возвращает все лица."""
        pid = db.add_photo("/allf.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9)
        db.add_face_sqlite_only(pid, [50, 60, 70, 80], 0.8)
        all_faces = db.get_all_faces()
        assert len(all_faces) >= 2

    def test_count_faces_with_where(self, db):
        """count_faces с WHERE условием."""
        pid = db.add_photo("/cfw.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9, persona_id="px1")
        db.add_face_sqlite_only(pid, [50, 60, 70, 80], 0.8)
        assert db.count_faces(where="persona_id='px1'") == 1

    def test_get_faces_for_persona(self, db):
        """get_faces_for_persona возвращает лица персоны."""
        pid = db.add_photo("/fpc.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9, persona_id="pf1")
        db.add_face_sqlite_only(pid, [50, 60, 70, 80], 0.8, persona_id="pf1")
        faces = db.get_faces_for_persona("pf1")
        assert len(faces) == 2

    def test_update_face_persona(self, db):
        """update_face_persona меняет persona_id у лица."""
        pid = db.add_photo("/ufp.jpg")
        fid, _ = db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9, persona_id="old_p")
        db.update_face_persona(fid, "new_p")
        face = db.get_face(fid)
        assert face["persona_id"] == "new_p"

    def test_persona_face_id_map(self, db):
        """persona_face_id_map возвращает map persona_id → face_id."""
        pid = db.add_photo("/pfmap.jpg")
        db.add_face_sqlite_only(pid, [10, 20, 30, 40], 0.9, persona_id="pm1", face_id="face_x")
        m = db.persona_face_id_map()
        assert m.get("pm1") == "face_x"


class TestCosineSimilarity:
    def test_identical_vectors(self, db):
        """Косинусная схожесть идентичных векторов = 1.0."""
        v = [1.0, 2.0, 3.0]
        sim = db._cosine_similarity(v, v)
        assert abs(sim - 1.0) < 0.001

    def test_orthogonal_vectors(self, db):
        """Косинусная схожесть ортогональных векторов = 0.0."""
        sim = db._cosine_similarity([1, 0, 0], [0, 1, 0])
        assert abs(sim) < 0.001

    def test_zero_vector(self, db):
        """Косинусная схожесть с нулевым вектором = 0.0."""
        sim = db._cosine_similarity([0, 0, 0], [1, 2, 3])
        assert sim == 0.0
