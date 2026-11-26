"""End-to-end AI Clipper processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .audio_analyzer import AudioAnalysisResult, analyze_audio
from .captions import build_caption_cues
from .editor_engine import render_clip
from .highlight_selector import select_highlights
from .hooks import plan_ai_editing_decisions
from .inputs import resolve_video_input
from .models import ClipCandidate, ClipRenderResult, MediaSourceInfo, ProjectConfig
from .visual_analyzer import VisualAnalysisResult, analyze_visual


@dataclass
class PipelineOutput:
    source_info: MediaSourceInfo
    audio_analysis: AudioAnalysisResult
    visual_analysis: VisualAnalysisResult
    candidates: List[ClipCandidate]
    rendered_clips: List[ClipRenderResult]


class ClipperPipeline:
    """Coordinates ingest -> multimodal analysis -> highlight selection -> AI edit plan -> rendering."""

    def __init__(self, assets_dir: str | Path):
        self.assets_dir = Path(assets_dir)

    def analyze_and_plan(
        self,
        config: ProjectConfig,
        work_dir: str | Path,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> tuple[MediaSourceInfo, AudioAnalysisResult, VisualAnalysisResult, List[ClipCandidate]]:
        work_path = Path(work_dir)
        work_path.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(0.05, "Resolving and validating media input...")
        source_info = resolve_video_input(
            config.source,
            download_dir=work_path / "downloads",
            youtube_api_key=config.youtube_api_key,
            twitch_oauth_token=config.twitch_oauth_token,
        )

        if progress_cb:
            progress_cb(0.20, "Running audio intelligence & Whisper word-level transcription...")
        audio_res = analyze_audio(
            source_info.resolved_path,
            category=config.category,
            language=config.language,
            whisper_model=config.whisper_model,
            use_gpu=config.use_gpu,
        )

        if progress_cb:
            progress_cb(0.45, "Running visual motion, scene change, and face-tracking analysis...")
        visual_res = analyze_visual(source_info.resolved_path)

        if progress_cb:
            progress_cb(0.60, "Scoring multi-signal highlights & selecting optimal clips...")
        candidates = select_highlights(
            audio=audio_res,
            visual=visual_res,
            chat_curve=None,
            category=config.category,
            preset=config.preset,
            intensity=config.intensity,
            preferred_duration=config.preferred_duration,
            max_clips=config.max_clips,
            enable_music=config.enable_music,
            enable_sfx=config.enable_sfx,
        )

        for cand in candidates:
            cand.timeline = plan_ai_editing_decisions(cand, audio_res, visual_res)
            cand.timeline.captions = build_caption_cues(
                audio_res.segments,
                cand.timeline.trim_start,
                cand.timeline.trim_end,
                cand.timeline.caption_style,
            )

        return source_info, audio_res, visual_res, candidates

    def run_full_project(
        self,
        config: ProjectConfig,
        work_dir: str | Path,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> PipelineOutput:
        source_info, audio_res, visual_res, candidates = self.analyze_and_plan(
            config=config,
            work_dir=work_dir,
            progress_cb=progress_cb,
        )

        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered: List[ClipRenderResult] = []

        total = max(1, len(candidates))
        for idx, cand in enumerate(candidates):
            base_pct = 0.65 + 0.35 * (idx / total)
            if progress_cb:
                progress_cb(base_pct, f"Rendering AI-edited vertical clip {idx + 1}/{total}: {cand.title}")
            out_file = out_dir / f"{cand.clip_id}.mp4"
            res = render_clip(
                source_video=source_info.resolved_path,
                clip=cand,
                output_mp4_path=out_file,
                assets_dir=self.assets_dir,
                use_gpu=config.use_gpu,
            )
            rendered.append(res)

        if progress_cb:
            progress_cb(1.0, f"Completed! Generated {len(rendered)} ready-to-publish vertical clips.")

        return PipelineOutput(
            source_info=source_info,
            audio_analysis=audio_res,
            visual_analysis=visual_res,
            candidates=candidates,
            rendered_clips=rendered,
        )
