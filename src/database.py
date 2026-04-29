"""Database management: SQLite for structured data, LanceDB for vectors"""

import sqlite3
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import lancedb
import pyarrow as pa

from config import LANCEDB_PATH, EMBEDDINGS_TABLE, DATA_DIR, PHOTO_SHARE_PATH

SQLITE_PATH = DATA_DIR / "gallery.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    d = {}
    for key in row.keys():
        d[key] = row[key]
    return d


def _rows_to_dicts(rows):
    return [_row_to_dict(r) for r in rows]


class DatabaseManager:

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or SQLITE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.sqlite = sqlite3.connect(str(self.db_path), timeout=30)
        self.sqlite.row_factory = sqlite3.Row
        self.sqlite.execute("PRAGMA journal_mode=WAL")
        self.sqlite.execute("PRAGMA foreign_keys=ON")
        self.sqlite.execute("PRAGMA busy_timeout=5000")

        self.lancedb_path = LANCEDB_PATH
        self.lancedb_path.mkdir(parents=True, exist_ok=True)
        self.vectordb = lancedb.connect(str(self.lancedb_path))

        self._create_tables()
        self._open_vector_tables()

        logger.info(f"Database initialized: SQLite={self.db_path}, LanceDB={self.lancedb_path}")

    def _create_tables(self):
        cur = self.sqlite.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS photos (
                photo_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                thumbnail_path TEXT,
                date TEXT,
                gps_lat REAL,
                gps_lon REAL,
                manual_gps INTEGER DEFAULT 0,
                camera_make TEXT,
                camera_model TEXT,
                description TEXT,
                faces_present INTEGER DEFAULT 0,
                exif_checked INTEGER DEFAULT 0,
                created_at TEXT,
                date_conflict INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(path);
            CREATE INDEX IF NOT EXISTS idx_photos_date ON photos(date);
            CREATE INDEX IF NOT EXISTS idx_photos_faces ON photos(faces_present);
            CREATE INDEX IF NOT EXISTS idx_photos_exif ON photos(exif_checked);
            CREATE INDEX IF NOT EXISTS idx_photos_desc ON photos(description);

            CREATE TABLE IF NOT EXISTS faces (
                face_id TEXT PRIMARY KEY,
                photo_id TEXT NOT NULL,
                persona_id TEXT,
                bbox_x1 REAL, bbox_y1 REAL,
                bbox_x2 REAL, bbox_y2 REAL,
                confidence REAL,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
            CREATE INDEX IF NOT EXISTS idx_faces_persona ON faces(persona_id);

            CREATE TABLE IF NOT EXISTS personas (
                persona_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT,
                comment TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS catalog_roots (
                root_id TEXT PRIMARY KEY,
                root_path TEXT NOT NULL,
                alias TEXT,
                scanned_at TEXT,
                file_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS catalog_files (
                file_id TEXT PRIMARY KEY,
                root_id TEXT,
                rel_path TEXT NOT NULL,
                abs_path TEXT NOT NULL,
                parent_dir TEXT,
                ext TEXT,
                size INTEGER DEFAULT 0,
                modified TEXT,
                ingested INTEGER DEFAULT 0,
                described INTEGER DEFAULT 0,
                exif_done INTEGER DEFAULT 0,
                faces_done INTEGER DEFAULT 0,
                embedded INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_abs ON catalog_files(abs_path);
             CREATE INDEX IF NOT EXISTS idx_catalog_ingested ON catalog_files(ingested);
             CREATE INDEX IF NOT EXISTS idx_catalog_root ON catalog_files(root_id);
         """)
        self.sqlite.commit()

        cur.execute("PRAGMA table_info(catalog_files)")
        cf_columns = [row[1] for row in cur.fetchall()]
        if 'content_hash' not in cf_columns:
            cur.execute("ALTER TABLE catalog_files ADD COLUMN content_hash TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_catalog_hash ON catalog_files(content_hash)")
            self.sqlite.commit()
        if 'is_canonical' not in cf_columns:
            cur.execute("ALTER TABLE catalog_files ADD COLUMN is_canonical INTEGER DEFAULT 1")
            self.sqlite.commit()

        cur.execute("PRAGMA table_info(photos)")
        columns = [row[1] for row in cur.fetchall()]
        if 'manual_gps' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN manual_gps INTEGER DEFAULT 0")
        if 'manual_date' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN manual_date TEXT")
        if 'deleted' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN deleted INTEGER DEFAULT 0")
        if 'rich_description' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN rich_description TEXT")
        if 'embedded' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN embedded INTEGER DEFAULT 0")
        if 'has_issues' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN has_issues INTEGER DEFAULT 0")
        if 'issue_type' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN issue_type TEXT")
        if 'photo_type' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN photo_type TEXT DEFAULT 'photo'")
        if 'exif_raw' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN exif_raw TEXT")
        if 'img_width' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN img_width INTEGER")
        if 'img_height' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN img_height INTEGER")
        if 'date_conflict' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN date_conflict INTEGER DEFAULT 0")
        if 'thumbnail_path' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN thumbnail_path TEXT")
        self.sqlite.commit()

        cur.execute("PRAGMA table_info(catalog_roots)")
        cr_columns = [row[1] for row in cur.fetchall()]
        if 'enabled' not in cr_columns:
            cur.execute("ALTER TABLE catalog_roots ADD COLUMN enabled INTEGER DEFAULT 1")
            self.sqlite.commit()

        p_columns = [row[1] for row in cur.execute("PRAGMA table_info(photos)").fetchall()]
        if 'root_id' not in p_columns:
            cur.execute("ALTER TABLE photos ADD COLUMN root_id TEXT")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_photos_root_id ON photos(root_id)")
            self.sqlite.commit()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='changes'")
        if not cur.fetchone():
            cur.execute("""
                CREATE TABLE changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    photo_id TEXT,
                    field TEXT,
                    value TEXT,
                    changed_at TEXT
                )
            """)
            self.sqlite.commit()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='photo_edits'")
        if not cur.fetchone():
            cur.execute("""
                CREATE TABLE photo_edits (
                    edit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params TEXT NOT NULL,
                    action_order INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edits_hash ON photo_edits(content_hash)")
            self.sqlite.commit()

        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_photos_effective_date'")
        if not cur.fetchone():
            cur.execute("CREATE INDEX IF NOT EXISTS idx_photos_effective_date ON photos(COALESCE(manual_date, date))")
            self.sqlite.commit()

    def _open_vector_tables(self):
        if "photo_embeddings" not in self.vectordb.list_tables().tables:
            schema = pa.schema([
                pa.field("photo_id", pa.string()),
                pa.field("search_text", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), 1024)),
                pa.field("meta_hash", pa.string()),
                pa.field("embedded_at", pa.string()),
            ])
            self.vectordb.create_table("photo_embeddings", schema=schema)

        if "face_vectors" not in self.vectordb.list_tables().tables:
            schema = pa.schema([
                pa.field("face_id", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), 512)),
            ])
            self.vectordb.create_table("face_vectors", schema=schema)

        self.photo_embeddings = self.vectordb.open_table("photo_embeddings")
        self.face_vectors = self.vectordb.open_table("face_vectors")

    # ─── Photos ──────────────────────────────────────────

    def add_photo(self, path, thumbnail_path="", date=None, gps=None, camera=None,
                  description=None, faces_present=False, exif_checked=False):
        photo_id = str(uuid.uuid4())
        self.sqlite.execute(
            "INSERT OR IGNORE INTO photos (photo_id,path,thumbnail_path,date,gps_lat,gps_lon,"
            "camera_make,camera_model,description,faces_present,exif_checked,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (photo_id, path, thumbnail_path, date,
             gps.get("lat") if gps else None,
             gps.get("lon") if gps else None,
             camera.get("make") if camera else None,
             camera.get("model") if camera else None,
             description, int(faces_present), int(exif_checked),
             datetime.now().isoformat())
        )
        self.sqlite.commit()
        return photo_id

    def add_photos_batch(self, records):
        cur = self.sqlite.cursor()
        for r in records:
            cur.execute(
                "INSERT OR IGNORE INTO photos (photo_id,path,thumbnail_path,date,gps_lat,gps_lon,"
                "camera_make,camera_model,description,faces_present,exif_checked,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.get("photo_id", str(uuid.uuid4())),
                 r.get("path"), r.get("thumbnail_path"), r.get("date"),
                 r.get("gps_lat"), r.get("gps_lon"),
                 r.get("camera_make"), r.get("camera_model"),
                 r.get("description"),
                 int(r.get("faces_present", False)),
                 int(r.get("exif_checked", False)),
                 r.get("created_at") or datetime.now().isoformat())
            )
        self.sqlite.commit()

    def get_photo(self, photo_id):
        row = self.sqlite.execute(
            "SELECT * FROM photos WHERE photo_id = ?", (photo_id,)
        ).fetchone()
        return _row_to_dict(row)

    def get_photo_by_path(self, path):
        row = self.sqlite.execute(
            "SELECT * FROM photos WHERE path = ?", (path,)
        ).fetchone()
        return _row_to_dict(row)

    def update_photo(self, photo_id, **kwargs):
        if not kwargs:
            return
        skip_log = {"exif_checked", "embedded"}
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cur = self.sqlite.cursor()
        for k, v in kwargs.items():
            if k in skip_log:
                continue
            if v is None:
                continue
            cur.execute(
                "INSERT INTO changes (photo_id, field, value, changed_at) VALUES (?, ?, ?, ?)",
                (photo_id, k, str(v)[:200], now)
            )
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [photo_id]
        cur.execute(f"UPDATE photos SET {sets} WHERE photo_id = ?", vals)
        self.sqlite.commit()

    def delete_photo(self, photo_id):
        self.sqlite.execute("DELETE FROM photos WHERE photo_id = ?", (photo_id,))
        self.sqlite.commit()

    def count_photos(self, where=None):
        sql = "SELECT COUNT(*) FROM photos"
        if where:
            sql += f" WHERE {where}"
        return self.sqlite.execute(sql).fetchone()[0]

    def _get_photo_share_path(self):
        return PHOTO_SHARE_PATH

    def _enabled_root_filter(self):
        enabled_roots = [r for r in self.get_catalog_roots() if r.get("enabled", 1)]
        if not enabled_roots:
            roots = self.get_catalog_roots()
            if not roots:
                return "1=1", []
            return "1=0", []
        enabled_ids = [r["root_id"] for r in enabled_roots]
        placeholders = ",".join("?" * len(enabled_ids))
        return f"cf.root_id IN ({placeholders})", enabled_ids

    def search_photos(self, q=None, person=None, date_from=None, date_to=None,
                      date_after=None, date_before=None,
                      path_after=None, path_before=None,
                      has_faces=None, no_description=None, has_issues=None,
                      issue_type=None, photo_type=None, has_gps=None,
                      no_date=None, has_description=None,
                      deleted=None, deleted_only=None,
                      content_hash=None, file_type=None,
                      sort="date_desc", limit=60, offset=0):
        ed = "COALESCE(manual_date, date)"
        sql = "SELECT photos.*, " + ed + " as effective_date, cf.content_hash FROM photos JOIN catalog_files cf ON cf.abs_path = photos.path WHERE cf.is_canonical = 1"
        params = []

        root_filter, root_params = self._enabled_root_filter()
        sql += f" AND {root_filter}"
        params.extend(root_params)

        if deleted_only is True:
            sql += " AND deleted = 1"
        elif deleted is not True:
            sql += " AND deleted = 0"

        if no_date is True:
            sql += f" AND ({ed} IS NULL OR length({ed}) < 4 OR substr({ed},1,4) = '0000')"
        if q:
            sql += " AND description LIKE ?"
            params.append(f"%{q}%")
        if date_from:
            sql += f" AND {ed} >= ?"
            params.append(date_from)
        if date_to:
            sql += f" AND {ed} <= ?"
            params.append(date_to)
        if date_after:
            if path_after:
                sql += f" AND ({ed} > ? OR ({ed} = ? AND path > ?))"
                params.extend([date_after, date_after, path_after])
            else:
                sql += f" AND {ed} > ?"
                params.append(date_after)
        if date_before:
            if path_before:
                sql += f" AND ({ed} < ? OR ({ed} = ? AND path < ?))"
                params.extend([date_before, date_before, path_before])
            else:
                sql += f" AND {ed} < ?"
                params.append(date_before)
        if has_faces is True:
            sql += " AND faces_present = 1"
        elif has_faces is False:
            sql += " AND faces_present = 0"
        if no_description is True:
            sql += " AND (description IS NULL OR description = '')"
        if has_description is True:
            sql += " AND description IS NOT NULL AND description != ''"
        if has_issues is True:
            sql += " AND has_issues = 1"
        if issue_type:
            sql += " AND issue_type = ?"
            params.append(issue_type)
        if photo_type:
            sql += " AND photo_type = ?"
            params.append(photo_type)
        if has_gps is True:
            sql += " AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL"
        elif has_gps is False:
            sql += " AND (gps_lat IS NULL OR gps_lon IS NULL)"

        _raw_exts = {'.cr2', '.nef', '.arw', '.dng', '.raw', '.rw2', '.orf', '.sr2', '.raf'}
        if file_type == 'raw':
            ext_clauses = ' OR '.join(['path LIKE ?' for _ in _raw_exts])
            sql += f" AND ({ext_clauses})"
            params.extend([f'%{e}' for e in sorted(_raw_exts)])
        elif file_type == 'non_raw':
            ext_clauses = ' AND '.join(['path NOT LIKE ?' for _ in _raw_exts])
            sql += f" AND ({ext_clauses})"
            params.extend([f'%{e}' for e in sorted(_raw_exts)])

        if content_hash:
            sql += " AND cf.content_hash LIKE ?"
            params.append(f"%{content_hash}%")

        if person:
            matching_paths = self.sqlite.execute(
                "SELECT DISTINCT p.path FROM photos p "
                "JOIN faces f ON f.photo_id = p.path OR f.photo_id = substr(p.path, length('" + str(PHOTO_SHARE_PATH) + "/') + 1) "
                "JOIN personas pe ON f.persona_id = pe.persona_id "
                "WHERE pe.display_name LIKE ? OR pe.name LIKE ?",
                (f"%{person}%", f"%{person}%")
            ).fetchall()
            paths = [r[0] for r in matching_paths]
            if paths:
                placeholders = ",".join("?" * len(paths))
                sql += f" AND path IN ({placeholders})"
                params.extend(paths)
            else:
                sql += " AND 1=0"

        order_map = {
            "date_desc": "effective_date DESC, path DESC",
            "date_asc": "effective_date ASC, path ASC",
            "created_desc": "created_at DESC, path DESC",
            "created_asc": "created_at ASC, path ASC",
        }
        sql += f" ORDER BY {order_map.get(sort, 'effective_date DESC')}"

        count_sql = sql.replace("SELECT photos.*, " + ed + " as effective_date", "SELECT COUNT(*)", 1)
        count_sql = count_sql.split(" ORDER BY ")[0]
        total = self.sqlite.execute(count_sql, params).fetchone()[0]

        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.sqlite.execute(sql, params).fetchall()
        return total, _rows_to_dicts(rows)

    def get_all_photos(self):
        root_filter, root_params = self._enabled_root_filter()
        rows = self.sqlite.execute(
            f"SELECT photos.* FROM photos JOIN catalog_files cf ON cf.abs_path = photos.path "
            f"WHERE cf.is_canonical = 1 AND {root_filter}",
            root_params
        ).fetchall()
        return _rows_to_dicts(rows)

    def get_date_histogram(self):
        root_filter, root_params = self._enabled_root_filter()
        ed = "COALESCE(manual_date, date)"
        rows = self.sqlite.execute(
            f"SELECT substr({ed},1,4) as year, substr({ed},1,7) as month, COUNT(*) as cnt "
            f"FROM photos JOIN catalog_files cf ON cf.abs_path = photos.path "
            f"WHERE {ed} IS NOT NULL AND length({ed}) >= 4 "
            f"AND substr({ed},1,4) != '0000' AND deleted = 0 AND cf.is_canonical = 1 AND {root_filter} "
            f"GROUP BY year, month ORDER BY year, month",
            root_params
        ).fetchall()
        years = {}
        months = {}
        for r in rows:
            y, m, cnt = r[0], r[1], r[2]
            years[y] = years.get(y, 0) + cnt
            months[m] = months.get(m, 0) + cnt
        no_date = self.sqlite.execute(
            "SELECT COUNT(*) FROM photos WHERE (COALESCE(manual_date, date) IS NULL OR length(COALESCE(manual_date, date)) < 4 OR substr(COALESCE(manual_date, date),1,4) = '0000') AND deleted = 0"
        ).fetchone()[0]
        if no_date > 0:
            years["no_date"] = no_date
        total = self.count_photos(where="deleted = 0")
        return {"years": dict(sorted(years.items())), "months": dict(sorted(months.items())), "total": total}

    # ─── Faces ──────────────────────────────────────────

    def add_face(self, photo_id, embedding, bbox, confidence, persona_id=None, face_id=None):
        if not face_id:
            face_id = str(uuid.uuid4())

        existing = self.sqlite.execute(
            "SELECT face_id FROM faces WHERE face_id = ?", (face_id,)
        ).fetchone()
        if existing:
            return face_id

        self.sqlite.execute(
            "INSERT OR IGNORE INTO faces (face_id,photo_id,persona_id,bbox_x1,bbox_y1,"
            "bbox_x2,bbox_y2,confidence,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (face_id, photo_id, persona_id,
             bbox[0], bbox[1], bbox[2], bbox[3], confidence,
             datetime.now().isoformat())
        )
        self.sqlite.commit()

        self.face_vectors.add([{
            "face_id": face_id,
            "embedding": embedding,
        }])

        return face_id

    def add_face_sqlite_only(self, photo_id, bbox, confidence, persona_id=None, face_id=None):
        if not face_id:
            face_id = str(uuid.uuid4())

        existing = self.sqlite.execute(
            "SELECT face_id FROM faces WHERE face_id = ?", (face_id,)
        ).fetchone()
        if existing:
            return face_id, False

        self.sqlite.execute(
            "INSERT OR IGNORE INTO faces (face_id,photo_id,persona_id,bbox_x1,bbox_y1,"
            "bbox_x2,bbox_y2,confidence,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (face_id, photo_id, persona_id,
             bbox[0], bbox[1], bbox[2], bbox[3], confidence,
             datetime.now().isoformat())
        )
        self.sqlite.commit()
        return face_id, True

    def add_face_vectors_batch(self, records):
        if records:
            self.face_vectors.add(records)

    def get_face(self, face_id):
        row = self.sqlite.execute(
            "SELECT * FROM faces WHERE face_id = ?", (face_id,)
        ).fetchone()
        return _row_to_dict(row)

    def get_faces_for_photo(self, photo_id):
        rows = self.sqlite.execute(
            "SELECT * FROM faces WHERE photo_id = ?", (photo_id,)
        ).fetchall()
        return _rows_to_dicts(rows)

    def get_faces_for_persona(self, persona_id, limit=100):
        rows = self.sqlite.execute(
            "SELECT * FROM faces WHERE persona_id = ? LIMIT ?", (persona_id, limit)
        ).fetchall()
        return _rows_to_dicts(rows)

    def update_face_persona(self, face_id, persona_id):
        self.sqlite.execute(
            "UPDATE faces SET persona_id = ? WHERE face_id = ?",
            (persona_id, face_id)
        )
        self.sqlite.commit()

    def get_face_embedding(self, face_id):
        results = self.face_vectors.search().where(
            f"face_id = '{face_id}'"
        ).limit(1).to_list()
        if results:
            return results[0].get("embedding")
        return None

    def get_all_face_embeddings(self):
        faces = self.sqlite.execute(
            "SELECT face_id, persona_id, photo_id FROM faces"
        ).fetchall()
        vec_rows = self.face_vectors.search().select(["face_id", "embedding"]).limit(10000000).to_list()
        vec_map = {v["face_id"]: v["embedding"] for v in vec_rows}
        result = []
        for f in faces:
            fid, pid, photo_id = f[0], f[1], f[2]
            emb = vec_map.get(fid)
            if emb:
                result.append({"face_id": fid, "persona_id": pid, "photo_id": photo_id, "embedding": emb})
        return result

    def get_all_faces(self):
        rows = self.sqlite.execute("SELECT * FROM faces").fetchall()
        return _rows_to_dicts(rows)

    def count_faces(self, where=None):
        sql = "SELECT COUNT(*) FROM faces"
        if where:
            sql += f" WHERE {where}"
        return self.sqlite.execute(sql).fetchone()[0]

    # ─── Personas ───────────────────────────────────────

    def add_persona(self, persona_id, name, display_name=None, comment=None):
        self.sqlite.execute(
            "INSERT OR IGNORE INTO personas (persona_id,name,display_name,comment,created_at) "
            "VALUES (?,?,?,?,?)",
            (persona_id, name, display_name, comment, datetime.now().isoformat())
        )
        self.sqlite.commit()
        return True

    def get_persona(self, persona_id):
        row = self.sqlite.execute(
            "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
        ).fetchone()
        return _row_to_dict(row)

    def get_all_personas(self):
        rows = self.sqlite.execute("SELECT * FROM personas").fetchall()
        return _rows_to_dicts(rows)

    def update_persona(self, persona_id, display_name=None, comment=None,
                       clear_display_name=False, clear_comment=False):
        if clear_display_name:
            self.sqlite.execute(
                "UPDATE personas SET display_name = NULL WHERE persona_id = ?",
                (persona_id,)
            )
        elif display_name is not None:
            self.sqlite.execute(
                "UPDATE personas SET display_name = ? WHERE persona_id = ?",
                (display_name, persona_id)
            )
        if clear_comment:
            self.sqlite.execute(
                "UPDATE personas SET comment = NULL WHERE persona_id = ?",
                (persona_id,)
            )
        elif comment is not None:
            self.sqlite.execute(
                "UPDATE personas SET comment = ? WHERE persona_id = ?",
                (comment, persona_id)
            )
        self.sqlite.commit()
        return self.get_persona(persona_id)

    def delete_persona(self, persona_id):
        self.sqlite.execute("DELETE FROM personas WHERE persona_id = ?", (persona_id,))
        self.sqlite.commit()

    def merge_personas(self, source_persona_id, target_persona_id):
        source = self.get_persona(source_persona_id)
        target = self.get_persona(target_persona_id)
        if not source or not target:
            return False
        if source_persona_id == target_persona_id:
            return False
        self.sqlite.execute(
            "UPDATE faces SET persona_id = ? WHERE persona_id = ?",
            (target_persona_id, source_persona_id)
        )
        self.sqlite.execute(
            "DELETE FROM personas WHERE persona_id = ?", (source_persona_id,)
        )
        self.sqlite.commit()
        return True

    def face_count_map(self):
        rows = self.sqlite.execute(
            "SELECT persona_id, COUNT(*) as cnt FROM faces WHERE persona_id IS NOT NULL GROUP BY persona_id"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def persona_face_id_map(self):
        rows = self.sqlite.execute(
            "SELECT persona_id, MIN(face_id) as face_id FROM faces WHERE persona_id IS NOT NULL GROUP BY persona_id"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def get_display_names(self):
        rows = self.sqlite.execute(
            "SELECT DISTINCT display_name FROM personas WHERE display_name IS NOT NULL ORDER BY display_name"
        ).fetchall()
        return [r[0] for r in rows]

    def get_personas_by_name(self, display_name):
        rows = self.sqlite.execute(
            "SELECT * FROM personas WHERE display_name = ?", (display_name,)
        ).fetchall()
        result = []
        for p in _rows_to_dicts(rows):
            face = self.sqlite.execute(
                "SELECT face_id FROM faces WHERE persona_id = ? LIMIT 1",
                (p["persona_id"],)
            ).fetchone()
            p["face_id"] = face[0] if face else None
            result.append(p)
        return result

    def search_similar_faces(self, embedding, limit=10, threshold=0.5):
        import numpy as np
        all_faces = self.get_all_face_embeddings()
        results = []
        for f in all_faces:
            sim = self._cosine_similarity(embedding, f["embedding"])
            if sim >= threshold:
                results.append({"face_id": f["face_id"], "persona_id": f["persona_id"], "similarity": sim})
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def _cosine_similarity(self, a, b):
        import numpy as np
        a_arr, b_arr = np.array(a), np.array(b)
        dot = np.dot(a_arr, b_arr)
        na, nb = np.linalg.norm(a_arr), np.linalg.norm(b_arr)
        return dot / (na * nb) if na and nb else 0.0

    # ─── Catalog ────────────────────────────────────────

    def add_catalog_root(self, root_id, root_path, alias=None, file_count=0, total_size=0):
        self.sqlite.execute(
            "INSERT OR IGNORE INTO catalog_roots (root_id,root_path,alias,scanned_at,"
            "file_count,total_size) VALUES (?,?,?,?,?,?)",
            (root_id, root_path, alias, datetime.now().isoformat(), file_count, total_size)
        )
        self.sqlite.commit()

    def update_catalog_root(self, root_id, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [root_id]
        self.sqlite.execute(f"UPDATE catalog_roots SET {sets} WHERE root_id = ?", vals)
        self.sqlite.commit()

    def get_catalog_roots(self):
        rows = self.sqlite.execute("SELECT * FROM catalog_roots").fetchall()
        return _rows_to_dicts(rows)

    def get_catalog_root(self, root_id):
        row = self.sqlite.execute(
            "SELECT * FROM catalog_roots WHERE root_id = ?", (root_id,)
        ).fetchone()
        return _row_to_dict(row)

    def delete_catalog_root(self, root_id):
        self.sqlite.execute("DELETE FROM catalog_files WHERE root_id = ?", (root_id,))
        self.sqlite.execute("DELETE FROM catalog_roots WHERE root_id = ?", (root_id,))
        self.sqlite.commit()

    def add_catalog_files_batch(self, records):
        cur = self.sqlite.cursor()
        for r in records:
            cur.execute(
                "INSERT OR IGNORE INTO catalog_files (file_id,root_id,rel_path,abs_path,"
                "parent_dir,ext,size,modified,content_hash,is_canonical,"
                "ingested,described,exif_done,faces_done,embedded) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.get("file_id", str(uuid.uuid4())),
                 r.get("root_id"), r.get("rel_path"), r.get("abs_path"),
                 r.get("parent_dir"), r.get("ext"),
                 r.get("size", 0), r.get("modified"),
                 r.get("content_hash"),
                 int(r.get("is_canonical", True)),
                 int(r.get("ingested", False)),
                 int(r.get("described", False)),
                 int(r.get("exif_done", False)),
                 int(r.get("faces_done", False)),
                 int(r.get("embedded", False)))
            )
        self.sqlite.commit()

    def get_catalog_files(self, root_id=None, where=None):
        sql = "SELECT * FROM catalog_files"
        params = []
        if root_id:
            sql += " WHERE root_id = ?"
            params.append(root_id)
            if where:
                sql += f" AND {where}"
        elif where:
            sql += f" WHERE {where}"
        rows = self.sqlite.execute(sql, params).fetchall()
        return _rows_to_dicts(rows)

    def count_catalog_files(self, where=None):
        sql = "SELECT COUNT(*) FROM catalog_files"
        if where:
            sql += f" WHERE {where}"
        return self.sqlite.execute(sql).fetchone()[0]

    def update_catalog_file(self, file_id, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [file_id]
        self.sqlite.execute(f"UPDATE catalog_files SET {sets} WHERE file_id = ?", vals)
        self.sqlite.commit()

    def update_catalog_file_by_path(self, abs_path, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [abs_path]
        self.sqlite.execute(f"UPDATE catalog_files SET {sets} WHERE abs_path = ?", vals)
        self.sqlite.commit()

    def delete_catalog_file(self, file_id):
        self.sqlite.execute("DELETE FROM catalog_files WHERE file_id = ?", (file_id,))
        self.sqlite.commit()

    def delete_catalog_files_by_root(self, root_id):
        self.sqlite.execute("DELETE FROM catalog_files WHERE root_id = ?", (root_id,))
        self.sqlite.commit()

    def get_catalog_file_by_path(self, abs_path):
        row = self.sqlite.execute(
            "SELECT * FROM catalog_files WHERE abs_path = ?", (abs_path,)
        ).fetchone()
        return _row_to_dict(row)

    # ─── Embeddings (LanceDB) ───────────────────────────

    def add_photo_embedding(self, photo_id, search_text, embedding, meta_hash):
        self.delete_photo_embedding(photo_id)
        self.photo_embeddings.add([{
            "photo_id": photo_id,
            "search_text": search_text,
            "embedding": embedding,
            "meta_hash": meta_hash,
            "embedded_at": datetime.now().isoformat(),
        }])

    def add_photo_embeddings_batch(self, records):
        ids_to_delete = [r["photo_id"] for r in records]
        if ids_to_delete:
            id_list = ", ".join(f"'{pid}'" for pid in ids_to_delete)
            try:
                self.photo_embeddings.delete(f"photo_id IN ({id_list})")
            except Exception:
                pass
        self.photo_embeddings.add(records)

    def delete_photo_embedding(self, photo_id):
        try:
            self.photo_embeddings.delete(f"photo_id = '{photo_id}'")
        except Exception:
            pass

    def dedup_photo_embeddings(self):
        """Remove duplicate photo_embeddings rows, keeping the last occurrence.
        Uses safe delete + optimize (no drop_table to avoid data loss).
        Returns (before_rows, after_rows, removed_count)."""
        tbl = self.photo_embeddings
        before_rows = tbl.count_rows()
        data = tbl.to_arrow()
        pids = data.column("photo_id").to_pylist()
        seen = {}
        for i, pid in enumerate(pids):
            seen[pid] = i
        dup_indices = set(range(len(pids))) - set(seen.values())
        if not dup_indices:
            return (before_rows, before_rows, 0)
        dup_pids = [pids[i] for i in sorted(dup_indices)]
        if dup_pids:
            for offset in range(0, len(dup_pids), 500):
                batch = dup_pids[offset:offset + 500]
                id_list = ", ".join(f"'{pid}'" for pid in batch)
                try:
                    tbl.delete(f"photo_id IN ({id_list})")
                except Exception:
                    pass
        after_rows = before_rows - len(dup_indices)
        return (before_rows, after_rows, len(dup_indices))

    def _optimize_table(self, tbl):
        """Compact and cleanup LanceDB table to reclaim space."""
        from datetime import timedelta
        try:
            tbl.optimize(cleanup_older_than=timedelta(seconds=0))
        except Exception:
            try:
                tbl.compact_files()
                tbl.cleanup_old_versions()
            except Exception:
                pass

    def compact_photo_embeddings(self):
        """Compact LanceDB fragments to reclaim space from soft-deleted rows."""
        self._optimize_table(self.photo_embeddings)

    def search_photo_embeddings(self, query_vector, limit=20):
        return self.photo_embeddings.search(query_vector).limit(limit).to_list()

    def count_photo_embeddings(self):
        try:
            return self.photo_embeddings.count_rows()
        except Exception:
            try:
                return len(self.photo_embeddings.search().select(["photo_id"]).limit(100000).to_list())
            except Exception:
                return 0

    def get_photo_embedding(self, photo_id):
        try:
            results = self.photo_embeddings.search().where(
                f"photo_id = '{photo_id}'"
            ).limit(1).to_list()
            return results[0] if results else None
        except Exception:
            return None

    # ─── Invalidate embeddings on metadata change ───────

    def invalidate_embeddings_for_photos(self, photo_ids):
        for pid in photo_ids:
            self.delete_photo_embedding(pid)

    def invalidate_embeddings_for_persona(self, persona_id):
        faces = self.get_faces_for_persona(persona_id)
        photo_rels = set(f.get("photo_id", "") for f in faces)
        if not photo_rels:
            return
        PREFIX = str(PHOTO_SHARE_PATH) + "/"
        rows = self.sqlite.execute(
            "SELECT photo_id, path FROM photos WHERE path LIKE ?",
            (PREFIX + "%",)
        ).fetchall()
        for r in rows:
            rel = r[1][len(PREFIX):] if r[1].startswith(PREFIX) else r[1]
            if rel in photo_rels:
                self.delete_photo_embedding(r[0])

    # ─── Status helpers ─────────────────────────────────

    def get_status(self):
        enabled_roots = [r for r in self.get_catalog_roots() if r.get("enabled", 1)]
        enabled_ids = [r["root_id"] for r in enabled_roots]
        rid_placeholders = ",".join("?" * len(enabled_ids)) if enabled_ids else ""

        if enabled_ids:
            catalog_total = self.sqlite.execute(
                f"SELECT COUNT(*) FROM catalog_files WHERE root_id IN ({rid_placeholders})",
                enabled_ids
            ).fetchone()[0]
            photos_total = self.sqlite.execute(
                f"SELECT COUNT(*) FROM photos WHERE deleted = 0 AND root_id IN ({rid_placeholders})",
                enabled_ids
            ).fetchone()[0]
            described = self.sqlite.execute(
                f"SELECT COUNT(*) FROM photos WHERE description IS NOT NULL AND description != '' AND deleted = 0 AND root_id IN ({rid_placeholders})",
                enabled_ids
            ).fetchone()[0]
            faces_flagged = self.sqlite.execute(
                f"SELECT COUNT(*) FROM photos WHERE faces_present = 1 AND deleted = 0 AND root_id IN ({rid_placeholders})",
                enabled_ids
            ).fetchone()[0]
            exif_done = self.sqlite.execute(
                f"SELECT COUNT(*) FROM photos WHERE exif_checked = 1 AND deleted = 0 AND root_id IN ({rid_placeholders})",
                enabled_ids
            ).fetchone()[0]
            embedded = self.sqlite.execute(
                f"SELECT COUNT(*) FROM photos WHERE embedded = 1 AND deleted = 0 AND root_id IN ({rid_placeholders})",
                enabled_ids
            ).fetchone()[0]
        else:
            catalog_total = photos_total = described = faces_flagged = exif_done = embedded = 0

        photos_deleted = self.count_photos(where="deleted = 1")
        faces_processed = faces_flagged
        personas_total = self.sqlite.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
        faces_total = self.count_faces()
        with_persona = self.count_faces("persona_id IS NOT NULL")
        no_cluster = self.count_faces("persona_id IS NULL")

        per_root = []
        for r in enabled_roots:
            rid = r["root_id"]
            r_photos = self.sqlite.execute("SELECT COUNT(*) FROM photos WHERE root_id = ? AND deleted = 0", (rid,)).fetchone()[0]
            r_described = self.sqlite.execute("SELECT COUNT(*) FROM photos WHERE root_id = ? AND description IS NOT NULL AND description != '' AND deleted = 0", (rid,)).fetchone()[0]
            r_exif = self.sqlite.execute("SELECT COUNT(*) FROM photos WHERE root_id = ? AND exif_checked = 1 AND deleted = 0", (rid,)).fetchone()[0]
            r_cat = self.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE root_id = ?", (rid,)).fetchone()[0]
            r_embedded = self.sqlite.execute("SELECT COUNT(*) FROM photos WHERE root_id = ? AND embedded = 1 AND deleted = 0", (rid,)).fetchone()[0]
            per_root.append({
                "root_id": rid,
                "alias": r.get("alias", ""),
                "catalog_total": r_cat,
                "ingested": r_photos,
                "described": r_described,
                "exif_done": r_exif,
                "embedded": r_embedded,
            })

        return {
            "photos_total": photos_total,
            "photos_deleted": photos_deleted,
            "photos_described": described,
            "photos_faces_flagged": faces_flagged,
            "photos_exif_done": exif_done,
            "faces_total": faces_total,
            "faces_with_persona": with_persona,
            "faces_no_cluster": no_cluster,
            "personas_total": personas_total,
            "catalog_total": max(catalog_total, photos_total),
            "catalog_ingested": photos_total,
            "catalog_not_ingested": max(catalog_total, photos_total) - photos_total,
            "catalog_described": described,
            "catalog_not_described": photos_total - described,
            "catalog_exif_done": exif_done,
            "catalog_exif_not": photos_total - exif_done,
            "catalog_faces_done": faces_processed,
            "catalog_faces_not": max(faces_flagged - faces_processed, 0),
            "photos_embedded": embedded,
            "photos_not_embedded": photos_total - embedded,
            "pct_ingested": round(min(photos_total, catalog_total) / max(catalog_total, 1) * 100, 2),
            "pct_described": round(described / max(photos_total, 1) * 100, 2),
            "pct_exif": round(exif_done / max(photos_total, 1) * 100, 2),
            "pct_faces": round(faces_processed / max(faces_flagged, 1) * 100, 2),
            "pct_embedded": round(embedded / max(photos_total, 1) * 100, 2),
            "faces_flagged_in_db": faces_flagged,
            "ingested_undescribed": photos_total - described,
            "ingested_no_exif": photos_total - exif_done,
            "faces_not_done": max(faces_flagged - faces_processed, 0),
            "per_root": per_root,
        }

    def mark_canonical_duplicates(self):
        """For each content_hash group with >1 file, mark one as canonical=1
        and the rest as canonical=0. Prefers already-described files, then
        shortest path. Returns (total_groups, total_copies)."""
        cur = self.sqlite.cursor()
        rows = cur.execute(
            "SELECT content_hash, COUNT(*) as cnt FROM catalog_files "
            "WHERE content_hash IS NOT NULL "
            "GROUP BY content_hash HAVING COUNT(*) > 1"
        ).fetchall()
        if not rows:
            return (0, 0)
        total_groups = len(rows)
        total_copies = 0
        for (h, cnt) in rows:
            files = cur.execute(
                "SELECT file_id, abs_path, described, ingested "
                "FROM catalog_files WHERE content_hash = ? ORDER BY "
                "described DESC, ingested DESC, length(abs_path) ASC, abs_path ASC",
                (h,)
            ).fetchall()
            canonical_id = files[0][0]
            copy_ids = [f[0] for f in files[1:]]
            if copy_ids:
                placeholders = ",".join("?" for _ in copy_ids)
                cur.execute(
                    f"UPDATE catalog_files SET is_canonical = 0 WHERE file_id IN ({placeholders})",
                    copy_ids
                )
                total_copies += len(copy_ids)
        self.sqlite.commit()
        return (total_groups, total_copies)

    def get_duplicate_paths(self, content_hash, exclude_path=None):
        """Get all abs_paths for non-canonical files with the same content_hash."""
        cur = self.sqlite.cursor()
        if exclude_path:
            rows = cur.execute(
                "SELECT abs_path FROM catalog_files "
                "WHERE content_hash = ? AND is_canonical = 0 "
                "ORDER BY abs_path",
                (content_hash,)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT abs_path FROM catalog_files "
                "WHERE content_hash = ? AND is_canonical = 0 "
                "ORDER BY abs_path",
                (content_hash,)
            ).fetchall()
        return [r[0] for r in rows]

    def is_path_canonical(self, abs_path):
        """Check if a file path is the canonical representative for its content_hash.
        Uses in-memory cache to avoid repeated queries."""
        if not hasattr(self, '_canonical_cache'):
            self._canonical_cache = {}
            self._canonical_cache_loaded = False
        if not self._canonical_cache_loaded:
            cur = self.sqlite.cursor()
            rows = cur.execute(
                "SELECT abs_path, is_canonical FROM catalog_files WHERE content_hash IS NOT NULL"
            ).fetchall()
            for p, c in rows:
                self._canonical_cache[p] = bool(c)
            self._canonical_cache_loaded = True
        return self._canonical_cache.get(abs_path, True)

    def invalidate_canonical_cache(self):
        """Invalidate the canonical cache after marking duplicates."""
        if hasattr(self, '_canonical_cache'):
            self._canonical_cache = {}
            self._canonical_cache_loaded = False

    def get_canonical_status(self):
        """Get stats about canonical/duplicate files."""
        cur = self.sqlite.cursor()
        total = cur.execute("SELECT COUNT(*) FROM catalog_files WHERE content_hash IS NOT NULL").fetchone()[0]
        canonical = cur.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND content_hash IS NOT NULL").fetchone()[0]
        copies = total - canonical
        groups = cur.execute(
            "SELECT COUNT(*) FROM (SELECT content_hash FROM catalog_files "
            "WHERE content_hash IS NOT NULL GROUP BY content_hash HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        return {"total_hashed": total, "canonical": canonical, "copies": copies, "duplicate_groups": groups}

    def get_edits(self, content_hash):
        cur = self.sqlite.cursor()
        rows = cur.execute(
            "SELECT edit_id, action, params, action_order, enabled FROM photo_edits "
            "WHERE content_hash = ? AND enabled = 1 ORDER BY action_order",
            (content_hash,)
        ).fetchall()
        return [{"edit_id": r[0], "action": r[1], "params": json.loads(r[2]), "action_order": r[3], "enabled": r[4]} for r in rows]

    def add_edit(self, content_hash, action, params, action_order=0):
        cur = self.sqlite.cursor()
        cur.execute(
            "INSERT INTO photo_edits (content_hash, action, params, action_order, enabled, created_at) VALUES (?,?,?, ?,1,?)",
            (content_hash, action, json.dumps(params), action_order, datetime.now().isoformat())
        )
        self.sqlite.commit()
        return cur.lastrowid

    def remove_edit(self, edit_id):
        cur = self.sqlite.cursor()
        cur.execute("DELETE FROM photo_edits WHERE edit_id = ?", (edit_id,))
        self.sqlite.commit()

    def clear_edits(self, content_hash, action=None):
        cur = self.sqlite.cursor()
        if action:
            cur.execute("DELETE FROM photo_edits WHERE content_hash = ? AND action = ?", (content_hash, action))
        else:
            cur.execute("DELETE FROM photo_edits WHERE content_hash = ?", (content_hash,))
        self.sqlite.commit()
