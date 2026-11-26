"""Backend configuration for AI Clipper 2.0 Web Application."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_DIR = Path(os.environ.get("CLIPPER_STORAGE_DIR", BASE_DIR / "storage")).resolve()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR = Path(os.environ.get("CLIPPER_ASSETS_DIR", BASE_DIR / "assets")).resolve()
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

_raw_db = os.environ.get("DATABASE_URL", f"sqlite:///{(STORAGE_DIR / 'clipper_web.db').as_posix()}")
if _raw_db.startswith("postgres://"):
    _raw_db = _raw_db.replace("postgres://", "postgresql+psycopg2://", 1)
elif _raw_db.startswith("postgresql://"):
    _raw_db = _raw_db.replace("postgresql://", "postgresql+psycopg2://", 1)
DATABASE_URL = _raw_db
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-change-this-in-production-ai-clipper-2")
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "72"))
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
