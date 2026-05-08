"""API endpoints for file catalog management"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import logging

from database import get_db
from config import VENV_PYTHON, LOG_FILE, PROJECT_ROOT, PHOTO_SHARE_PATH

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".raw", ".cr2", ".nef", ".arw", ".dng", ".heic"}
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class AddRootRequest(BaseModel):
    path: str
    alias: str = ""


@router.get("/roots")
async def get_roots():
    try:
        db = get_db()
        roots = db.get_catalog_roots()
        result = []
        for r in roots:
            rid = r["root_id"]
            files = db.get_catalog_files(root_id=rid)
            ingested = sum(1 for f in files if f.get("ingested"))
            described = sum(1 for f in files if f.get("described"))
            exif_done = sum(1 for f in files if f.get("exif_done"))
            faces_done = sum(1 for f in files if f.get("faces_done"))
            result.append({
                "root_id": rid,
                "root_path": r["root_path"],
                "alias": r.get("alias", ""),
                "scanned_at": r.get("scanned_at"),
                "enabled": bool(r.get("enabled", 1)),
                "file_count": len(files),
                "total_size": sum(f.get("size", 0) for f in files),
                "ingested": ingested,
                "described": described,
                "exif_done": exif_done,
                "faces_done": faces_done,
                "not_ingested": len(files) - ingested,
            })
        return result
    except Exception as e:
        logger.error(f"Failed to get roots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add_root")
async def add_root(req: AddRootRequest):
    try:
        db = get_db()
        from pathlib import Path
        root_path = str(Path(req.path).resolve())
        existing_roots = db.get_catalog_roots()
        for er in existing_roots:
            if er.get("root_path") == root_path:
                return {"ok": False, "error": "Root already registered"}

        import uuid
        root_id = str(uuid.uuid4())
        db.add_catalog_root(
            root_id=root_id,
            root_path=root_path,
            alias=req.alias or Path(root_path).name,
        )
        return {"ok": True, "root_id": root_id}
    except Exception as e:
        logger.error(f"Failed to add root: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan/{root_id}")
async def scan_root(root_id: str):
    import subprocess
    import os
    cmd = f"/usr/bin/nohup {VENV_PYTHON} {PROJECT_ROOT / 'scan_catalog.py'} --scan >> {LOG_FILE} 2>&1 &"
    from datetime import datetime
    with open(str(LOG_FILE), "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [CONTROL] Starting: catalog scan\n")
    os.system(cmd)
    return {"ok": True}


@router.get("/stats")
async def catalog_stats():
    try:
        db = get_db()
        roots = db.get_catalog_roots()
        all_files = db.get_catalog_files()

        total = len(all_files)
        ingested = sum(1 for f in all_files if f.get("ingested"))
        described = sum(1 for f in all_files if f.get("described"))
        exif_done = sum(1 for f in all_files if f.get("exif_done"))
        faces_done = sum(1 for f in all_files if f.get("faces_done"))
        total_size = sum(f.get("size", 0) for f in all_files)

        by_ext = {}
        for f in all_files:
            e = f.get("ext", "?")
            by_ext[e] = by_ext.get(e, 0) + 1

        dirs = set(f.get("parent_dir", "") for f in all_files)

        by_year = {}
        for f in all_files:
            d = f.get("parent_dir", "")
            for p in d.split("/"):
                if len(p) == 4 and p.isdigit():
                    by_year[p] = by_year.get(p, 0) + 1
                    break

        return {
            "roots": len(roots),
            "total_files": total,
            "total_dirs": len(dirs),
            "total_size": total_size,
            "ingested": ingested,
            "not_ingested": total - ingested,
            "described": described,
            "not_described": total - described,
            "exif_done": exif_done,
            "faces_done": faces_done,
            "by_ext": dict(sorted(by_ext.items(), key=lambda x: -x[1])[:15]),
            "by_year": dict(sorted(by_year.items())),
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree")
async def get_tree(root_id: str = "", path: str = "", limit: int = 200, offset: int = 0):
    import os
    from pathlib import Path
    try:
        db = get_db()
        root = db.get_catalog_root(root_id) if root_id else None
        root_path = root["root_path"] if root else ""

        if root_id:
            files = db.get_catalog_files(root_id=root_id)
        else:
            files = db.get_catalog_files()

        if path:
            filtered = [f for f in files if f.get("parent_dir", "").startswith(path)]
        else:
            filtered = files

        db_has_data = len(filtered) > 0

        if not db_has_data and root_path and os.path.isdir(root_path):
            scan_base = os.path.join(root_path, path) if path else root_path
            if os.path.isdir(scan_base):
                subdirs_list = []
                direct_files = []
                try:
                    for entry in sorted(os.scandir(scan_base), key=lambda e: e.name.lower()):
                        if entry.name.startswith("."):
                            continue
                        if entry.is_dir():
                            sub_files = [f for f in os.scandir(entry.path) if not f.name.startswith(".")]
                            photo_count = sum(1 for f in sub_files if Path(f.name).suffix.lower() in SUPPORTED_EXTS)
                            subdirs_list.append({
                                "name": entry.name,
                                "total": photo_count,
                                "ingested": 0, "described": 0, "exif_done": 0,
                                "faces_done": 0, "embedded": 0, "pct_done": 0,
                            })
                        elif entry.is_file() and Path(entry.name).suffix.lower() in SUPPORTED_EXTS:
                            try:
                                sz = entry.stat().st_size
                            except OSError:
                                sz = 0
                            direct_files.append({
                                "file_id": "",
                                "rel_path": os.path.relpath(entry.path, root_path) if root_path else entry.name,
                                "abs_path": entry.path,
                                "ext": Path(entry.name).suffix.lower(),
                                "file_size": sz,
                                "ingested": False, "described": False, "exif_done": False,
                                "faces_done": False, "embedded": False, "description": None,
                            })
                except PermissionError:
                    pass

                return {
                    "path": path,
                    "subdirs": subdirs_list,
                    "total_files": len(direct_files),
                    "files": direct_files[offset:offset + limit],
                    "scanned": False,
                }

        subdirs = {}
        direct_files = []
        for f in filtered:
            pd = f.get("parent_dir", "")
            if pd == path:
                direct_files.append(f)
            else:
                rel = pd[len(path):].lstrip("/") if path else pd
                first = rel.split("/")[0]
                if first:
                    if first not in subdirs:
                        subdirs[first] = {"total": 0, "ingested": 0, "described": 0, "exif_done": 0, "faces_done": 0, "embedded": 0}
                    subdirs[first]["total"] += 1
                    if f.get("ingested"):
                        subdirs[first]["ingested"] += 1
                    if f.get("described"):
                        subdirs[first]["described"] += 1
                    if f.get("exif_done"):
                        subdirs[first]["exif_done"] += 1
                    if f.get("faces_done"):
                        subdirs[first]["faces_done"] += 1
                    if f.get("embedded"):
                        subdirs[first]["embedded"] += 1

        total_files = len(direct_files)
        page = direct_files[offset:offset + limit]

        result_files = []
        import sqlite3 as sq
        sq_cur = db.sqlite.cursor()
        for f in page:
            rel = f.get("rel_path", "")
            desc_row = sq_cur.execute(
                "SELECT description FROM photos WHERE path = ?",
                (str(PHOTO_SHARE_PATH) + "/" + rel,) if rel else ("",)
            ).fetchone()
            description = desc_row[0] if desc_row else None
            result_files.append({
                "file_id": f["file_id"],
                "rel_path": f["rel_path"],
                "abs_path": f.get("abs_path", ""),
                "ext": f.get("ext", ""),
                "file_size": f.get("size", 0),
                "ingested": bool(f.get("ingested")),
                "described": bool(f.get("described")),
                "exif_done": bool(f.get("exif_done")),
                "faces_done": bool(f.get("faces_done")),
                "embedded": bool(f.get("embedded")),
                "description": description,
            })

        subdirs_list = []
        for name in sorted(subdirs.keys()):
            s = subdirs[name]
            t = s["total"]
            subdirs_list.append({
                "name": name,
                "total": t,
                "ingested": s["ingested"],
                "described": s["described"],
                "exif_done": s["exif_done"],
                "faces_done": s["faces_done"],
                "embedded": s["embedded"],
                "pct_done": round((s["described"] + s["exif_done"] + s["embedded"]) / max(t * 3, 1) * 100),
            })

        return {
            "path": path,
            "subdirs": subdirs_list,
            "total_files": total_files,
            "files": result_files,
            "scanned": True,
        }
    except Exception as e:
        logger.error(f"Failed to get tree: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_flags():
    import subprocess
    import os
    cmd = f"/usr/bin/nohup {VENV_PYTHON} {PROJECT_ROOT / 'scan_catalog.py'} --sync >> {LOG_FILE} 2>&1 &"
    from datetime import datetime
    with open(str(LOG_FILE), "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [CONTROL] Starting: catalog sync\n")
    os.system(cmd)
    return {"ok": True}


@router.delete("/root/{root_id}")
async def delete_root(root_id: str):
    try:
        db = get_db()
        db.delete_catalog_root(root_id)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to delete root: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/root/{root_id}/toggle")
async def toggle_root(root_id: str):
    try:
        db = get_db()
        root = db.get_catalog_root(root_id)
        if not root:
            raise HTTPException(status_code=404, detail="Root not found")
        new_val = 0 if root.get("enabled", 1) else 1
        db.update_catalog_root(root_id, enabled=new_val)
        return {"ok": True, "enabled": bool(new_val)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle root: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locate")
async def locate_photo(path: str = ""):
    try:
        db = get_db()

        row = db.sqlite.execute(
            "SELECT cf.root_id, cf.parent_dir FROM catalog_files cf WHERE cf.abs_path = ?",
            (path,)
        ).fetchone()

        if row:
            root = db.get_catalog_root(row[0])
            return {
                "found": True,
                "root_id": row[0],
                "parent_dir": row[1],
                "root_alias": root.get("alias", "") if root else "",
            }

        roots = db.get_catalog_roots()
        for root in roots:
            rp = root.get("root_path", "")
            if rp and path.startswith(rp + "/"):
                rel = path[len(rp):].lstrip("/")
                parts = rel.split("/")
                parent_dir = "/".join(parts[:-1]) if len(parts) > 1 else ""
                return {
                    "found": True,
                    "root_id": root["root_id"],
                    "parent_dir": parent_dir,
                    "root_alias": root.get("alias", ""),
                }

        return {"found": False}
    except Exception as e:
        logger.error(f"Failed to locate photo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/browse")
async def browse_dirs(path: str = ""):
    import os
    from pathlib import Path
    try:
        base = Path(path) if path else Path("/")
        if not base.is_dir():
            base = Path("/")
        entries = []
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    entries.append({
                        "name": entry.name,
                        "path": str(entry),
                    })
                except PermissionError:
                    pass
        return {"path": str(base), "dirs": entries}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        logger.error(f"Failed to browse dirs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hash_status")
async def hash_status():
    try:
        db = get_db()
        total = db.count_catalog_files()
        with_hash = db.sqlite.execute(
            "SELECT COUNT(*) FROM catalog_files WHERE content_hash IS NOT NULL"
        ).fetchone()[0]
        without_hash = total - with_hash
        zero_byte = db.sqlite.execute(
            "SELECT COUNT(*) FROM catalog_files WHERE content_hash IS NULL AND size = 0"
        ).fetchone()[0]
        pending_hash = without_hash - zero_byte
        duplicates = db.sqlite.execute(
            "SELECT COUNT(*) FROM (SELECT content_hash FROM catalog_files "
            "WHERE content_hash IS NOT NULL GROUP BY content_hash HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        dup_files = db.sqlite.execute(
            "SELECT COUNT(*) FROM catalog_files WHERE content_hash IN "
            "(SELECT content_hash FROM catalog_files WHERE content_hash IS NOT NULL "
            "GROUP BY content_hash HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        return {
            "total_files": total,
            "with_hash": with_hash,
            "without_hash": without_hash,
            "zero_byte": zero_byte,
            "pending_hash": pending_hash,
            "duplicate_groups": duplicates,
            "duplicate_files": dup_files,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hash_backfill")
async def hash_backfill():
    import subprocess, os
    try:
        venv_python = os.environ.get("GALLERY_VENV_PYTHON", str(PROJECT_ROOT / "venv" / "bin" / "python3"))
        script = str(PROJECT_ROOT / "scan_catalog.py")
        proc = subprocess.Popen(
            [venv_python, script, "--hash"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return {"ok": True, "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates")
async def find_duplicates(limit: int = 50):
    try:
        db = get_db()
        rows = db.sqlite.execute(
            "SELECT content_hash, COUNT(*) as cnt, "
            "GROUP_CONCAT(abs_path, '|') as paths "
            "FROM catalog_files WHERE content_hash IS NOT NULL "
            "GROUP BY content_hash HAVING COUNT(*) > 1 "
            "ORDER BY cnt DESC LIMIT ?",
            (limit,)
        ).fetchall()
        result = []
        for r in rows:
            paths = r[2].split("|") if r[2] else []
            result.append({
                "hash": r[0],
                "count": r[1],
                "paths": paths,
            })
        return {"duplicates": result, "total_groups": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hash_backfill_stop")
async def hash_backfill_stop():
    import os, signal
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "scan_catalog.py.*--hash"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split("\n") if result.stdout.strip() else []
        killed = []
        for pid_str in pids:
            try:
                pid = int(pid_str.strip())
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except (ValueError, ProcessLookupError):
                pass
        return {"ok": True, "killed": killed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hash_backfill_status")
async def hash_backfill_status():
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "scan_catalog.py.*--hash"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split("\n") if result.stdout.strip() else []
        running = [int(p.strip()) for p in pids if p.strip().isdigit()]
        return {"running": len(running) > 0, "pids": running}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
