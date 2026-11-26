"""Original royalty-free synthesized SFX and background music generator."""

from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Dict

import numpy as np

SAMPLE_RATE = 44100


def _write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -0.98, 0.98)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


def _gen_whoosh(duration: float = 0.42) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 1, len(t))
    # Smooth band-shaped envelope + pitch sweep
    env = np.sin(np.pi * t / duration) ** 1.6
    kernel = np.hanning(35)
    kernel /= kernel.sum()
    filtered = np.convolve(noise, kernel, mode="same")
    sweep = np.sin(2 * np.pi * (140 + 480 * (t / duration)) * t) * 0.25
    return (filtered * 1.4 + sweep) * env * 0.75


def _gen_impact(duration: float = 0.55) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freq = 135 * np.exp(-6.5 * t) + 38
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.sin(phase) * np.exp(-5.0 * t)
    rng = np.random.default_rng(7)
    transient = rng.normal(0, 0.35, len(t)) * np.exp(-45.0 * t)
    return (sub * 0.85 + transient) * 0.85


def _gen_pop(duration: float = 0.16) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freq = 520 + 680 * np.exp(-25 * t)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    env = np.exp(-22 * t) * (1 - np.exp(-220 * t))
    return np.sin(phase) * env * 0.7


def _gen_riser(duration: float = 1.2) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freq = 180 * (2 ** (2.2 * t / duration))
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    env = (t / duration) ** 2 * np.exp(-4 * np.maximum(0, t - duration * 0.9))
    return np.sin(phase) * env * 0.5


def _gen_music_loop(style: str, duration: float = 16.0) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    if style == "energetic_pulse":
        bpm = 124
        chords = [(220, 261.63, 329.63), (174.61, 220, 261.63), (196, 246.94, 293.66), (164.81, 196, 246.94)]
    elif style == "cyber_drive":
        bpm = 132
        chords = [(146.83, 220, 293.66), (164.81, 246.94, 329.63), (130.81, 196, 261.63), (146.83, 220, 293.66)]
    elif style == "cinematic_ambient":
        bpm = 80
        chords = [(130.81, 196, 246.94), (110, 164.81, 220), (146.83, 220, 261.63), (123.47, 196, 246.94)]
    elif style == "upbeat_groove":
        bpm = 116
        chords = [(261.63, 329.63, 392.0), (220, 261.63, 329.63), (174.61, 220, 261.63), (196, 246.94, 293.66)]
    else:  # lofi_focus
        bpm = 86
        chords = [(174.61, 220, 261.63, 329.63), (164.81, 196, 246.94, 293.66), (146.83, 174.61, 220, 261.63), (130.81, 164.81, 196, 246.94)]

    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4
    out = np.zeros_like(t)

    for i, chord in enumerate(chords):
        bar_start = i * bar_sec
        bar_end = (i + 1) * bar_sec
        mask = (t >= bar_start) & (t < bar_end)
        local_t = t[mask] - bar_start
        pad = np.zeros_like(local_t)
        for f in chord:
            pad += np.sin(2 * np.pi * f * local_t) * 0.14
            pad += np.sin(2 * np.pi * (f * 0.5) * local_t) * 0.08
        fade = np.minimum(local_t / 0.15, 1.0) * np.minimum((bar_sec - local_t) / 0.15, 1.0)
        out[mask] += pad * fade

    # Subtle rhythmic pulse kick on beats for energetic/cyber/groove
    if style in ("energetic_pulse", "cyber_drive", "upbeat_groove"):
        beat_idx = np.floor(t / beat_sec)
        beat_phase = t - beat_idx * beat_sec
        kick = np.sin(2 * np.pi * 62 * beat_phase) * np.exp(-14 * beat_phase) * 0.28
        hat = (np.sin(2 * np.pi * 4200 * beat_phase) * 0.03) * np.exp(-40 * beat_phase)
        out += kick + hat

    # Smooth loop boundary fade
    edge = int(0.05 * SAMPLE_RATE)
    out[:edge] *= np.linspace(0, 1, edge)
    out[-edge:] *= np.linspace(1, 0, edge)
    return np.tanh(out * 0.9) * 0.55


def ensure_audio_assets(assets_dir: str | Path) -> Dict[str, str]:
    """Generate and return paths to all built-in SFX and royalty-free music tracks."""
    base = Path(assets_dir) / "audio"
    base.mkdir(parents=True, exist_ok=True)

    generators = {
        "sfx_whoosh": ("whoosh.wav", _gen_whoosh),
        "sfx_impact": ("impact.wav", _gen_impact),
        "sfx_pop": ("pop.wav", _gen_pop),
        "sfx_riser": ("riser.wav", _gen_riser),
        "music_energetic_pulse": ("music_energetic_pulse.wav", lambda: _gen_music_loop("energetic_pulse")),
        "music_cyber_drive": ("music_cyber_drive.wav", lambda: _gen_music_loop("cyber_drive")),
        "music_cinematic_ambient": ("music_cinematic_ambient.wav", lambda: _gen_music_loop("cinematic_ambient")),
        "music_upbeat_groove": ("music_upbeat_groove.wav", lambda: _gen_music_loop("upbeat_groove")),
        "music_lofi_focus": ("music_lofi_focus.wav", lambda: _gen_music_loop("lofi_focus")),
    }

    paths: Dict[str, str] = {}
    for key, (filename, fn) in generators.items():
        p = base / filename
        if not p.exists() or p.stat().st_size < 1000:
            _write_wav(p, fn())
        paths[key] = str(p.resolve())
    return paths


def available_music_tracks() -> list[str]:
    return [
        "energetic_pulse",
        "cyber_drive",
        "lofi_focus",
        "cinematic_ambient",
        "upbeat_groove",
    ]
