import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_MODULES_TO_CLEAN = (
    "main", "database", "api", "api.photos", "api.persons", "api.catalog"
)


def _clean_modules():
    for mod in list(sys.modules.keys()):
        if mod in _MODULES_TO_CLEAN:
            del sys.modules[mod]


@pytest.fixture
def tmp_data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    lance = data / "lancedb"
    lance.mkdir(parents=True)
    logs = tmp_path / "logs"
    logs.mkdir()
    thumbs = tmp_path / "thumbnails"
    thumbs.mkdir()
    photo_share = tmp_path / "photos"
    photo_share.mkdir()
    flags = data / "pipeline_flags"
    flags.mkdir(parents=True)
    return {
        "data": data,
        "lancedb": lance,
        "logs": logs,
        "thumbnails": thumbs,
        "photo_share": photo_share,
        "flags": flags,
        "db_path": data / "gallery.db",
    }


@pytest.fixture
def db(tmp_data):
    _clean_modules()
    cfg_patches = [
        patch("config.DATA_DIR", tmp_data["data"]),
        patch("config.LANCEDB_PATH", tmp_data["lancedb"]),
        patch("config.PHOTO_SHARE_PATH", tmp_data["photo_share"]),
        patch("config.FLAG_DIR", tmp_data["flags"]),
    ]
    for p in cfg_patches:
        p.start()
    from database import DatabaseManager
    db_patches = [
        patch("database.SQLITE_PATH", tmp_data["db_path"]),
    ]
    for p in db_patches:
        p.start()
    manager = DatabaseManager(db_path=tmp_data["db_path"])
    yield manager
    manager.sqlite.close()
    for p in db_patches + cfg_patches:
        p.stop()
    _clean_modules()


@pytest.fixture
def db_with_photos(db):
    root_id = "test_root"
    db.add_catalog_root(root_id, "/photos", alias="test")
    db.add_catalog_files_batch([
        {"file_id": "f1", "root_id": root_id,
         "rel_path": "2024/img1.jpg", "abs_path": "/photos/2024/img1.jpg",
         "parent_dir": "2024", "ext": ".jpg", "is_canonical": 1,
         "content_hash": "hash1"},
        {"file_id": "f2", "root_id": root_id,
         "rel_path": "2024/img2.jpg", "abs_path": "/photos/2024/img2.jpg",
         "parent_dir": "2024", "ext": ".jpg", "is_canonical": 1,
         "content_hash": "hash2"},
        {"file_id": "f3", "root_id": root_id,
         "rel_path": "2025/img3.jpg", "abs_path": "/photos/2025/img3.jpg",
         "parent_dir": "2025", "ext": ".jpg", "is_canonical": 1,
         "content_hash": "hash3"},
    ])
    db.add_photo("/photos/2024/img1.jpg", date="2024-01-15 10:00:00",
                 description="зимний лес", faces_present=True)
    db.add_photo("/photos/2024/img2.jpg", date="2024-03-20 14:30:00",
                 description="весенний парк", gps={"lat": 55.75, "lon": 37.62},
                 camera={"make": "Canon", "model": "EOS R5"})
    db.add_photo("/photos/2025/img3.jpg", date="2025-06-01 09:00:00",
                 description="летнее море")
    return db


@pytest.fixture
def app_client(tmp_data):
    _clean_modules()
    cfg_patches = [
        patch("config.DATA_DIR", tmp_data["data"]),
        patch("config.LANCEDB_PATH", tmp_data["lancedb"]),
        patch("config.LOG_FILE", tmp_data["logs"] / "pipeline.log"),
        patch("config.THUMBNAILS_DIR", tmp_data["thumbnails"]),
        patch("config.PHOTO_SHARE_PATH", tmp_data["photo_share"]),
        patch("config.FLAG_DIR", tmp_data["flags"]),
    ]
    for p in cfg_patches:
        p.start()
    from main import app
    from starlette.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    for p in cfg_patches:
        p.stop()
    _clean_modules()


# ═══════════════════════════════════════════════════════════════════════
# Фикстура миникопии реальной БД для write-тестов
# ═══════════════════════════════════════════════════════════════════════

REAL_DB = Path(__file__).parent.parent / "data" / "gallery.db"


