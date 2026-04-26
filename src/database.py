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
            CREATE INDEX IF NOT EXISTS idx_photos_effective_date ON photos(COALESCE(manual_date, date));
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

        cur.execute("PRAGMA table_info(photos)")
        columns = [row[1] for row in cur.fetchall()]
        if 'manual_gps' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN manual_gps INTEGER DEFAULT 0")
            self.sqlite.commit()
            logger.info("Migration: added manual_gps column to photos table")
        if 'manual_date' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN manual_date TEXT")
            self.sqlite.commit()
            logger.info("Migration: added manual_date column to photos table")
        if 'deleted' not in columns:
            cur.execute("ALTER TABLE photos ADD COLUMN deleted INTEGER DEFAULT 0")
            self.sqlite.commit()
            logger.info("Migration: added deleted column to photos table")

    def _open_vector_tables(self):
        if "photo_embeddings" not in self.vectordb.table_names():
            schema = pa.schema([
                pa.field("photo_id", pa.string()),
                pa.field("search_text", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), 1024)),
                pa.field("meta_hash", pa.string()),
                pa.field("embedded_at", pa.string()),
            ])
            self.vectordb.create_table("photo_embeddings", schema=schema)

        if "face_vectors" not in self.vectordb.table_names():
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

    def search_photos(self, q=None, person=None, date_from=None, date_to=None,
                      date_after=None, date_before=None,
                      path_after=None, path_before=None,
                      has_faces=None, no_description=None, has_issues=None,
                      issue_type=None, photo_type=None, has_gps=None,
                      no_date=None, has_description=None,
                      deleted=None, deleted_only=None,
                      sort="date_desc", limit=60, offset=0):
        ed = "COALESCE(manual_date, date)"
        sql = "SELECT *, " + ed + " as effective_date FROM photos WHERE 1=1"
        params = []

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

        count_sql = sql.replace("SELECT *", "SELECT COUNT(*)", 1)
        total = self.sqlite.execute(count_sql, params).fetchone()[0]

        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.sqlite.execute(sql, params).fetchall()
        return total, _rows_to_dicts(rows)

    def get_all_photos(self):
        rows = self.sqlite.execute("SELECT * FROM photos").fetchall()
        return _rows_to_dicts(rows)

    def get_date_histogram(self):
        ed = "COALESCE(manual_date, date)"
        rows = self.sqlite.execute(
            f"SELECT substr({ed},1,4) as year, substr({ed},1,7) as month, COUNT(*) as cnt "
            f"FROM photos WHERE {ed} IS NOT NULL AND length({ed}) >= 4 "
            f"AND substr({ed},1,4) != '0000' AND deleted = 0 "
            f"GROUP BY year, month ORDER BY year, month"
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
            "SELECT face_id, persona_id FROM faces"
        ).fetchall()
        vec_rows = self.face_vectors.search().select(["face_id", "embedding"]).limit(100000).to_list()
        vec_map = {v["face_id"]: v["embedding"] for v in vec_rows}
        result = []
        for f in faces:
            fid, pid = f[0], f[1]
            emb = vec_map.get(fid)
            if emb:
                result.append({"face_id": fid, "persona_id": pid, "embedding": emb})
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
                "parent_dir,ext,size,modified,ingested,described,exif_done,faces_done,embedded) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.get("file_id", str(uuid.uuid4())),
                 r.get("root_id"), r.get("rel_path"), r.get("abs_path"),
                 r.get("parent_dir"), r.get("ext"),
                 r.get("size", 0), r.get("modified"),
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
        photos_total = self.count_photos(where="deleted = 0")
        photos_deleted = self.count_photos(where="deleted = 1")
        described = self.count_photos("description IS NOT NULL AND description != ''")
        faces_flagged = self.count_photos("faces_present = 1")
        exif_done = self.count_photos("exif_checked = 1")
        faces_processed = self.sqlite.execute(
            "SELECT COUNT(DISTINCT photo_id) FROM faces"
        ).fetchone()[0]
        embedded = self.sqlite.execute("SELECT COUNT(*) FROM photos WHERE embedded = 1").fetchone()[0]
        catalog_total = self.count_catalog_files()
        personas_total = self.sqlite.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
        faces_total = self.count_faces()
        with_persona = self.count_faces("persona_id IS NOT NULL")
        no_cluster = self.count_faces("persona_id IS NULL")

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
            "catalog_faces_not": faces_flagged - faces_processed,
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
            "faces_not_done": faces_flagged - faces_processed,
        }
