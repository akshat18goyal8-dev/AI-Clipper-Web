"""Audio intelligence: acoustic excitement analysis + Whisper ASR with word timestamps."""

from __future__ import annotations

import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .hardware import detect_hardware
from .models import ContentCategory, TranscriptSegment, WordTimestamp

EXCITEMENT_KEYWORDS = {
    "common": {
        "bro", "omg", "what", "wait", "insane", "crazy", "no way", "oh my god",
        "actually", "literally", "unbelievable", "wtf", "stop", "look", "listen",
        "bhai", "yaar", "kya", "arey", "dekho", "sach", "bawaal", "gazab",
    },
    ContentCategory.GAMING: {
        "clutch", "headshot", "ace", "kill", "eliminated", "one hp", "wipe", "gg",
        "no scope", "boss", "win", "victory", "comeback", "revive", "rush", "shot",
    },
    ContentCategory.PODCASTS: {
        "truth", "secret", "mistake", "problem", "million", "honest", "controversial",
        "reason", "never", "always", "changed", "story", "lesson", "remember",
    },
    ContentCategory.EDUCATION: {
        "important", "remember", "key", "formula", "step", "because", "therefore",
        "example", "mistake", "concept", "rule", "trick", "method", "why",
    },
    ContentCategory.ENTERTAINMENT: {
        "funny", "laugh", "prank", "surprise", "reveal", "shocked", "hilarious", "twist",
    },
}


@dataclass
class AudioAnalysisResult:
    duration: float
    sample_rate: int
    timeline_times: np.ndarray  # 0.5s bins
    excitement_curve: np.ndarray  # 0..100 per bin
    rms_db_curve: np.ndarray
    silence_intervals: List[Tuple[float, float]]
    segments: List[TranscriptSegment]
    detected_language: str


@lru_cache(maxsize=2)
def _load_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device=device, compute_type=compute_type)


def extract_mono_wav(video_path: str, out_wav: str, sample_rate: int = 16000) -> bool:
    hw = detect_hardware()
    cmd = [
        hw.ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        out_wav,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return res.returncode == 0 and Path(out_wav).exists() and Path(out_wav).stat().st_size > 100


def _read_wav_float32(wav_path: str) -> Tuple[np.ndarray, int]:
    with wave.open(wav_path, "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, sr


def compute_acoustic_features(
    samples: np.ndarray,
    sr: int,
    bin_sec: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Tuple[float, float]]]:
    """Compute acoustic excitement curve (0..100), RMS dB, and silence intervals."""
    if len(samples) == 0:
        t = np.array([0.0], dtype=np.float32)
        return t, np.zeros(1, dtype=np.float32), np.array([-60.0], dtype=np.float32), []

    bin_size = max(1, int(sr * bin_sec))
    num_bins = max(1, int(np.ceil(len(samples) / bin_size)))
    padded = np.pad(samples, (0, num_bins * bin_size - len(samples)))
    frames = padded.reshape(num_bins, bin_size)

    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-9)
    rms_db = 20.0 * np.log10(rms + 1e-6)
    peak = np.max(np.abs(frames), axis=1)

    # Zero-crossing rate proxy for vocal intensity / shouting / fricative bursts
    signs = np.signbit(frames)
    zcr = np.mean(signs[:, 1:] != signs[:, :-1], axis=1)

    # Spectral flux across consecutive bins
    mag = np.abs(np.fft.rfft(frames * np.hanning(bin_size), axis=1))
    mag_norm = mag / (np.sum(mag, axis=1, keepdims=True) + 1e-8)
    flux = np.zeros(num_bins, dtype=np.float32)
    if num_bins > 1:
        diff = np.maximum(0.0, mag_norm[1:] - mag_norm[:-1])
        flux[1:] = np.sum(diff, axis=1)

    # Normalize relative to baseline using robust median/std z-scores
    def robust_norm(arr: np.ndarray) -> np.ndarray:
        med = np.median(arr)
        mad = np.median(np.abs(arr - med)) + 1e-5
        z = (arr - med) / (1.4826 * mad)
        return np.clip((z + 0.5) / 4.0, 0.0, 1.0)

    rms_score = robust_norm(rms_db)
    peak_score = robust_norm(peak)
    flux_score = robust_norm(flux)
    zcr_score = robust_norm(zcr)

    # Sudden jump bonus vs previous 4-second local baseline
    jump = np.zeros(num_bins, dtype=np.float32)
    win = max(2, int(4.0 / bin_sec))
    for i in range(num_bins):
        lo = max(0, i - win)
        local_med = np.median(rms_db[lo:i]) if i > lo else rms_db[i]
        jump[i] = np.clip((rms_db[i] - local_med) / 14.0, 0.0, 1.0)

    combined = (
        0.38 * rms_score
        + 0.22 * peak_score
        + 0.18 * flux_score
        + 0.10 * zcr_score
        + 0.12 * jump
    )
    # Mute true silence bins
    silence_thresh = max(-48.0, float(np.percentile(rms_db, 15)) + 3.0)
    is_silent = rms_db < min(-34.0, silence_thresh)
    combined[is_silent] *= 0.15
    excitement_curve = np.clip(combined * 100.0, 0.0, 100.0).astype(np.float32)

    silence_intervals: List[Tuple[float, float]] = []
    cur_start: Optional[float] = None
    for idx, silent in enumerate(is_silent):
        t0 = idx * bin_sec
        if silent and cur_start is None:
            cur_start = t0
        elif not silent and cur_start is not None:
            if t0 - cur_start >= 0.6:
                silence_intervals.append((cur_start, t0))
            cur_start = None
    if cur_start is not None:
        end_t = num_bins * bin_sec
        if end_t - cur_start >= 0.6:
            silence_intervals.append((cur_start, end_t))

    times = np.arange(num_bins, dtype=np.float32) * bin_sec
    return times, excitement_curve, rms_db.astype(np.float32), silence_intervals