@pytest.fixture
def minidb(tmp_data):
    """Миникопия реальной БД: структура + первые N реальных строк.

    Копирует структуру из реальной БД, затем через ATTACH DATABASE
    переносит первые N строк из каждой таблицы.
    Пути к фото — реальные (файлы на диске не меняются).

    Используется для write-тестов (SECONDARY).
    """
    import sqlite3

    test_path = tmp_data["db_path"]

    # Копируем структуру (только CREATE, без INSERT)
    prod = sqlite3.connect(str(REAL_DB))
    schema_lines = []
    skip_data = False
    for line in prod.iterdump():
        if line.startswith("INSERT INTO"):
            skip_data = True
        elif line.startswith("CREATE"):
            skip_data = False
        if not skip_data:
            schema_lines.append(line)
    prod.close()

    schema = "\n".join(schema_lines)

    mini = sqlite3.connect(str(test_path))
    mini.executescript(schema)

    # ATTACH реальную БД и копируем первые N строк ДАННЫХ
    mini.execute(f"ATTACH DATABASE '{REAL_DB}' AS prod")

    photo_ids = [r[0] for r in mini.execute(
        "SELECT p.photo_id FROM prod.photos p "
        "WHERE p.deleted = 0 AND EXISTS ("
        "SELECT 1 FROM prod.catalog_files cf "
        "WHERE cf.abs_path = p.path AND cf.is_canonical = 1 AND cf.deleted = 0"
        ") LIMIT 100").fetchall()]
    if photo_ids:
        ph = ",".join("?" * len(photo_ids))
        mini.execute(f"INSERT INTO photos SELECT * FROM prod.photos WHERE photo_id IN ({ph})", photo_ids)

    photo_paths = [r[0] for r in mini.execute(
        "SELECT path FROM prod.photos WHERE photo_id IN (" + ",".join("?" * len(photo_ids)) + ")",
        photo_ids).fetchall()] if photo_ids else []
    if photo_paths:
        ph_paths = ",".join("?" * len(photo_paths))
        mini.execute(f"INSERT INTO catalog_files SELECT * FROM prod.catalog_files WHERE abs_path IN ({ph_paths})", photo_paths)
    mini.commit()

    for tbl, rowid_col, limit in [
        ("faces", "rowid", 500),
        ("personas", "rowid", 50),
        ("catalog_roots", "rowid", 5),
        ("changes", "rowid", 50),
        ("settings", "rowid", 20),
    ]:
        cnt = mini.execute(f"SELECT COUNT(*) FROM prod.{tbl}").fetchone()[0]
        if cnt == 0:
            continue
        if tbl == "photos":
            ids = [r[0] for r in mini.execute(
                f"SELECT p.photo_id FROM prod.photos p "
                f"WHERE p.deleted = 0 AND EXISTS ("
                f"SELECT 1 FROM prod.catalog_files cf "
                f"WHERE cf.abs_path = p.path AND cf.is_canonical = 1 AND cf.deleted = 0"
                f") LIMIT {limit}").fetchall()]
        else:
            if cnt > limit:
                ids = [r[0] for r in mini.execute(
                    f"SELECT {rowid_col} FROM prod.{tbl} LIMIT {limit}").fetchall()]
            else:
                ids = None
        if ids:
            ph = ",".join("?" * len(ids))
            mini.execute(
                f"INSERT INTO {tbl} SELECT * FROM prod.{tbl} "
                f"WHERE {rowid_col} IN ({ph})", ids)
        elif ids is None:
            mini.execute(f"INSERT INTO {tbl} SELECT * FROM prod.{tbl}")
        mini.commit()

    mini.execute("DETACH DATABASE prod")
    mini.execute("VACUUM")
    mini.close()

    _clean_modules()
    cfg_patches = [
        patch("config.DATA_DIR", tmp_data["data"]),
        patch("config.LANCEDB_PATH", tmp_data["lancedb"]),
        patch("config.LOG_FILE", tmp_data["logs"] / "pipeline.log"),
        patch("config.THUMBNAILS_DIR", tmp_data["thumbnails"]),
        patch("config.PHOTO_SHARE_PATH", tmp_data["photo_share"]),
        patch("config.FLAG_DIR", tmp_data["flags"]),
    ]
    for p in cfg_patches:
        p.start()

    from database import DatabaseManager
    db_patches = [patch("database.SQLITE_PATH", test_path)]
    for p in db_patches:
        p.start()
    db = DatabaseManager(db_path=test_path)

    from main import app
    from starlette.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)

    yield {"db": db, "client": client, "tmp_data": tmp_data}

    db.sqlite.close()
    for p in db_patches + cfg_patches:
        p.stop()
    _clean_modules()
