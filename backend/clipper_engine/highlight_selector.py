"""Multi-signal highlight fusion, boundary snapping, deduplication, and engagement scoring."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np

from .audio_analyzer import AudioAnalysisResult
from .models import (
    ClipCandidate,
    ContentCategory,
    DeadAirCut,
    EditingIntensity,
    EditingPreset,
    EditTimeline,
    HighlightSignalBreakdown,
    TranscriptSegment,
    WordTimestamp,
)
from .presets import INTENSITY_PROFILES, PRESET_PROFILES
from .visual_analyzer import VisualAnalysisResult

SUPPORTED_DURATIONS = (10, 15, 30, 45, 60)

# Category weights (audio, visual, chat_when_present)
CATEGORY_WEIGHTS: Dict[ContentCategory, Tuple[float, float, float]] = {
    ContentCategory.GAMING: (0.42, 0.38, 0.20),
    ContentCategory.PODCASTS: (0.62, 0.18, 0.20),
    ContentCategory.EDUCATION: (0.65, 0.25, 0.10),
    ContentCategory.ENTERTAINMENT: (0.48, 0.32, 0.20),
    ContentCategory.INTERVIEWS: (0.60, 0.25, 0.15),
    ContentCategory.REACTIONS: (0.50, 0.30, 0.20),
    ContentCategory.GENERAL: (0.50, 0.30, 0.20),
}


def fuse_multimodal_scores(
    audio_curve: np.ndarray,
    visual_curve: np.ndarray,
    chat_curve: Optional[np.ndarray],
    category: ContentCategory,
) -> np.ndarray:
    n = max(len(audio_curve), len(visual_curve))
    a = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(audio_curve)), audio_curve)
    v = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(visual_curve)), visual_curve)
    w_a, w_v, w_c = CATEGORY_WEIGHTS.get(category, (0.5, 0.3, 0.2))

    if chat_curve is not None and len(chat_curve) > 0 and float(np.max(chat_curve)) > 0:
        c = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(chat_curve)), chat_curve)
        combined = w_a * a + w_v * v + w_c * c
    else:
        # Re-normalize audio + visual weights cleanly when live chat is unavailable
        total = w_a + w_v
        combined = (w_a / total) * a + (w_v / total) * v
    return np.clip(combined, 0.0, 100.0).astype(np.float32)


def _choose_optimal_duration(
    peak_t: float,
    total_duration: float,
    combined_curve: np.ndarray,
    bin_sec: float,
    preferred_duration: Optional[int],
) -> int:
    if preferred_duration is not None:
        clamped = min(60, max(10, int(preferred_duration)))
        return min(SUPPORTED_DURATIONS, key=lambda d: abs(d - clamped))

    # Auto-pick best duration based on how wide the excitement plateau around peak_t is
    peak_idx = int(peak_t / bin_sec)
    thresh = max(35.0, float(combined_curve[min(peak_idx, len(combined_curve) - 1)]) * 0.55)
    left = peak_idx
    while left > 0 and combined_curve[left - 1] >= thresh and (peak_idx - left) * bin_sec < 28:
        left -= 1
    right = peak_idx
    while right < len(combined_curve) - 1 and combined_curve[right + 1] >= thresh and (right - peak_idx) * bin_sec < 28:
        right += 1

    span = (right - left) * bin_sec + 8.0  # Context pre/post buffer
    usable = min(60.0, total_duration)
    for d in SUPPORTED_DURATIONS:
        if d >= span and d <= usable + 2.0:
            return d
    # Fallback to largest supported duration that fits inside video
    fitting = [d for d in SUPPORTED_DURATIONS if d <= max(10.0, total_duration)]
    return fitting[-1] if fitting else 10


def _snap_to_sentence_boundaries(
    start_t: float,
    end_t: float,
    peak_t: float,
    target_dur: float,
    total_duration: float,
    segments: List[TranscriptSegment],
) -> Tuple[float, float]:
    """Adjust clip bounds so sentences aren't sliced mid-word while staying <= 60s."""
    if total_duration <= target_dur:
        return 0.0, min(60.0, total_duration)

    if not segments:
        s = max(0.0, min(peak_t - target_dur * 0.42, total_duration - target_dur))
        return round(s, 2), round(min(total_duration, s + target_dur), 2)

    # Find segments overlapping desired window
    desired_start = max(0.0, peak_t - target_dur * 0.40)
    desired_end = min(total_duration, desired_start + target_dur)

    # Snap start to nearest segment start within +/- 3.5s
    best_start = desired_start
    best_dist = 3.5
    for seg in segments:
        d = abs(seg.start - desired_start)
        if d < best_dist and seg.start <= peak_t - 2.0:
            best_dist = d
            best_start = max(0.0, seg.start - 0.25)

    # Snap end to nearest segment end within +/- 4.0s while keeping <= 60s
    best_end = min(total_duration, best_start + target_dur)
    best_end_dist = 4.0
    for seg in segments:
        d = abs(seg.end - (best_start + target_dur))
        if d < best_end_dist and seg.end > peak_t + 2.0 and (seg.end - best_start) <= 60.0:
            best_end_dist = d
            best_end = min(total_duration, seg.end + 0.35)

    if best_end - best_start < 8.0:
        best_end = min(total_duration, best_start + min(target_dur, 60.0))
    if best_end - best_start > 60.0:
        best_end = best_start + 60.0

    return round(best_start, 2), round(best_end, 2)