def _score_text_excitement(text: str, category: ContentCategory) -> float:
    lower = text.lower()
    score = 0.0
    if "!" in text:
        score += 18.0
    if "?" in text:
        score += 10.0
    kws = EXCITEMENT_KEYWORDS["common"] | EXCITEMENT_KEYWORDS.get(category, set())
    hits = sum(1 for kw in kws if kw in lower)
    score += min(45.0, hits * 15.0)
    # All caps emphasis words
    caps_words = [w for w in text.split() if len(w) >= 3 and w.isupper()]
    score += min(20.0, len(caps_words) * 8.0)
    return min(100.0, score)


def analyze_audio(
    video_path: str,
    category: ContentCategory = ContentCategory.GENERAL,
    language: str = "auto",
    whisper_model: str = "base",
    use_gpu: bool = True,
    bin_sec: float = 0.5,
) -> AudioAnalysisResult:
    hw = detect_hardware(prefer_gpu=use_gpu)
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = str(Path(tmp) / "audio.wav")
        ok = extract_mono_wav(video_path, wav_path, sample_rate=16000)
        if not ok:
            t = np.array([0.0], dtype=np.float32)
            return AudioAnalysisResult(
                duration=0.0,
                sample_rate=16000,
                timeline_times=t,
                excitement_curve=np.zeros(1, dtype=np.float32),
                rms_db_curve=np.array([-60.0], dtype=np.float32),
                silence_intervals=[],
                segments=[],
                detected_language="en",
            )

        samples, sr = _read_wav_float32(wav_path)
        duration = len(samples) / float(sr)
        times, curve, rms_db, silences = compute_acoustic_features(samples, sr, bin_sec=bin_sec)

        # Run Whisper ASR with word-level timestamps if there is non-silent audio
        segments: List[TranscriptSegment] = []
        detected_lang = "en" if language == "auto" else language

        if float(np.max(np.abs(samples))) > 0.004:
            try:
                model = _load_whisper_model(whisper_model, hw.whisper_device, hw.whisper_compute_type)
                lang_arg = None if language == "auto" else language
                raw_segs, info = model.transcribe(
                    wav_path,
                    language=lang_arg,
                    word_timestamps=True,
                    vad_filter=True,
                    beam_size=1,
                )
                if info and getattr(info, "language", None):
                    detected_lang = info.language
                emph_kws = EXCITEMENT_KEYWORDS["common"] | EXCITEMENT_KEYWORDS.get(category, set())
                for seg in raw_segs:
                    words: List[WordTimestamp] = []
                    for w in (seg.words or []):
                        w_clean = w.word.strip()
                        if not w_clean:
                            continue
                        is_emph = (
                            w_clean.lower().strip(".,!?") in emph_kws
                            or w_clean.endswith("!")
                            or (len(w_clean) >= 3 and w_clean.isupper())
                        )
                        words.append(
                            WordTimestamp(
                                word=w_clean,
                                start=float(w.start),
                                end=float(w.end),
                                probability=float(getattr(w, "probability", 1.0)),
                                is_emphasis=is_emph,
                            )
                        )
                    t_seg = TranscriptSegment(
                        start=float(seg.start),
                        end=float(seg.end),
                        text=seg.text.strip(),
                        language=detected_lang,
                        words=words,
                    )
                    segments.append(t_seg)

                    # Boost excitement curve in bins containing semantic excitement
                    sem_boost = _score_text_excitement(t_seg.text, category)
                    if sem_boost > 0:
                        mask = (times >= t_seg.start) & (times <= t_seg.end)
                        curve[mask] = np.clip(curve[mask] * 0.72 + sem_boost * 0.35, 0.0, 100.0)
            except Exception:
                # If whisper model download/load fails offline, acoustic analysis still operates gracefully
                pass

        return AudioAnalysisResult(
            duration=duration,
            sample_rate=sr,
            timeline_times=times,
            excitement_curve=curve,
            rms_db_curve=rms_db,
            silence_intervals=silences,
            segments=segments,
            detected_language=detected_lang,
        )
