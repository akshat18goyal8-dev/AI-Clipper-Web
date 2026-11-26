"""Real-time Live Stream Monitor with rolling buffer and multi-signal highlight clipping."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .audio_analyzer import analyze_audio
from .captions import build_caption_cues
from .chat_analyzer import LiveChatAnalyzer, TwitchIRCReader, YouTubeLiveChatPoller
from .editor_engine import render_clip
from .hardware import detect_hardware
from .highlight_selector import select_highlights
from .hooks import plan_ai_editing_decisions
from .inputs import resolve_live_stream_url
from .models import (
    ClipRenderResult,
    ContentCategory,
    EditingIntensity,
    EditingPreset,
    PlatformType,
)
from .visual_analyzer import analyze_visual


@dataclass
class LiveTelemetry:
    audio_score: float
    visual_score: float
    chat_score: Optional[float]
    combined_score: float
    status_text: str
    chat_status: str
    buffered_segments: int


class LiveStreamMonitor:
    """Monitors an active live stream using a rolling segment buffer + real-time audio/visual/chat scoring."""

    def __init__(
        self,
        stream_url: str,
        output_dir: str | Path,
        assets_dir: str | Path,
        category: ContentCategory = ContentCategory.GAMING,
        preset: EditingPreset = EditingPreset.GAMING_VIRAL,
        intensity: EditingIntensity = EditingIntensity.HIGH_ENERGY,
        buffer_seconds: int = 120,
        sensitivity_threshold: float = 65.0,
        cooldown_seconds: int = 35,
        youtube_api_key: Optional[str] = None,
        twitch_oauth_token: Optional[str] = None,
        on_telemetry: Optional[Callable[[LiveTelemetry], None]] = None,
        on_clip_generated: Optional[Callable[[ClipRenderResult], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.stream_url = stream_url
        self.output_dir = Path(output_dir)
        self.assets_dir = Path(assets_dir)
        self.category = category
        self.preset = preset
        self.intensity = intensity
        self.buffer_seconds = max(40, min(300, buffer_seconds))
        self.sensitivity_threshold = float(sensitivity_threshold)
        self.cooldown_seconds = max(15, cooldown_seconds)
        self.youtube_api_key = youtube_api_key
        self.twitch_oauth_token = twitch_oauth_token
        self.on_telemetry = on_telemetry
        self.on_clip_generated = on_clip_generated
        self.on_error = on_error

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._chat_analyzer = LiveChatAnalyzer()
        self._chat_reader = None
        self._last_trigger_ts = 0.0
        self.generated_clips: List[ClipRenderResult] = []

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._ffmpeg_proc and self._ffmpeg_proc.poll() is None:
            try:
                self._ffmpeg_proc.terminate()
            except Exception:
                pass
        if self._chat_reader:
            self._chat_reader.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _run_loop(self) -> None:
        hw = detect_hardware()
        buffer_dir = self.output_dir / "_live_buffer"
        buffer_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = self.output_dir / "live_clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        try:
            resolved = resolve_live_stream_url(self.stream_url)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))
            return

        platform: PlatformType = resolved["platform"]
        if platform == PlatformType.TWITCH and resolved.get("channel"):
            self._chat_reader = TwitchIRCReader(
                channel=resolved["channel"],
                analyzer=self._chat_analyzer,
                oauth_token=self.twitch_oauth_token,
            )
            self._chat_reader.start()
        elif platform == PlatformType.YOUTUBE and resolved.get("video_id"):
            self._chat_reader = YouTubeLiveChatPoller(
                video_id=resolved["video_id"],
                api_key=self.youtube_api_key,
                analyzer=self._chat_analyzer,
            )
            self._chat_reader.start()

        seg_seconds = 10
        wrap_count = max(6, self.buffer_seconds // seg_seconds)
        seg_pattern = str(buffer_dir / "seg_%03d.ts")

        cmd = [
            hw.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            resolved["stream_url"],
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(seg_seconds),
            "-segment_wrap",
            str(wrap_count),
            "-reset_timestamps",
            "1",
            seg_pattern,
        ]
        self._ffmpeg_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        seen_mtime: dict[str, float] = {}
        while not self._stop_event.is_set():
            if self._ffmpeg_proc.poll() is not None:
                err = self._ffmpeg_proc.stderr.read().decode("utf-8", errors="ignore") if self._ffmpeg_proc.stderr else ""
                if not self._stop_event.is_set() and self.on_error:
                    self.on_error(f"Stream capture ended: {err or 'stream disconnected'}")
                break

            seg_files = sorted(buffer_dir.glob("seg_*.ts"), key=lambda p: p.stat().st_mtime)
            chat_note = self._chat_reader.status_note if self._chat_reader else "Chat unavailable (audio+visual active)"

            # Inspect newest completed segment (second-to-last written file)
            if len(seg_files) >= 2:
                latest_done = seg_files[-2]
                mtime = latest_done.stat().st_mtime
                if seen_mtime.get(latest_done.name) != mtime:
                    seen_mtime[latest_done.name] = mtime
                    try:
                        audio_res = analyze_audio(str(latest_done), category=self.category, whisper_model="tiny")
                        vis_res = analyze_visual(str(latest_done), sample_fps=2.0)
                        a_score = float(audio_res.excitement_curve.max()) if len(audio_res.excitement_curve) else 0.0
                        v_score = float(vis_res.action_curve.max()) if len(vis_res.action_curve) else 0.0
                        c_score = self._chat_analyzer.get_score_at()
                        if c_score is not None:
                            combined = 0.45 * a_score + 0.32 * v_score + 0.23 * c_score
                        else:
                            combined = 0.60 * a_score + 0.40 * v_score

                        if self.on_telemetry:
                            self.on_telemetry(
                                LiveTelemetry(
                                    audio_score=round(a_score, 1),
                                    visual_score=round(v_score, 1),
                                    chat_score=round(c_score, 1) if c_score is not None else None,
                                    combined_score=round(combined, 1),
                                    status_text=f"Monitoring '{resolved['title']}'...",
                                    chat_status=chat_note,
                                    buffered_segments=len(seg_files),
                                )
                            )

                        now = time.time()
                        if combined >= self.sensitivity_threshold and (now - self._last_trigger_ts) >= self.cooldown_seconds:
                            self._last_trigger_ts = now
                            self._capture_and_render_buffer(seg_files[-4:], clips_dir, hw.ffmpeg_path)
                    except Exception:
                        pass

            self._stop_event.wait(2.5)

    def _capture_and_render_buffer(self, recent_segs: List[Path], clips_dir: Path, ffmpeg_path: str) -> None:
        if not recent_segs:
            return
        concat_list = clips_dir / f"concat_{int(time.time())}.txt"
        merged_mp4 = clips_dir / f"raw_{int(time.time())}.mp4"
        concat_list.write_text(
            "\n".join(f"file '{str(p.resolve()).replace(chr(39), chr(39)*2)}'" for p in recent_segs),
            encoding="utf-8",
        )
        res = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(merged_mp4),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        concat_list.unlink(missing_ok=True)
        if res.returncode != 0 or not merged_mp4.exists():
            return

        audio_res = analyze_audio(str(merged_mp4), category=self.category, whisper_model="base")
        vis_res = analyze_visual(str(merged_mp4))
        cands = select_highlights(
            audio=audio_res,
            visual=vis_res,
            chat_curve=None,
            category=self.category,
            preset=self.preset,
            intensity=self.intensity,
            max_clips=1,
        )
        if not cands:
            return
        best = cands[0]
        best.timeline = plan_ai_editing_decisions(best, audio_res, vis_res)
        best.timeline.captions = build_caption_cues(
            audio_res.segments, best.timeline.trim_start, best.timeline.trim_end, best.timeline.caption_style
        )
        out_path = clips_dir / f"live_highlight_{int(time.time())}.mp4"
        rendered = render_clip(str(merged_mp4), best, out_path, self.assets_dir)
        merged_mp4.unlink(missing_ok=True)
        self.generated_clips.append(rendered)
        if self.on_clip_generated:
            self.on_clip_generated(rendered)