def _compute_engagement_breakdown(
    start_t: float,
    end_t: float,
    peak_t: float,
    audio: AudioAnalysisResult,
    visual: VisualAnalysisResult,
    chat_curve: Optional[np.ndarray],
    segments: List[TranscriptSegment],
    category: ContentCategory,
) -> HighlightSignalBreakdown:
    bin_sec = 0.5
    a_mask = (audio.timeline_times >= start_t) & (audio.timeline_times <= end_t)
    v_mask = (visual.timeline_times >= start_t) & (visual.timeline_times <= end_t)

    audio_slice = audio.excitement_curve[a_mask] if np.any(a_mask) else np.array([30.0])
    visual_slice = visual.action_curve[v_mask] if np.any(v_mask) else np.array([30.0])

    audio_score = float(np.percentile(audio_slice, 90) * 0.6 + np.mean(audio_slice) * 0.4)
    visual_score = float(np.percentile(visual_slice, 90) * 0.6 + np.mean(visual_slice) * 0.4)

    # Opening hook = energy in first 3 seconds of the clip
    hook_mask = (audio.timeline_times >= start_t) & (audio.timeline_times <= start_t + 3.0)
    vhook_mask = (visual.timeline_times >= start_t) & (visual.timeline_times <= start_t + 3.0)
    h_a = float(np.max(audio.excitement_curve[hook_mask])) if np.any(hook_mask) else audio_score * 0.7
    h_v = float(np.max(visual.action_curve[vhook_mask])) if np.any(vhook_mask) else visual_score * 0.7
    opening_hook = float(np.clip(0.55 * h_a + 0.45 * h_v, 15.0, 99.0))

    # Transcript clarity & emotional cues
    clip_segs = [s for s in segments if s.end >= start_t and s.start <= end_t]
    words = [w for s in clip_segs for w in s.words]
    dur = max(1.0, end_t - start_t)
    words_per_sec = len(words) / dur
    clarity = float(np.clip(45.0 + min(45.0, words_per_sec * 16.0), 25.0, 96.0)) if words else 42.0
    emph_count = sum(1 for w in words if w.is_emphasis)
    emotional = float(np.clip(audio_score * 0.65 + min(35.0, emph_count * 7.0), 15.0, 99.0))

    # Pacing: penalize excessive silence ratio
    sil_sec = sum(max(0.0, min(end_t, s1) - max(start_t, s0)) for s0, s1 in audio.silence_intervals)
    active_ratio = max(0.0, 1.0 - sil_sec / dur)
    pacing = float(np.clip(35.0 + active_ratio * 60.0, 20.0, 98.0))

    chat_score: Optional[float] = None
    if chat_curve is not None and len(chat_curve) > 0 and float(np.max(chat_curve)) > 0:
        c_slice = chat_curve[a_mask] if len(chat_curve) == len(audio.timeline_times) and np.any(a_mask) else chat_curve
        chat_score = float(np.clip(np.percentile(c_slice, 90), 0.0, 100.0))

    w_a, w_v, w_c = CATEGORY_WEIGHTS.get(category, (0.5, 0.3, 0.2))
    if chat_score is not None:
        base = w_a * audio_score + w_v * visual_score + w_c * chat_score
    else:
        base = (w_a / (w_a + w_v)) * audio_score + (w_v / (w_a + w_v)) * visual_score

    total = float(
        np.clip(
            0.46 * base + 0.16 * opening_hook + 0.16 * emotional + 0.12 * clarity + 0.10 * pacing,
            10.0,
            99.0,
        )
    )

    reasons: List[str] = []
    if audio_score >= 65:
        reasons.append(f"strong vocal energy spike ({audio_score:.0f}/100)")
    if visual_score >= 60:
        reasons.append(f"high visual motion/action ({visual_score:.0f}/100)")
    if chat_score is not None and chat_score >= 60:
        reasons.append(f"live chat surge ({chat_score:.0f}/100)")
    if emph_count >= 2:
        reasons.append("high-impact reaction phrases detected")
    if opening_hook >= 65:
        reasons.append("engaging opening 3s momentum")
    if not reasons:
        reasons.append("balanced audio-visual momentum and clear dialogue pacing")

    explanation = (
        f"Selected around {peak_t:.1f}s due to " + ", ".join(reasons) + ". "
        "Note: Engagement score estimates relative moment strength, not a virality guarantee."
    )

    return HighlightSignalBreakdown(
        opening_hook=round(opening_hook, 1),
        emotional_intensity=round(emotional, 1),
        audio_excitement=round(float(np.clip(audio_score, 0, 100)), 1),
        visual_engagement=round(float(np.clip(visual_score, 0, 100)), 1),
        chat_activity=round(chat_score, 1) if chat_score is not None else None,
        content_clarity=round(clarity, 1),
        pacing=round(pacing, 1),
        total_score=round(total, 1),
        explanation=explanation,
    )


