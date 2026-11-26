"""SQLAlchemy models and database session management (PostgreSQL or SQLite)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    whisper_model = Column(String(32), default="base")
    use_gpu = Column(Boolean, default=True)
    default_preset = Column(String(64), default="High-Energy Creator Style")
    default_intensity = Column(String(32), default="HIGH ENERGY")
    default_category = Column(String(32), default="General Videos")
    enable_music = Column(Boolean, default=True)
    enable_sfx = Column(Boolean, default=True)
    youtube_api_key = Column(String(255), default="")
    twitch_client_id = Column(String(255), default="")
    twitch_oauth_token = Column(String(255), default="")

    user = relationship("User", back_populates="settings")


class Project(Base):
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    source_input = Column(Text, nullable=False)
    resolved_path = Column(Text, default="")
    platform = Column(String(32), default="local_file")
    category = Column(String(64), default="General Videos")
    preset = Column(String(64), default="High-Energy Creator Style")
    intensity = Column(String(32), default="HIGH ENERGY")
    duration = Column(Float, default=0.0)
    status = Column(String(32), default="queued")
    progress = Column(Float, default=0.0)
    status_message = Column(Text, default="Queued")
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="projects")
    clips = relationship("Clip", back_populates="project", cascade="all, delete-orphan")


class Clip(Base):
    __tablename__ = "clips"
    clip_id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    peak_time = Column(Float, default=0.0)
    category = Column(String(64), default="General Videos")
    language = Column(String(16), default="en")
    transcript_text = Column(Text, default="")
    score = Column(Float, default=0.0)
    explanation = Column(Text, default="")
    breakdown_json = Column(Text, nullable=False)
    timeline_json = Column(Text, nullable=False)
    video_path = Column(Text, default="")
    thumbnail_path = Column(Text, default="")
    encoder_used = Column(String(32), default="libx264")
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="clips")


class ExportRecord(Base):
    __tablename__ = "exports"
    export_id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    clip_id = Column(String(36), nullable=False)
    title = Column(String(255), nullable=False)
    output_path = Column(Text, nullable=False)
    width = Column(Integer, default=1080)
    height = Column(Integer, default=1920)
    duration = Column(Float, default=0.0)
    encoder_used = Column(String(32), default="libx264")
    created_at = Column(DateTime, default=utcnow)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
