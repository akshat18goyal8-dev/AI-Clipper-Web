"""Professional editing presets and intensity profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .models import CaptionStyle, EditingIntensity, EditingPreset


@dataclass(frozen=True)
class IntensityProfile:
    zoom_frequency: float  # Zooms per 15s
    max_zoom_scale: float
    shake_strength: float
    sfx_density: float
    overlay_count_max: int
    silence_trim_threshold: float  # Seconds of silence before compression
    hook_enabled: bool
    speed_ramp_enabled: bool


INTENSITY_PROFILES: Dict[EditingIntensity, IntensityProfile] = {
    EditingIntensity.MINIMAL: IntensityProfile(
        zoom_frequency=0.4,
        max_zoom_scale=1.06,
        shake_strength=0.0,
        sfx_density=0.2,
        overlay_count_max=0,
        silence_trim_threshold=1.6,
        hook_enabled=False,
        speed_ramp_enabled=False,
    ),
    EditingIntensity.MODERATE: IntensityProfile(
        zoom_frequency=1.2,
        max_zoom_scale=1.10,
        shake_strength=0.0,
        sfx_density=0.5,
        overlay_count_max=1,
        silence_trim_threshold=1.2,
        hook_enabled=True,
        speed_ramp_enabled=False,
    ),
    EditingIntensity.HIGH_ENERGY: IntensityProfile(
        zoom_frequency=2.4,
        max_zoom_scale=1.16,
        shake_strength=4.5,
        sfx_density=0.85,
        overlay_count_max=3,
        silence_trim_threshold=0.85,
        hook_enabled=True,
        speed_ramp_enabled=True,
    ),
    EditingIntensity.VIRAL_STYLE: IntensityProfile(
        zoom_frequency=3.5,
        max_zoom_scale=1.22,
        shake_strength=7.5,
        sfx_density=1.0,
        overlay_count_max=4,
        silence_trim_threshold=0.65,
        hook_enabled=True,
        speed_ramp_enabled=True,
    ),
}


@dataclass(frozen=True)
class PresetProfile:
    name: EditingPreset
    caption_style: CaptionStyle
    default_reframe_mode: str
    default_music_track: str
    default_music_volume: float
    accent_color: str
    overlay_vocabulary: tuple[str, ...]
    prefer_punch_zoom: bool


PRESET_PROFILES: Dict[EditingPreset, PresetProfile] = {
    EditingPreset.GAMING_VIRAL: PresetProfile(
        name=EditingPreset.GAMING_VIRAL,
        caption_style=CaptionStyle(
            font_name="Impact",
            font_size=80,
            primary_color="#FFFFFF",
            highlight_color="#00FF9D",
            outline_color="#050814",
            outline_width=7,
            shadow_depth=5,
            uppercase=True,
            animation="bounce",
            max_words_per_cue=3,
        ),
        default_reframe_mode="split_gaming",
        default_music_track="cyber_drive",
        default_music_volume=0.14,
        accent_color="#00FF9D",
        overlay_vocabulary=("CLUTCH!", "INSANE!", "NO WAY!", "GG!", "W PLAY!"),
        prefer_punch_zoom=True,
    ),
    EditingPreset.HIGH_ENERGY: PresetProfile(
        name=EditingPreset.HIGH_ENERGY,
        caption_style=CaptionStyle(
            font_name="Arial Black",
            font_size=76,
            primary_color="#FFFFFF",
            highlight_color="#FFE600",
            outline_color="#000000",
            outline_width=6,
            shadow_depth=4,
            uppercase=True,
            animation="pop",
            max_words_per_cue=3,
        ),
        default_reframe_mode="smart_track",
        default_music_track="energetic_pulse",
        default_music_volume=0.16,
        accent_color="#FFE600",
        overlay_vocabulary=("WAIT FOR IT!", "CRAZY!", "UNREAL!", "OMG!", "WATCH THIS!"),
        prefer_punch_zoom=True,
    ),
    EditingPreset.PODCAST_PRO: PresetProfile(
        name=EditingPreset.PODCAST_PRO,
        caption_style=CaptionStyle(
            font_name="Segoe UI Bold",
            font_size=68,
            primary_color="#F8FAFC",
            highlight_color="#38BDF8",
            outline_color="#0F172A",
            outline_width=5,
            shadow_depth=3,
            uppercase=False,
            animation="slide",
            max_words_per_cue=4,
        ),
        default_reframe_mode="smart_track",
        default_music_track="lofi_focus",
        default_music_volume=0.10,
        accent_color="#38BDF8",
        overlay_vocabulary=("KEY TAKEAWAY", "REAL TALK", "LISTEN CLOSELY", "FACT!"),
        prefer_punch_zoom=False,
    ),
    EditingPreset.CINEMATIC_DOC: PresetProfile(
        name=EditingPreset.CINEMATIC_DOC,
        caption_style=CaptionStyle(
            font_name="Georgia",
            font_size=64,
            primary_color="#F1F5F9",
            highlight_color="#F59E0B",
            outline_color="#020617",
            outline_width=4,
            shadow_depth=4,
            uppercase=False,
            animation="fade",
            max_words_per_cue=4,
        ),
        default_reframe_mode="blur_fill",
        default_music_track="cinematic_ambient",
        default_music_volume=0.18,
        accent_color="#F59E0B",
        overlay_vocabulary=("THE TURNING POINT", "CRITICAL MOMENT", "WHAT HAPPENED NEXT"),
        prefer_punch_zoom=False,
    ),
    EditingPreset.MINIMAL_CLEAN: PresetProfile(
        name=EditingPreset.MINIMAL_CLEAN,
        caption_style=CaptionStyle(
            font_name="Segoe UI Semibold",
            font_size=62,
            primary_color="#FFFFFF",
            highlight_color="#A78BFA",
            outline_color="#111827",
            outline_width=4,
            shadow_depth=2,
            uppercase=False,
            animation="fade",
            max_words_per_cue=4,
        ),
        default_reframe_mode="smart_track",
        default_music_track="lofi_focus",
        default_music_volume=0.08,
        accent_color="#A78BFA",
        overlay_vocabulary=("HIGHLIGHT", "NOTE THIS"),
        prefer_punch_zoom=False,
    ),
    EditingPreset.MEME_COMEDY: PresetProfile(
        name=EditingPreset.MEME_COMEDY,
        caption_style=CaptionStyle(
            font_name="Impact",
            font_size=82,
            primary_color="#FFFFFF",
            highlight_color="#FF4D6D",
            outline_color="#000000",
            outline_width=7,
            shadow_depth=5,
            uppercase=True,
            animation="bounce",
            max_words_per_cue=2,
        ),
        default_reframe_mode="smart_track",
        default_music_track="upbeat_groove",
        default_music_volume=0.15,
        accent_color="#FF4D6D",
        overlay_vocabulary=("BRO WHAT?!", "WAIT A SEC!", "LMAO!", "PLOT TWIST!", "NO CHILL!"),
        prefer_punch_zoom=True,
    ),
    EditingPreset.EDUCATIONAL_CREATOR: PresetProfile(
        name=EditingPreset.EDUCATIONAL_CREATOR,
        caption_style=CaptionStyle(
            font_name="Segoe UI Bold",
            font_size=68,
            primary_color="#FFFFFF",
            highlight_color="#22C55E",
            outline_color="#052E16",
            outline_width=5,
            shadow_depth=3,
            uppercase=False,
            animation="pop",
            max_words_per_cue=4,
        ),
        default_reframe_mode="blur_fill",
        default_music_track="lofi_focus",
        default_music_volume=0.09,
        accent_color="#22C55E",
        overlay_vocabulary=("PRO TIP", "REMEMBER THIS", "KEY CONCEPT", "STEP BY STEP"),
        prefer_punch_zoom=False,
    ),
}
