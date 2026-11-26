"""Context-aware opening hooks, smart zoom keyframes, SFX events, and graphic overlays."""

from __future__ import annotations

import numpy as np

from .audio_analyzer import AudioAnalysisResult
from .models import (
    ClipCandidate,
    ContentCategory,
    EditTimeline,
    GraphicOverlay,
    SfxEvent,
    ZoomKeyframe,
)
from .presets import INTENSITY_PROFILES, PRESET_PROFILES
from .visual_analyzer import VisualAnalysisResult


def generate_opening_hook(clip: ClipCandidate) -> str:
    """Create a truthful, curiosity-driven 1-3s hook grounded in the actual clip content."""
    text = clip.transcript_text.strip()
    lower = text.lower()
    cat = clip.category

    if text:
        words = text.split()
        # Look for a genuine punchy question or exclamation in the clip
        for sentence in text.replace("?", "?|").replace("!", "!|").split("|"):
            s = sentence.strip()
            if 3 <= len(s.split()) <= 8 and ("?" in s or "!" in s):
                return s.upper()

        if any(k in lower for k in ("clutch", "one hp", "headshot", "ace", "win")):
            return "WATCH HOW THIS PLAY ENDS!"
        if any(k in lower for k in ("secret", "mistake", "truth", "never")):
            return "DON'T MISS THIS POINT!"
        if len(words) >= 4:
            snippet = " ".join(words[:5]).rstrip(".,!?")
            return f'"{snippet.upper()}..."'

    if cat == ContentCategory.GAMING:
        return "THE CRAZIEST MOMENT!"
    if cat == ContentCategory.PODCASTS or cat == ContentCategory.INTERVIEWS:
        return "WAIT FOR HIS REACTION!"
    if cat == ContentCategory.EDUCATION:
        return "THIS EXPLAINS EVERYTHING!"
    if cat == ContentCategory.REACTIONS:
        return "HE DID NOT EXPECT THIS!"
    return "WAIT FOR THE END!"


def plan_ai_editing_decisions(
    clip: ClipCandidate,
    audio: AudioAnalysisResult,
    visual: VisualAnalysisResult,
) -> EditTimeline:
    """Populate smart zooms, opening hook, graphic overlays, and sound design cues."""
    tl = clip.timeline.model_copy(deep=True)
    preset_prof = PRESET_PROFILES[tl.preset]
    int_prof = INTENSITY_PROFILES[tl.intensity]
    clip_dur = max(1.0, tl.trim_end - tl.trim_start)

    # 1. Opening Hook
    if int_prof.hook_enabled:
        tl.hook_text = generate_opening_hook(clip)
    else:
        tl.hook_text = ""

    # 2. Smart Zoom Keyframes aligned to actual audio/visual peaks (never random)
    tl.zoom_keyframes = []
    if int_prof.hook_enabled:
        tl.zoom_keyframes.append(
            ZoomKeyframe(
                time=0.15,
                duration=1.1,
                target_scale=min(1.12, int_prof.max_zoom_scale),
                easing="punch" if preset_prof.prefer_punch_zoom else "smooth",
                shake_intensity=0.0,
            )
        )

    a_mask = (audio.timeline_times >= tl.trim_start) & (audio.timeline_times <= tl.trim_end)
    v_mask = (visual.timeline_times >= tl.trim_start) & (visual.timeline_times <= tl.trim_end)
    times = audio.timeline_times[a_mask]
    a_vals = audio.excitement_curve[a_mask]
    v_vals = (
        np.interp(times, visual.timeline_times[v_mask], visual.action_curve[v_mask])
        if np.any(v_mask) and len(times) > 0
        else np.zeros_like(a_vals)
    )
    energy = 0.6 * a_vals + 0.4 * v_vals

    desired_zooms = max(0, int(round((clip_dur / 15.0) * int_prof.zoom_frequency)))
    zoom_times: list[float] = [0.15] if tl.zoom_keyframes else []
    if len(energy) > 2 and desired_zooms > 0:
        ranked = np.argsort(-energy)
        for idx in ranked:
            if len(tl.zoom_keyframes) >= desired_zooms + 1:
                break
            rel_t = float(times[idx] - tl.trim_start)
            if rel_t < 2.2 or rel_t > clip_dur - 1.2:
                continue
            if any(abs(rel_t - zt) < 2.8 for zt in zoom_times):
                continue
            peak_strength = float(energy[idx])
            scale = 1.0 + (int_prof.max_zoom_scale - 1.0) * min(1.0, peak_strength / 85.0)
            tl.zoom_keyframes.append(
                ZoomKeyframe(
                    time=round(rel_t, 2),
                    duration=0.95 if preset_prof.prefer_punch_zoom else 1.4,
                    target_scale=round(scale, 3),
                    easing="punch" if preset_prof.prefer_punch_zoom else "ease_out",
                    shake_intensity=int_prof.shake_strength if peak_strength >= 70.0 else 0.0,
                )
            )
            zoom_times.append(rel_t)

    # 3. Context-aware graphic overlays at high-energy moments
    tl.overlays = []
    if tl.hook_text:
        tl.overlays.append(
            GraphicOverlay(
                time=0.0,
                duration=2.4,
                text=tl.hook_text,
                style="hook_banner",
                accent_color=preset_prof.accent_color,
                position_y=0.14,
            )
        )

    vocab = preset_prof.overlay_vocabulary
    overlay_idx = 0
    for z in tl.zoom_keyframes[1:]:
        if overlay_idx >= int_prof.overlay_count_max:
            break
        label = vocab[overlay_idx % len(vocab)]
        tl.overlays.append(
            GraphicOverlay(
                time=z.time,
                duration=1.35,
                text=label,
                style="badge",
                accent_color=preset_prof.accent_color,
                position_y=0.22,
            )
        )
        overlay_idx += 1

    # 4. Sound Design SFX aligned to hook + punch zooms
    tl.sfx_events = []
    if tl.enable_sfx and int_prof.sfx_density > 0:
        if tl.hook_text:
            tl.sfx_events.append(SfxEvent(time=0.05, sfx_type="whoosh", volume=0.65))
        for i, z in enumerate(tl.zoom_keyframes[1:]):
            if i / max(1, len(tl.zoom_keyframes) - 1) <= int_prof.sfx_density:
                sfx = "impact" if z.shake_intensity > 0 else ("pop" if i % 2 == 1 else "whoosh")
                tl.sfx_events.append(SfxEvent(time=max(0.0, z.time - 0.05), sfx_type=sfx, volume=0.72))

    return tl
