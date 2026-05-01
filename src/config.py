"""Configuration for Gailery Photo Gallery"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

PHOTO_SHARE_PATH = Path(os.environ.get("PHOTO_SHARE_PATH", str(PROJECT_ROOT / "photos")))
DATA_DIR = Path(os.environ.get("GALLERY_DATA_DIR", str(PROJECT_ROOT / "data")))
MODELS_DIR = Path(os.environ.get("GALLERY_MODELS_DIR", str(PROJECT_ROOT / "models")))

def _apply_models_dir_override():
    global MODELS_DIR
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        override = db.get_setting("models_dir")
        if override and Path(override).is_dir():
            MODELS_DIR = Path(override)
    except Exception:
        pass

_apply_models_dir_override()
THUMBNAILS_DIR = Path(os.environ.get("GALLERY_THUMBNAILS_DIR", str(PROJECT_ROOT / "thumbnails")))
LOGS_DIR = Path(os.environ.get("GALLERY_LOGS_DIR", str(PROJECT_ROOT / "logs")))
LLAMA_CPP_DIR = Path(os.environ.get("LLAMA_CPP_DIR", "/opt/llama.cpp"))
VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(PROJECT_ROOT / "venv" / "bin" / "python3"))
LOG_FILE = LOGS_DIR / "pipeline.log"
FLAG_DIR = DATA_DIR / "pipeline_flags"

MQTT_HOST = os.environ.get("GALLERY_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("GALLERY_MQTT_PORT", "1883"))
MQTT_WS_PORT = int(os.environ.get("GALLERY_MQTT_WS_PORT", "9001"))
GPU_LOCK_TIMEOUT = int(os.environ.get("GALLERY_GPU_LOCK_TIMEOUT", "120"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Image processing
THUMBNAIL_SIZE = 512
THUMBNAIL_FORMAT = "WebP"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".raw", ".cr2", ".nef", ".arw", ".dng"}

# Face detection
FACE_DETECTION_MODEL = "retinaface"  # or "yolo26"
FACE_CONFIDENCE_THRESHOLD = 0.5

# Face embeddings
EMBEDDING_MODEL = "facenet"  # or "insightface"
EMBEDDING_DIMENSION = 128

# Database
LANCEDB_PATH = DATA_DIR / "lancedb"
PHOTOS_TABLE = "photos"
FACES_TABLE = "faces"
PERSONAS_TABLE = "personas"
CATALOG_ROOTS_TABLE = "catalog_roots"
CATALOG_FILES_TABLE = "catalog_files"
EMBEDDINGS_TABLE = "photo_embeddings"

EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIM = 1024

# Batch processing
BATCH_SIZE = 32
MAX_WORKERS = 4
