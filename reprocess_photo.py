#!/usr/bin/env python3
"""
reprocess_photo.py - Reprocess single photo: faces → describe → embed.

Usage:
    python reprocess_photo.py --hash <content_hash>
    python reprocess_photo.py --path <photo_path>

Resets all AI flags, deletes faces/embeddings, then runs the full chain.
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")


def log(msg):
    line = f"[{datetime.now().isoformat()}] [REPROCESS] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line)


def reset_photo(db, content_hash):
    path_row = db.sqlite.execute(
        "SELECT abs_path FROM catalog_files WHERE content_hash = ? AND is_canonical = 1 LIMIT 1",
        (content_hash,)
    ).fetchone()
    if not path_row:
        log(f"content_hash {content_hash} not found in catalog")
        return None
    path = path_row[0]

    face_count = db.sqlite.execute(
        "SELECT COUNT(*) FROM faces WHERE content_hash = ?", (content_hash,)
    ).fetchone()[0]

    log(f"Resetting {path}")
    log(f"  Deleting {face_count} face rows")

    db.sqlite.execute("DELETE FROM faces WHERE content_hash = ?", (content_hash,))
    db.sqlite.execute(
        "UPDATE catalog_files SET faces_done = 0, described = 0, embedded = 0 WHERE content_hash = ?",
        (content_hash,)
    )
    db.sqlite.execute(
        "UPDATE photos SET description = NULL, faces_present = 0, embedded = 0 WHERE path = ? AND deleted = 0",
        (path,)
    )

    try:
        db.delete_photo_embedding(content_hash)
        log("  Deleted photo embedding from LanceDB")
    except (ValueError, OSError, RuntimeError) as e:
        log(f"  LanceDB delete warning: {e}")

    try:
        db.face_vectors.delete(f"content_hash = '{content_hash}'")
    except (ValueError, OSError, RuntimeError):
        pass

    db.sqlite.commit()
    log("  Flags reset: faces_done=0, described=0, embedded=0, description=NULL")
    return path


def run_step(name, cmd):
    import subprocess
    log(f"START: {name}")
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent / "src")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in proc.stdout:
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            print(text, flush=True)
    proc.wait()
    elapsed = time.time() - t0
    if proc.returncode == 0:
        log(f"DONE: {name} ({elapsed:.0f}s)")
    else:
        log(f"FAILED: {name} rc={proc.returncode} ({elapsed:.0f}s)")
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description="Reprocess single photo: faces → describe → embed")
    parser.add_argument("--hash", type=str, default="", help="content_hash of photo")
    parser.add_argument("--path", type=str, default="", help="Photo file path (lookup hash)")
    parser.add_argument("--skip-faces", action="store_true", help="Skip face detection")
    parser.add_argument("--skip-describe", action="store_true", help="Skip description")
    parser.add_argument("--skip-embed", action="store_true", help="Skip embedding")
    args = parser.parse_args()

    from database import DatabaseManager
    db = DatabaseManager()

    content_hash = args.hash
    if not content_hash and args.path:
        row = db.sqlite.execute(
            "SELECT content_hash FROM catalog_files WHERE abs_path = ? AND is_canonical = 1 LIMIT 1",
            (args.path,)
        ).fetchone()
        if row:
            content_hash = row[0]
        else:
            log(f"Path not found in catalog: {args.path}")
            return 1

    if not content_hash:
        log("Specify --hash or --path")
        return 1

    log(f"=== Reprocessing photo hash={content_hash[:16]}... ===")

    path = reset_photo(db, content_hash)
    if not path:
        return 1

    py = sys.executable
    base = str(Path(__file__).parent)

    if not args.skip_faces:
        rc = run_step("FACES", [py, f"{base}/faces.py", "--hash", content_hash, "--limit", "1", "--no-gpu-lock"])
        if rc != 0:
            log("FACES failed, aborting")
            return 1

    if not args.skip_describe:
        rc = run_step("DESCRIBE", [py, f"{base}/describe.py", "--hash", content_hash, "--limit", "1", "--batch-size", "1", "--no-gpu-lock"])
        if rc != 0:
            log("DESCRIBE failed, aborting")
            return 1

    if not args.skip_embed:
        rc = run_step("EMBED", [py, f"{base}/embed.py", "--hash", content_hash, "--limit", "1", "--no-gpu-lock"])
        if rc != 0:
            log("EMBED failed, aborting")
            return 1

    log("=== Reprocess complete ===")

    row = db.sqlite.execute(
        "SELECT cf.faces_done, cf.described, cf.embedded, p.description "
        "FROM catalog_files cf JOIN photos p ON p.path = cf.abs_path "
        "WHERE cf.content_hash = ? AND cf.is_canonical = 1",
        (content_hash,)
    ).fetchone()
    if row:
        log(f"  faces_done={row[0]} described={row[1]} embedded={row[2]}")
        if row[3]:
            log(f"  description: {row[3][:200]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
