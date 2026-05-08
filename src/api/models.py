"""API endpoints for model management"""

import hashlib
import os
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from config import PROJECT_ROOT, MODELS_DIR, LOG_FILE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])

# SHA256 hashes verified against HuggingFace LFS on 2026-05-01
# All models traceable to HF repos — integrity guaranteed by LFS sha256

KNOWN_MODELS = [
    {
        "id": "qwen3-vlm",
        "name": "Qwen3.5-4B VLM (llama.cpp)",
        "repo": "unsloth/Qwen3.5-4B-GGUF",
        "type": "gguf",
        "role": "Описание фотографий",
        "files": [
            {
                "name": "Qwen3.5-4B-Q4_K_M.gguf",
                "path": "gguf/Qwen3.5-4B-Q4_K_M.gguf",
                "sha256": "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
                "size": 2740937888,
                "hf_repo": "unsloth/Qwen3.5-4B-GGUF",
                "hf_file": "Qwen3.5-4B-Q4_K_M.gguf",
            },
            {
                "name": "mmproj-BF16.gguf",
                "path": "gguf/mmproj-BF16.gguf",
                "sha256": "302b92d565080b9cc0281186979ae75a7429ec23d14f6f7607a035539b21f3a6",
                "size": 675569344,
                "hf_repo": "unsloth/Qwen3.5-4B-GGUF",
                "hf_file": "mmproj-BF16.gguf",
            },
        ],
        "used_by": "vision_describe.py",
    },
    {
        "id": "qwen3-embed",
        "name": "Qwen3-Embedding-0.6B (GGUF)",
        "repo": "Qwen/Qwen3-Embedding-0.6B-GGUF",
        "type": "gguf",
        "role": "Эмбеддинги фото (pipeline + поиск)",
        "files": [
            {
                "name": "Qwen3-Embedding-0.6B-F16.gguf",
                "path": "gguf/Qwen3-Embedding-0.6B-F16.gguf",
                "sha256": "421a27e58d165478cc7acb984a688c2aa41404968b0203e7cd743ece44c54340",
                "size": 1197629632,
                "hf_repo": "Qwen/Qwen3-Embedding-0.6B-GGUF",
                "hf_file": "Qwen3-Embedding-0.6B-f16.gguf",
            },
        ],
        "used_by": "embed.py, semantic_search.py",
    },
    {
        "id": "qwen3-text",
        "name": "Qwen3.5-4B Text (llama.cpp)",
        "repo": "unsloth/Qwen3.5-4B-GGUF",
        "type": "gguf",
        "role": "Обогащение описаний (enrich)",
        "files": [
            {
                "name": "Qwen3.5-4B-Q4_K_M.gguf",
                "path": "gguf/Qwen3.5-4B-Q4_K_M.gguf",
                "sha256": "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
                "size": 2740937888,
                "hf_repo": "unsloth/Qwen3.5-4B-GGUF",
                "hf_file": "Qwen3.5-4B-Q4_K_M.gguf",
            },
        ],
        "note": "Совместно с VLM — тот же gguf-файл",
        "used_by": "enrich_description.py",
    },
    {
        "id": "insightface",
        "name": "InsightFace buffalo_l",
        "repo": "DavidHoa/buffalo_l",
        "type": "onnx",
        "role": "Детекция лиц и эмбеддинги",
        "files": [
            {
                "name": "det_10g.onnx",
                "path": "insightface/models/buffalo_l/det_10g.onnx",
                "sha256": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
                "size": 16923827,
                "hf_repo": "DavidHoa/buffalo_l",
                "hf_file": "det_10g.onnx",
            },
            {
                "name": "w600k_r50.onnx",
                "path": "insightface/models/buffalo_l/w600k_r50.onnx",
                "sha256": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
                "size": 174383860,
                "hf_repo": "DavidHoa/buffalo_l",
                "hf_file": "w600k_r50.onnx",
            },
            {
                "name": "1k3d68.onnx",
                "path": "insightface/models/buffalo_l/1k3d68.onnx",
                "sha256": "df5c06b8a0c12e422b2ed8947b8869faa4105387f199c477af038aa01f9a45cc",
                "size": 143607619,
                "hf_repo": "DavidHoa/buffalo_l",
                "hf_file": "1k3d68.onnx",
            },
            {
                "name": "2d106det.onnx",
                "path": "insightface/models/buffalo_l/2d106det.onnx",
                "sha256": "f001b856447c413801ef5c42091ed0cd516fcd21f2d6b79635b1e733a7109dbf",
                "size": 5030888,
                "hf_repo": "DavidHoa/buffalo_l",
                "hf_file": "2d106det.onnx",
            },
            {
                "name": "genderage.onnx",
                "path": "insightface/models/buffalo_l/genderage.onnx",
                "sha256": "4fde69b1c810857b88c64a335084f1c3fe8f01246c9a191b48c7bb756d6652fb",
                "size": 1322532,
                "hf_repo": "DavidHoa/buffalo_l",
                "hf_file": "genderage.onnx",
            },
        ],
        "used_by": "faces.py",
    },
]


