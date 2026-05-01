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
