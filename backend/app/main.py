"""FastAPI backend application for AI Clipper 2.0 Web."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from clipper_engine import (
    ContentCategory,
    EditingIntensity,
    EditingPreset,
    EditTimeline,
    HighlightSignalBreakdown,
    ProjectConfig,
    available_music_tracks,
    classify_source,
    detect_hardware,
)

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .config import CORS_ORIGINS, STORAGE_DIR
from .db import Clip, ExportRecord, Project, User, UserSettings, get_db, init_db
from .tasks import broker

init_db()

app = FastAPI(title="AI Clipper 2.0 Web API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterReq(BaseModel):
    email: str
    full_name: str
    password: str


class LoginReq(BaseModel):
    email: str
    password: str


class UrlProjectReq(BaseModel):
    source_url: str
    category: ContentCategory = ContentCategory.GENERAL
    preset: EditingPreset = EditingPreset.HIGH_ENERGY
    intensity: EditingIntensity = EditingIntensity.HIGH_ENERGY
    preferred_duration: Optional[int] = None
    max_clips: int = 4
    language: str = "auto"
    enable_music: bool = True
    enable_sfx: bool = True


class LiveStartReq(BaseModel):
    stream_url: str
    category: ContentCategory = ContentCategory.GAMING
    preset: EditingPreset = EditingPreset.GAMING_VIRAL
    intensity: EditingIntensity = EditingIntensity.HIGH_ENERGY
    buffer_seconds: int = 120
    sensitivity: float = 65.0


class BatchExportReq(BaseModel):
    clip_ids: List[str]


class SettingsReq(BaseModel):
    whisper_model: str = "base"
    use_gpu: bool = True
    default_preset: str = EditingPreset.HIGH_ENERGY.value
    default_intensity: str = EditingIntensity.HIGH_ENERGY.value
    default_category: str = ContentCategory.GENERAL.value
    enable_music: bool = True
    enable_sfx: bool = True
    youtube_api_key: str = ""
    twitch_client_id: str = ""
    twitch_oauth_token: str = ""


def _user_settings_or_default(db: Session, user_id: str) -> UserSettings:
    st = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not st:
        st = UserSettings(user_id=user_id)
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


@app.get("/api/health")
def health():
    hw = detect_hardware()
    return {
        "status": "ok",
        "hardware": hw.model_dump(),
        "redis_connected": broker.redis_connected,
        "music_tracks": available_music_tracks(),
        "presets": [p.value for p in EditingPreset],
        "intensities": [i.value for i in EditingIntensity],
        "categories": [c.value for c in ContentCategory],
    }


@app.post("/api/auth/register")
def register(req: RegisterReq, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not email or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Valid email and password (>= 6 chars) required")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email is already registered")
    uid = uuid.uuid4().hex
    user = User(id=uid, email=email, full_name=req.full_name.strip() or "Creator", password_hash=hash_password(req.password))
    db.add(user)
    db.add(UserSettings(user_id=uid))
    db.commit()
    token = create_access_token(uid, email)
    return {"access_token": token, "user": {"id": uid, "email": email, "full_name": user.full_name}}


@app.post("/api/auth/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email)
    return {"access_token": token, "user": {"id": user.id, "email": user.email, "full_name": user.full_name}}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.user_id == user.id).order_by(Project.created_at.desc()).all()
    clips = db.query(Clip).filter(Clip.user_id == user.id).order_by(Clip.score.desc()).all()
    exports = db.query(ExportRecord).filter(ExportRecord.user_id == user.id).count()
    avg_score = round(sum(c.score for c in clips) / len(clips), 1) if clips else 0.0
    hw = detect_hardware()
    return {
        "stats": {
            "projects": len(projects),
            "clips": len(clips),
            "exports": exports,
            "avg_score": avg_score,
            "encoder": hw.preferred_video_encoder,
            "whisper_device": hw.whisper_device,
        },
        "recent_projects": [
            {
                "id": p.id,
                "title": p.title,
                "platform": p.platform,
                "category": p.category,
                "preset": p.preset,
                "status": p.status,
                "progress": p.progress,
                "status_message": p.status_message,
                "created_at": p.created_at.isoformat() if p.created_at else "",
            }
            for p in projects[:10]
        ],
        "top_clips": [
            {
                "clip_id": c.clip_id,
                "title": c.title,
                "score": c.score,
                "duration": c.duration,
                "category": c.category,
                "explanation": c.explanation,
            }
            for c in clips[:4]
        ],
    }


@app.post("/api/projects/upload")
async def create_upload_project(
    file: UploadFile = File(...),
    category: ContentCategory = Form(ContentCategory.GENERAL),
    preset: EditingPreset = Form(EditingPreset.HIGH_ENERGY),
    intensity: EditingIntensity = Form(EditingIntensity.HIGH_ENERGY),
    preferred_duration: Optional[int] = Form(None),
    max_clips: int = Form(4),
    language: str = Form("auto"),
    enable_music: bool = Form(True),
    enable_sfx: bool = Form(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    upload_dir = STORAGE_DIR / "uploads" / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.mp4").name
    dest = upload_dir / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    st = _user_settings_or_default(db, user.id)
    proj = Project(
        id=project_id,
        user_id=user.id,
        title=Path(safe_name).stem,
        source_input=str(dest),
        resolved_path=str(dest),
        platform="local_file",
        category=category.value,
        preset=preset.value,
        intensity=intensity.value,
        status="queued",
        progress=0.02,
        status_message="Uploaded; queued for AI analysis",
    )
    db.add(proj)
    db.commit()

    cfg = ProjectConfig(
        source=str(dest),
        category=category,
        preset=preset,
        intensity=intensity,
        preferred_duration=preferred_duration,
        max_clips=max(1, min(15, max_clips)),
        language=language,
        whisper_model=st.whisper_model,
        use_gpu=st.use_gpu,
        enable_music=enable_music,
        enable_sfx=enable_sfx,
        youtube_api_key=st.youtube_api_key or None,
        twitch_client_id=st.twitch_client_id or None,
        twitch_oauth_token=st.twitch_oauth_token or None,
    )
    broker.submit_project(project_id, user.id, cfg)
    return {"project_id": project_id, "status": "queued"}


@app.post("/api/projects/url")
def create_url_project(req: UrlProjectReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not req.source_url.strip():
        raise HTTPException(status_code=400, detail="source_url is required")
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    plat = classify_source(req.source_url).value
    st = _user_settings_or_default(db, user.id)
    proj = Project(
        id=project_id,
        user_id=user.id,
        title=req.source_url[:60],
        source_input=req.source_url,
        platform=plat,
        category=req.category.value,
        preset=req.preset.value,
        intensity=req.intensity.value,
        status="queued",
        progress=0.02,
        status_message="Queued URL ingestion",
    )
    db.add(proj)
    db.commit()

    cfg = ProjectConfig(
        source=req.source_url,
        category=req.category,
        preset=req.preset,
        intensity=req.intensity,
        preferred_duration=req.preferred_duration,
        max_clips=max(1, min(15, req.max_clips)),
        language=req.language,
        whisper_model=st.whisper_model,
        use_gpu=st.use_gpu,
        enable_music=req.enable_music,
        enable_sfx=req.enable_sfx,
        youtube_api_key=st.youtube_api_key or None,
        twitch_client_id=st.twitch_client_id or None,
        twitch_oauth_token=st.twitch_oauth_token or None,
    )
    broker.submit_project(project_id, user.id, cfg)
    return {"project_id": project_id, "status": "queued"}


@app.get("/api/projects")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Project).filter(Project.user_id == user.id).order_by(Project.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "platform": p.platform,
            "category": p.category,
            "preset": p.preset,
            "intensity": p.intensity,
            "status": p.status,
            "progress": p.progress,
            "status_message": p.status_message,
            "created_at": p.created_at.isoformat() if p.created_at else "",
        }
        for p in rows
    ]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": p.id,
        "title": p.title,
        "status": p.status,
        "progress": p.progress,
        "status_message": p.status_message,
    }


@app.websocket("/ws/jobs/{project_id}")
async def ws_job_progress(websocket: WebSocket, project_id: str, db: Session = Depends(get_db)):
    await websocket.accept()
    try:
        while True:
            p = db.query(Project).filter(Project.id == project_id).first()
            db.expire_all()
            if not p:
                await websocket.send_json({"status": "not_found", "progress": 0, "message": "Not found"})
                break
            await websocket.send_json({"status": p.status, "progress": p.progress, "message": p.status_message})
            if p.status in ("completed", "failed"):
                break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass


@app.post("/api/live/start")
def start_live(req: LiveStartReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = _user_settings_or_default(db, user.id)
    pid = broker.start_live(
        user_id=user.id,
        stream_url=req.stream_url,
        category=req.category,
        preset=req.preset,
        intensity=req.intensity,
        buffer_seconds=req.buffer_seconds,
        sensitivity=req.sensitivity,
        youtube_api_key=st.youtube_api_key or None,
        twitch_oauth_token=st.twitch_oauth_token or None,
    )
    return {"project_id": pid, "status": "monitoring"}


@app.post("/api/live/stop")
def stop_live(user: User = Depends(get_current_user)):
    broker.stop_live(user.id)
    return {"status": "stopped"}


@app.get("/api/live/status")
def live_status(user: User = Depends(get_current_user)):
    return broker.get_live_status(user.id)


@app.get("/api/clips")
def list_clips(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Clip).filter(Clip.user_id == user.id).order_by(Clip.score.desc(), Clip.created_at.desc()).all()
    return [
        {
            "clip_id": c.clip_id,
            "project_id": c.project_id,
            "title": c.title,
            "start_time": c.start_time,
            "end_time": c.end_time,
            "duration": c.duration,
            "category": c.category,
            "language": c.language,
            "score": c.score,
            "explanation": c.explanation,
            "breakdown": json.loads(c.breakdown_json),
            "timeline": json.loads(c.timeline_json),
            "encoder_used": c.encoder_used,
            "has_video": bool(c.video_path and Path(c.video_path).exists()),
        }
        for c in rows
    ]


@app.get("/api/clips/{clip_id}")
def get_clip(clip_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Clip).filter(Clip.clip_id == clip_id, Clip.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Clip not found")
    return {
        "clip_id": c.clip_id,
        "project_id": c.project_id,
        "title": c.title,
        "start_time": c.start_time,
        "end_time": c.end_time,
        "duration": c.duration,
        "category": c.category,
        "language": c.language,
        "transcript_text": c.transcript_text,
        "score": c.score,
        "explanation": c.explanation,
        "breakdown": json.loads(c.breakdown_json),
        "timeline": json.loads(c.timeline_json),
        "encoder_used": c.encoder_used,
    }


@app.put("/api/clips/{clip_id}/timeline")
def update_clip_timeline(
    clip_id: str,
    timeline: EditTimeline,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.query(Clip).filter(Clip.clip_id == clip_id, Clip.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Clip not found")
    c.timeline_json = timeline.model_dump_json()
    c.start_time = timeline.trim_start
    c.end_time = timeline.trim_end
    c.duration = round(max(1.0, timeline.trim_end - timeline.trim_start), 2)
    db.commit()
    return {"status": "saved", "timeline": json.loads(c.timeline_json)}


@app.post("/api/clips/{clip_id}/render")
def render_edited_clip(clip_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Clip).filter(Clip.clip_id == clip_id, Clip.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Clip not found")
    st = _user_settings_or_default(db, user.id)
    try:
        res = broker.rerender_clip(clip_id, use_gpu=st.use_gpu)
        return res.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/clips/{clip_id}")
def delete_clip(clip_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Clip).filter(Clip.clip_id == clip_id, Clip.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Clip not found")
    db.delete(c)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/clips/{clip_id}/video")
def stream_clip_video(clip_id: str, token: Optional[str] = None, db: Session = Depends(get_db)):
    # Allow query token for HTML5 <video src="..."> playback
    import jwt as _jwt
    from .config import JWT_SECRET_KEY

    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = _jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        uid = payload.get("sub")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    c = db.query(Clip).filter(Clip.clip_id == clip_id, Clip.user_id == uid).first()
    if not c or not c.video_path or not Path(c.video_path).exists():
        raise HTTPException(status_code=404, detail="Rendered video not found")
    return FileResponse(c.video_path, media_type="video/mp4", filename=f"{clip_id}.mp4")


@app.get("/api/clips/{clip_id}/thumbnail")
def get_clip_thumbnail(clip_id: str, token: Optional[str] = None, db: Session = Depends(get_db)):
    import jwt as _jwt
    from .config import JWT_SECRET_KEY

    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        uid = _jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"]).get("sub")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    c = db.query(Clip).filter(Clip.clip_id == clip_id, Clip.user_id == uid).first()
    if not c or not c.thumbnail_path or not Path(c.thumbnail_path).exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(c.thumbnail_path, media_type="image/jpeg")


@app.post("/api/clips/batch-export")
def batch_export(req: BatchExportReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clips = db.query(Clip).filter(Clip.user_id == user.id, Clip.clip_id.in_(req.clip_ids)).all()
    if not clips:
        raise HTTPException(status_code=404, detail="No matching clips found")
    export_dir = STORAGE_DIR / "exports" / user.id
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / f"ai_clipper_batch_{uuid.uuid4().hex[:6]}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in clips:
            if c.video_path and Path(c.video_path).exists():
                zf.write(c.video_path, arcname=f"{c.clip_id}.mp4")
                db.add(
                    ExportRecord(
                        export_id=f"exp_{uuid.uuid4().hex[:8]}",
                        user_id=user.id,
                        clip_id=c.clip_id,
                        title=c.title,
                        output_path=c.video_path,
                        width=1080,
                        height=1920,
                        duration=c.duration,
                        encoder_used=c.encoder_used,
                    )
                )
    db.commit()
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/exports")
def list_exports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ExportRecord).filter(ExportRecord.user_id == user.id).order_by(ExportRecord.created_at.desc()).all()
    return [
        {
            "export_id": r.export_id,
            "clip_id": r.clip_id,
            "title": r.title,
            "width": r.width,
            "height": r.height,
            "duration": r.duration,
            "encoder_used": r.encoder_used,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


@app.get("/api/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = _user_settings_or_default(db, user.id)
    return {
        "whisper_model": st.whisper_model,
        "use_gpu": st.use_gpu,
        "default_preset": st.default_preset,
        "default_intensity": st.default_intensity,
        "default_category": st.default_category,
        "enable_music": st.enable_music,
        "enable_sfx": st.enable_sfx,
        "youtube_api_key_configured": bool(st.youtube_api_key),
        "twitch_client_id": st.twitch_client_id,
        "twitch_oauth_configured": bool(st.twitch_oauth_token),
    }


@app.put("/api/settings")
def update_settings(req: SettingsReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = _user_settings_or_default(db, user.id)
    st.whisper_model = req.whisper_model
    st.use_gpu = req.use_gpu
    st.default_preset = req.default_preset
    st.default_intensity = req.default_intensity
    st.default_category = req.default_category
    st.enable_music = req.enable_music
    st.enable_sfx = req.enable_sfx
    if req.youtube_api_key:
        st.youtube_api_key = req.youtube_api_key
    if req.twitch_client_id:
        st.twitch_client_id = req.twitch_client_id
    if req.twitch_oauth_token:
        st.twitch_oauth_token = req.twitch_oauth_token
    db.commit()
    return {"status": "saved"}