_models_cache = {"ts": 0, "data": None}
_CACHE_TTL = 300


def _get_hf_token():
    try:
        from database import get_db
        db = get_db()
        return db.get_setting("hf_token") or ""
    except Exception:
        return ""


def _sha256_file(path, block_size=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _check_model_file(file_info, verify_hash=False):
    p = MODELS_DIR / file_info["path"]
    exists = p.exists()
    size_mb = p.stat().st_size / 1e6 if exists else 0
    expected_sha = file_info.get("sha256", "")
    expected_size = file_info.get("size", 0)
    sha256_ok = None
    sha256_actual = None
    size_ok = None
    if exists:
        actual_size = p.stat().st_size
        size_ok = actual_size == expected_size
    if exists and verify_hash and expected_sha:
        sha256_actual = _sha256_file(str(p))
        sha256_ok = sha256_actual == expected_sha
    return {
        "name": file_info["name"],
        "path": str(p),
        "exists": exists,
        "size_mb": round(size_mb, 1),
        "sha256_ok": sha256_ok,
        "sha256_actual": sha256_actual,
        "size_ok": size_ok,
        "hf_repo": file_info.get("hf_repo", ""),
        "hf_file": file_info.get("hf_file", ""),
    }


@router.get("")
async def list_models():
    import time as _t
    now = _t.time()
    if _models_cache["data"] and (now - _models_cache["ts"]) < _CACHE_TTL:
        return _models_cache["data"]

    token = _get_hf_token()
    result = []
    for m in KNOWN_MODELS:
        info = {
            "id": m["id"],
            "name": m["name"],
            "repo": m["repo"],
            "type": m["type"],
            "role": m["role"],
            "used_by": m.get("used_by", ""),
            "note": m.get("note", ""),
        }

        files = [_check_model_file(f) for f in m["files"]]
        info["files"] = files
        info["present"] = all(f["exists"] for f in files)
        info["verified"] = all(f.get("sha256_ok") for f in files if f["exists"]) if info["present"] else False
        info["size_ok"] = all(f.get("size_ok") for f in files if f["exists"]) if info["present"] else False
        info["total_size_mb"] = round(sum(f["size_mb"] for f in files), 1)

        result.append(info)

    data = {"models": result, "hf_token_set": bool(token), "models_dir": str(MODELS_DIR)}
    _models_cache["ts"] = now
    _models_cache["data"] = data
    return data


@router.post("/download/{model_id}")
async def download_model(model_id: str):
    model = None
    for m in KNOWN_MODELS:
        if m["id"] == model_id:
            model = m
            break
    if not model:
        raise HTTPException(404, f"Unknown model: {model_id}")


@router.get("/dir")
async def get_models_dir():
    return {"models_dir": str(MODELS_DIR), "env_var": "GALLERY_MODELS_DIR"}


@router.put("/dir")
async def set_models_dir(request: Request):
    from database import get_db
    body = await request.json()
    path = body.get("path", "")
    if not path:
        raise HTTPException(400, "path is required")
    p = Path(path).resolve()
    if not p.exists():
        raise HTTPException(400, f"Directory does not exist: {p}")
    if not p.is_dir():
        raise HTTPException(400, f"Not a directory: {p}")
        db = get_db()
    db.set_setting("models_dir", str(p))
    import config
    config.MODELS_DIR = p
    _models_cache["data"] = None
    return {"models_dir": str(p), "note": "Путь сохранён. Перезапустите воркеры для полного применения."}


@router.get("/check/{model_id}")
async def check_model(model_id: str):
    for m in KNOWN_MODELS:
        if m["id"] == model_id:
            files = [_check_model_file(f, verify_hash=True) for f in m["files"]]
            present = all(f["exists"] for f in files)
            verified = all(f.get("sha256_ok") for f in files if f["exists"]) if present else False
            return {"present": present, "verified": verified, "files": files}
    raise HTTPException(404, f"Unknown model: {model_id}")