def select_highlights(
    audio: AudioAnalysisResult,
    visual: VisualAnalysisResult,
    chat_curve: Optional[np.ndarray],
    category: ContentCategory,
    preset: EditingPreset,
    intensity: EditingIntensity,
    preferred_duration: Optional[int] = None,
    max_clips: int = 5,
    enable_music: bool = True,
    enable_sfx: bool = True,
) -> List[ClipCandidate]:
    total_duration = max(audio.duration, visual.duration, 1.0)
    bin_sec = 0.5
    combined = fuse_multimodal_scores(audio.excitement_curve, visual.action_curve, chat_curve, category)

    # Smooth slightly with 3-bin kernel to avoid single-frame noise peaks
    if len(combined) >= 3:
        smoothed = np.convolve(combined, np.array([0.25, 0.5, 0.25]), mode="same")
    else:
        smoothed = combined

    # Rank candidate peak indices with minimum spacing to avoid duplicate clips
    sorted_indices = np.argsort(-smoothed)
    selected_windows: List[Tuple[float, float, float]] = []
    min_gap = max(8.0, min(18.0, total_duration / max(2, max_clips + 1)))

    # If video is short (<= 60s), always ensure at least 1 strong clip covering the best moment
    if total_duration <= 60.0 and max_clips >= 1:
        peak_idx = int(sorted_indices[0])
        peak_t = float(peak_idx * bin_sec)
        dur = min(60.0, total_duration)
        if preferred_duration and preferred_duration < total_duration:
            s_t, e_t = _snap_to_sentence_boundaries(0.0, dur, peak_t, float(preferred_duration), total_duration, audio.segments)
        else:
            s_t, e_t = 0.0, round(dur, 2)
        selected_windows.append((s_t, e_t, peak_t))

    for idx in sorted_indices:
        if len(selected_windows) >= max_clips:
            break
        peak_t = float(idx * bin_sec)
        # Skip if peak is already covered inside an existing clip or within min_gap
        if any((s - 3.0) <= peak_t <= (e + 3.0) or abs(peak_t - p) < min_gap for s, e, p in selected_windows):
            continue
        target_dur = _choose_optimal_duration(peak_t, total_duration, smoothed, bin_sec, preferred_duration)
        s_t, e_t = _snap_to_sentence_boundaries(0.0, total_duration, peak_t, float(target_dur), total_duration, audio.segments)
        # Ensure non-overlapping
        if any(not (e_t <= s + 1.5 or s_t >= e - 1.5) for s, e, _ in selected_windows):
            continue
        selected_windows.append((s_t, e_t, peak_t))

    if not selected_windows:
        dur = min(30.0, total_duration)
        selected_windows.append((0.0, round(dur, 2), round(dur * 0.5, 2)))

    preset_prof = PRESET_PROFILES[preset]
    int_prof = INTENSITY_PROFILES[intensity]

    candidates: List[ClipCandidate] = []
    for i, (s_t, e_t, peak_t) in enumerate(selected_windows):
        clip_segs = [seg for seg in audio.segments if seg.end >= s_t and seg.start <= e_t]
        transcript_text = " ".join(seg.text for seg in clip_segs).strip()
        breakdown = _compute_engagement_breakdown(s_t, e_t, peak_t, audio, visual, chat_curve, audio.segments, category)

        # Dead air cuts relative to clip start
        dead_cuts: List[DeadAirCut] = []
        for si0, si1 in audio.silence_intervals:
            ov0 = max(s_t + 0.5, si0)
            ov1 = min(e_t - 0.5, si1)
            if ov1 - ov0 >= int_prof.silence_trim_threshold:
                dead_cuts.append(DeadAirCut(start=round(ov0 - s_t, 2), end=round(ov1 - s_t, 2)))

        timeline = EditTimeline(
            trim_start=s_t,
            trim_end=e_t,
            reframe_mode=preset_prof.default_reframe_mode,
            preset=preset,
            intensity=intensity,
            caption_style=preset_prof.caption_style.model_copy(),
            dead_air_cuts=dead_cuts,
            music_volume=preset_prof.default_music_volume,
            enable_music=enable_music,
            enable_sfx=enable_sfx,
            music_track=preset_prof.default_music_track,
        )

        # Generate concise title from transcript or category
        if transcript_text:
            snippet = " ".join(transcript_text.split()[:7])
            title = snippet + ("..." if len(transcript_text.split()) > 7 else "")
        else:
            title = f"{category.value} Highlight #{i + 1}"

        candidates.append(
            ClipCandidate(
                clip_id=f"clip_{uuid.uuid4().hex[:8]}",
                title=title,
                start_time=s_t,
                end_time=e_t,
                duration=round(e_t - s_t, 2),
                peak_time=round(peak_t, 2),
                category=category,
                language=audio.detected_language,
                transcript_text=transcript_text,
                breakdown=breakdown,
                timeline=timeline,
            )
        )

    candidates.sort(key=lambda c: c.breakdown.total_score, reverse=True)
    return candidates
