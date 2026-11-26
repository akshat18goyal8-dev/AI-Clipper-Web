"""Background job queue (Redis-backed telemetry + ThreadPoolExecutor worker) and Live Monitor manager."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from clipper_engine import (
    ClipCandidate,
    ClipRenderResult,
    ClipperPipeline,
    ContentCategory,
    EditingIntensity,
    EditingPreset,
    EditTimeline,
    HighlightSignalBreakdown,
    LiveStreamMonitor,
    LiveTelemetry,
    ProjectConfig,
    render_clip,
)

from .config import ASSETS_DIR, REDIS_URL, STORAGE_DIR
from .db import Clip, ExportRecord, Project, SessionLocal


class JobBroker:
    """Publishes progress updates to Redis when available, with in-memory fallback."""

    def __init__(self) -> None:
        self._redis = None
        self.redis_connected = False
        try:
            import redis

            client = redis.from_url(REDIS_URL, socket_connect_timeout=1.0)
            client.ping()
            self._redis = client
            self.redis_connected = True
        except Exception:
            self._redis = None
            self.redis_connected = False

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clipper_web_job")
        self._live_monitors: Dict[str, LiveStreamMonitor] = {}
        self._live_telemetry: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def publish_progress(self, project_id: str, progress: float, message: str, status: str = "processing") -> None:
        if self._redis:
            try:
                self._redis.setex(
                    f"job:{project_id}",
                    3600,
                    json.dumps({"progress": progress, "message": message, "status": status}),
                )
            except Exception:
                pass

    def submit_project(self, project_id: str, user_id: str, config: ProjectConfig) -> None:
        self._executor.submit(self._run_project_job, project_id, user_id, config)

    def _run_project_job(self, project_id: str, user_id: str, config: ProjectConfig) -> None:
        db = SessionLocal()
        work_dir = STORAGE_DIR / "work" / project_id
        out_dir = STORAGE_DIR / "renders" / project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        cfg = config.model_copy(update={"output_dir": str(out_dir)})

        try:
            pipeline = ClipperPipeline(assets_dir=ASSETS_DIR)

            def on_prog(pct: float, msg: str) -> None:
                proj = db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    proj.status = "processing"
                    proj.progress = float(pct)
                    proj.status_message = msg
                    db.commit()
                self.publish_progress(project_id, pct, msg, "processing")

            source_info, _, _, candidates = pipeline.analyze_and_plan(cfg, work_dir=work_dir, progress_cb=on_prog)
            proj = db.query(Project).filter(Project.id == project_id).first()
            if proj:
                proj.resolved_path = source_info.resolved_path
                proj.title = source_info.title
                proj.duration = source_info.duration
                db.commit()

            total = max(1, len(candidates))
            for idx, cand in enumerate(candidates):
                on_prog(0.65 + 0.34 * (idx / total), f"Rendering vertical clip {idx + 1}/{total}: {cand.title}")
                out_file = out_dir / f"{cand.clip_id}.mp4"
                res = render_clip(
                    source_video=source_info.resolved_path,
                    clip=cand,
                    output_mp4_path=out_file,
                    assets_dir=ASSETS_DIR,
                    use_gpu=cfg.use_gpu,
                )
                clip_row = Clip(
                    clip_id=cand.clip_id,
                    project_id=project_id,
                    user_id=user_id,
                    title=cand.title,
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                    duration=cand.duration,
                    peak_time=cand.peak_time,
                    category=cand.category.value,
                    language=cand.language,
                    transcript_text=cand.transcript_text,
                    score=cand.breakdown.total_score,
                    explanation=cand.breakdown.explanation,
                    breakdown_json=cand.breakdown.model_dump_json(),
                    timeline_json=cand.timeline.model_dump_json(),
                    video_path=res.output_path,
                    thumbnail_path=res.thumbnail_path,
                    encoder_used=res.encoder_used,
                )
                db.add(clip_row)
                db.add(
                    ExportRecord(
                        export_id=f"exp_{uuid.uuid4().hex[:8]}",
                        user_id=user_id,
                        clip_id=cand.clip_id,
                        title=cand.title,
                        output_path=res.output_path,
                        width=res.width,
                        height=res.height,
                        duration=res.duration,
                        encoder_used=res.encoder_used,
                    )
                )
                db.commit()

            proj = db.query(Project).filter(Project.id == project_id).first()
            if proj:
                proj.status = "completed"
                proj.progress = 1.0
                proj.status_message = f"Completed ({len(candidates)} clips)"
                db.commit()
            self.publish_progress(project_id, 1.0, f"Completed ({len(candidates)} clips)", "completed")
        except Exception as exc:
            proj = db.query(Project).filter(Project.id == project_id).first()
            if proj:
                proj.status = "failed"
                proj.progress = 0.0
                proj.status_message = str(exc)
                db.commit()
            self.publish_progress(project_id, 0.0, str(exc), "failed")
        finally:
            db.close()

    def rerender_clip(self, clip_id: str, use_gpu: bool = True) -> ClipRenderResult:
        db = SessionLocal()
        try:
            row = db.query(Clip).filter(Clip.clip_id == clip_id).first()
            if not row:
                raise ValueError("Clip not found")
            proj = db.query(Project).filter(Project.id == row.project_id).first()
            if not proj or not proj.resolved_path or not Path(proj.resolved_path).exists():
                raise ValueError("Source video file for this clip is no longer present on server")

            timeline = EditTimeline.model_validate_json(row.timeline_json)
            breakdown = HighlightSignalBreakdown.model_validate_json(row.breakdown_json)
            cand = ClipCandidate(
                clip_id=row.clip_id,
                title=row.title,
                start_time=timeline.trim_start,
                end_time=timeline.trim_end,
                duration=round(max(1.0, timeline.trim_end - timeline.trim_start), 2),
                peak_time=row.peak_time,
                category=ContentCategory(row.category),
                language=row.language,
                transcript_text=row.transcript_text,
                breakdown=breakdown,
                timeline=timeline,
            )
            out_dir = STORAGE_DIR / "renders" / row.project_id
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{row.clip_id}_edited.mp4"
            res = render_clip(proj.resolved_path, cand, out_file, ASSETS_DIR, use_gpu=use_gpu)

            row.start_time = timeline.trim_start
            row.end_time = timeline.trim_end
            row.duration = res.duration
            row.video_path = res.output_path
            row.thumbnail_path = res.thumbnail_path
            row.encoder_used = res.encoder_used
            db.add(
                ExportRecord(
                    export_id=f"exp_{uuid.uuid4().hex[:8]}",
                    user_id=row.user_id,
                    clip_id=row.clip_id,
                    title=row.title,
                    output_path=res.output_path,
                    width=res.width,
                    height=res.height,
                    duration=res.duration,
                    encoder_used=res.encoder_used,
                )
            )
            db.commit()
            return res
        finally:
            db.close()

    def start_live(
        self,
        user_id: str,
        stream_url: str,
        category: ContentCategory,
        preset: EditingPreset,
        intensity: EditingIntensity,
        buffer_seconds: int,
        sensitivity: float,
        youtube_api_key: Optional[str],
        twitch_oauth_token: Optional[str],
    ) -> str:
        self.stop_live(user_id)
        project_id = f"live_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(
                Project(
                    id=project_id,
                    user_id=user_id,
                    title=f"Live: {stream_url[:52]}",
                    source_input=stream_url,
                    resolved_path=stream_url,
                    platform="live_stream",
                    category=category.value,
                    preset=preset.value,
                    intensity=intensity.value,
                    status="monitoring",
                    progress=0.5,
                    status_message="Live stream rolling buffer active",
                )
            )
            db.commit()
        finally:
            db.close()

        out_dir = STORAGE_DIR / "live" / user_id / project_id

        def on_tel(tel: LiveTelemetry) -> None:
            with self._lock:
                self._live_telemetry[user_id] = {
                    "active": True,
                    "project_id": project_id,
                    "audio_score": tel.audio_score,
                    "visual_score": tel.visual_score,
                    "chat_score": tel.chat_score,
                    "combined_score": tel.combined_score,
                    "status_text": tel.status_text,
                    "chat_status": tel.chat_status,
                    "buffered_segments": tel.buffered_segments,
                }

        def on_clip(res: ClipRenderResult) -> None:
            sdb = SessionLocal()
            try:
                bd = HighlightSignalBreakdown(total_score=res.score, explanation=res.explanation)
                sdb.add(
                    Clip(
                        clip_id=res.clip_id,
                        project_id=project_id,
                        user_id=user_id,
                        title=res.title,
                        start_time=res.timeline.trim_start,
                        end_time=res.timeline.trim_end,
                        duration=res.duration,
                        category=category.value,
                        score=res.score,
                        explanation=res.explanation,
                        breakdown_json=bd.model_dump_json(),
                        timeline_json=res.timeline.model_dump_json(),
                        video_path=res.output_path,
                        thumbnail_path=res.thumbnail_path,
                        encoder_used=res.encoder_used,
                    )
                )
                sdb.commit()
            finally:
                sdb.close()

        def on_err(msg: str) -> None:
            with self._lock:
                self._live_telemetry[user_id] = {
                    "active": False,
                    "project_id": project_id,
                    "audio_score": 0,
                    "visual_score": 0,
                    "chat_score": None,
                    "combined_score": 0,
                    "status_text": f"Error: {msg}",
                    "chat_status": "Disconnected",
                    "buffered_segments": 0,
                }

        mon = LiveStreamMonitor(
            stream_url=stream_url,
            output_dir=out_dir,
            assets_dir=ASSETS_DIR,
            category=category,
            preset=preset,
            intensity=intensity,
            buffer_seconds=buffer_seconds,
            sensitivity_threshold=sensitivity,
            youtube_api_key=youtube_api_key,
            twitch_oauth_token=twitch_oauth_token,
            on_telemetry=on_tel,
            on_clip_generated=on_clip,
            on_error=on_err,
        )
        with self._lock:
            self._live_monitors[user_id] = mon
            self._live_telemetry[user_id] = {
                "active": True,
                "project_id": project_id,
                "audio_score": 0,
                "visual_score": 0,
                "chat_score": None,
                "combined_score": 0,
                "status_text": "Connecting to live stream...",
                "chat_status": "Initializing...",
                "buffered_segments": 0,
            }
        mon.start()
        return project_id

    def stop_live(self, user_id: str) -> None:
        with self._lock:
            mon = self._live_monitors.pop(user_id, None)
            if user_id in self._live_telemetry:
                self._live_telemetry[user_id]["active"] = False
                self._live_telemetry[user_id]["status_text"] = "Stopped"
        if mon:
            mon.stop()

    def get_live_status(self, user_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._live_telemetry.get(
                user_id,
                {
                    "active": False,
                    "project_id": None,
                    "audio_score": 0,
                    "visual_score": 0,
                    "chat_score": None,
                    "combined_score": 0,
                    "status_text": "Idle",
                    "chat_status": "Not connected",
                    "buffered_segments": 0,
                },
            )


broker = JobBroker()
