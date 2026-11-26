"""AI Clipper 2.0 Shared Intelligent Video Processing Engine."""

from .audio_analyzer import AudioAnalysisResult, analyze_audio
from .captions import build_caption_cues, write_ass_subtitles
from .chat_analyzer import LiveChatAnalyzer, TwitchIRCReader, YouTubeLiveChatPoller
from .editor_engine import render_clip
from .hardware import detect_hardware
from .highlight_selector import select_highlights
from .hooks import generate_opening_hook, plan_ai_editing_decisions
from .inputs import MediaInputError, classify_source, probe_media_file, resolve_live_stream_url, resolve_video_input
from .live_monitor import LiveStreamMonitor, LiveTelemetry
from .models import (
    CaptionCue,
    CaptionStyle,
    ClipCandidate,
    ClipRenderResult,
    ContentCategory,
    EditingIntensity,
    EditingPreset,
    EditTimeline,
    HardwareCapabilities,
    HighlightSignalBreakdown,
    MediaSourceInfo,
    PlatformType,
    ProjectConfig,
)
from .pipeline import ClipperPipeline, PipelineOutput
from .presets import INTENSITY_PROFILES, PRESET_PROFILES
from .reframer import SubjectReframer
from .sound_assets import available_music_tracks, ensure_audio_assets

__all__ = [
    "AudioAnalysisResult",
    "CaptionCue",
    "CaptionStyle",
    "ClipCandidate",
    "ClipRenderResult",
    "ClipperPipeline",
    "ContentCategory",
    "EditTimeline",
    "EditingIntensity",
    "EditingPreset",
    "HardwareCapabilities",
    "HighlightSignalBreakdown",
    "INTENSITY_PROFILES",
    "LiveChatAnalyzer",
    "LiveStreamMonitor",
    "LiveTelemetry",
    "MediaInputError",
    "MediaSourceInfo",
    "PRESET_PROFILES",
    "PipelineOutput",
    "PlatformType",
    "ProjectConfig",
    "SubjectReframer",
    "TwitchIRCReader",
    "YouTubeLiveChatPoller",
    "analyze_audio",
    "available_music_tracks",
    "build_caption_cues",
    "classify_source",
    "detect_hardware",
    "ensure_audio_assets",
    "generate_opening_hook",
    "plan_ai_editing_decisions",
    "probe_media_file",
    "render_clip",
    "resolve_live_stream_url",
    "resolve_video_input",
    "select_highlights",
    "write_ass_subtitles",
]
