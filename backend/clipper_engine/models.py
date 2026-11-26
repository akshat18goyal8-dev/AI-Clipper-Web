"""Core data models and enums for AI Clipper 2.0."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ContentCategory(str, Enum):
    GAMING = "Gaming"
    PODCASTS = "Podcasts"
    EDUCATION = "Education"
    ENTERTAINMENT = "Entertainment"
    INTERVIEWS = "Interviews"
    REACTIONS = "Reactions"
    GENERAL = "General Videos"


class EditingPreset(str, Enum):
    GAMING_VIRAL = "Gaming Viral Style"
    HIGH_ENERGY = "High-Energy Creator Style"
    PODCAST_PRO = "Podcast Professional Style"
    CINEMATIC_DOC = "Cinematic Documentary Style"
    MINIMAL_CLEAN = "Minimal Clean Style"
    MEME_COMEDY = "Meme and Comedy Style"
    EDUCATIONAL_CREATOR = "Educational Creator Style"


class EditingIntensity(str, Enum):
    MINIMAL = "MINIMAL"
    MODERATE = "MODERATE"
    HIGH_ENERGY = "HIGH ENERGY"
    VIRAL_STYLE = "VIRAL STYLE"


class PlatformType(str, Enum):
    LOCAL_FILE = "local_file"
    DIRECT_URL = "direct_url"
    YOUTUBE = "youtube"
    TWITCH = "twitch"
    OTHER_STREAM = "other_stream"


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    probability: float = 1.0
    is_emphasis: bool = False


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    language: str = "en"
    words: List[WordTimestamp] = Field(default_factory=list)


class CaptionCue(BaseModel):
    id: str
    start: float
    end: float
    text: str
    words: List[WordTimestamp] = Field(default_factory=list)
    highlight_indices: List[int] = Field(default_factory=list)
    position_y: int = 1420  # Vertical pixel anchor on 1080x1920


class CaptionStyle(BaseModel):
    font_name: str = "Arial Black"
    font_size: int = 74
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFE600"
    outline_color: str = "#000000"
    outline_width: int = 6
    shadow_depth: int = 4
    uppercase: bool = True
    animation: str = "pop"  # pop, slide, fade, bounce
    max_words_per_cue: int = 3


class HighlightSignalBreakdown(BaseModel):
    opening_hook: float = Field(ge=0, le=100, default=0.0)
    emotional_intensity: float = Field(ge=0, le=100, default=0.0)
    audio_excitement: float = Field(ge=0, le=100, default=0.0)
    visual_engagement: float = Field(ge=0, le=100, default=0.0)
    chat_activity: Optional[float] = Field(ge=0, le=100, default=None)
    content_clarity: float = Field(ge=0, le=100, default=0.0)
    pacing: float = Field(ge=0, le=100, default=0.0)
    total_score: float = Field(ge=0, le=100, default=0.0)
    explanation: str = ""


class ZoomKeyframe(BaseModel):
    time: float  # Relative to clip start (seconds)
    duration: float = 0.8
    target_scale: float = 1.15
    easing: str = "ease_out"  # ease_out, punch, smooth
    shake_intensity: float = 0.0


class GraphicOverlay(BaseModel):
    time: float  # Relative to clip start
    duration: float = 1.6
    text: str
    subtext: str = ""
    style: str = "badge"  # hook_banner, badge, callout, emoji
    accent_color: str = "#FF3B30"
    position_y: float = 0.18  # Normalized Y (0..1)


class SfxEvent(BaseModel):
    time: float  # Relative to clip start
    sfx_type: str  # whoosh, impact, pop, riser
    volume: float = 0.7


class DeadAirCut(BaseModel):
    start: float  # Relative to clip start
    end: float


class EditTimeline(BaseModel):
    trim_start: float
    trim_end: float
    target_width: int = 1080
    target_height: int = 1920
    crop_offset_x: float = 0.0  # -1.0 .. 1.0 manual pan adjustment
    crop_offset_y: float = 0.0  # -1.0 .. 1.0 manual vertical adjustment
    reframe_mode: str = "smart_track"  # smart_track, blur_fill, split_gaming
    preset: EditingPreset = EditingPreset.HIGH_ENERGY
    intensity: EditingIntensity = EditingIntensity.HIGH_ENERGY
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    captions: List[CaptionCue] = Field(default_factory=list)
    hook_text: str = ""
    intro_text: str = ""
    outro_text: str = ""
    zoom_keyframes: List[ZoomKeyframe] = Field(default_factory=list)
    overlays: List[GraphicOverlay] = Field(default_factory=list)
    sfx_events: List[SfxEvent] = Field(default_factory=list)
    dead_air_cuts: List[DeadAirCut] = Field(default_factory=list)
    dialogue_volume: float = 1.0
    music_volume: float = 0.16
    sfx_volume: float = 0.55
    enable_music: bool = True
    enable_sfx: bool = True
    enable_noise_reduction: bool = True
    music_track: str = "energetic_pulse"


class ClipCandidate(BaseModel):
    clip_id: str
    title: str
    start_time: float
    end_time: float
    duration: float
    peak_time: float
    category: ContentCategory
    language: str = "en"
    transcript_text: str = ""
    breakdown: HighlightSignalBreakdown
    timeline: EditTimeline


class ClipRenderResult(BaseModel):
    clip_id: str
    title: str
    output_path: str
    thumbnail_path: str
    duration: float
    width: int = 1080
    height: int = 1920
    encoder_used: str
    score: float
    explanation: str
    timeline: EditTimeline


class HardwareCapabilities(BaseModel):
    cpu_count: int
    torch_cuda_available: bool
    cuda_device_name: Optional[str] = None
    ffmpeg_path: str
    ffprobe_path: str
    preferred_video_encoder: str
    available_hw_encoders: List[str] = Field(default_factory=list)
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"


class MediaSourceInfo(BaseModel):
    source_input: str
    resolved_path: str
    platform: PlatformType
    title: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    is_live: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectConfig(BaseModel):
    source: str
    category: ContentCategory = ContentCategory.GENERAL
    preset: EditingPreset = EditingPreset.HIGH_ENERGY
    intensity: EditingIntensity = EditingIntensity.HIGH_ENERGY
    preferred_duration: Optional[int] = None  # None = Auto (10,15,30,45,60), max 60
    max_clips: int = 5
    language: str = "auto"  # auto, en, hi
    whisper_model: str = "base"
    use_gpu: bool = True
    enable_music: bool = True
    enable_sfx: bool = True
    output_dir: str = "outputs"
    youtube_api_key: Optional[str] = None
    twitch_client_id: Optional[str] = None
    twitch_oauth_token: Optional[str] = None
