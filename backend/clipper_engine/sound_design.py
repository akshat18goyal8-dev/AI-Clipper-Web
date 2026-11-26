"""Sound design engine: voice normalization, noise reduction, SFX mixing, and ducked background music."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

from .hardware import detect_hardware
from .models import EditTimeline
from .sound_assets import ensure_audio_assets


def build_final_audio_mix(
    source_video: str,
    timeline: EditTimeline,
    out_wav_path: str | Path,
    assets_dir: str | Path,
    final_duration: float,
) -> str:
    """Produce a broadcast-leveled audio track with noise reduction, SFX, and ducked music."""
    hw = detect_hardware()
    assets: Dict[str, str] = ensure_audio_assets(assets_dir)
    out_path = Path(out_wav_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # First extract trimmed source dialogue with optional noise reduction & loudness normalization
    dialogue_wav = out_path.with_name(out_path.stem + "_dlg.wav")
    trim_dur = max(0.5, timeline.trim_end - timeline.trim_start)

    # Check if source has audio
    probe_cmd = [
        hw.ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        source_video,
    ]
    has_audio = bool(subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10).stdout.strip())

    if has_audio:
        a_filters: List[str] = []
        if timeline.enable_noise_reduction:
            a_filters.append("afftdn=nf=-25")
        a_filters.append("dynaudnorm=f=150:g=15")
        a_filters.append(f"volume={max(0.0, min(2.0, timeline.dialogue_volume)):.2f}")
        cmd_dlg = [
            hw.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timeline.trim_start:.3f}",
            "-t",
            f"{trim_dur:.3f}",
            "-i",
            source_video,
            "-vn",
            "-af",
            ",".join(a_filters),
            "-ac",
            "2",
            "-ar",
            "44100",
            "-t",
            f"{final_duration:.3f}",
            str(dialogue_wav),
        ]
        subprocess.run(cmd_dlg, capture_output=True, text=True, timeout=60, check=True)
    else:
        # Generate silent dialogue track so SFX + music still mix cleanly
        cmd_sil = [
            hw.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={final_duration:.3f}",
            str(dialogue_wav),
        ]
        subprocess.run(cmd_sil, capture_output=True, text=True, timeout=30, check=True)

    # Assemble FFmpeg filtergraph mixing dialogue + ducked music + timed SFX
    inputs: List[str] = ["-i", str(dialogue_wav)]
    mix_labels: List[str] = ["[0:a]"]
    filter_parts: List[str] = []
    input_idx = 1

    if timeline.enable_music and timeline.music_volume > 0.005:
        music_key = f"music_{timeline.music_track}"
        music_file = assets.get(music_key) or assets["music_energetic_pulse"]
        inputs.extend(["-stream_loop", "-1", "-i", music_file])
        m_vol = max(0.0, min(1.0, timeline.music_volume))
        filter_parts.append(
            f"[{input_idx}:a]atrim=0:{final_duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={m_vol:.3f},afade=t=in:st=0:d=0.4,afade=t=out:st={max(0, final_duration - 0.6):.3f}:d=0.6[bgm]"
        )
        # Duck music slightly beneath speech using sidechaincompress when dialogue exists
        if has_audio:
            filter_parts.append("[0:a]asplit=2[dlg_main][dlg_sc]")
            filter_parts.append(
                "[bgm][dlg_sc]sidechaincompress=threshold=0.04:ratio=4:attack=30:release=250[bgm_ducked]"
            )
            mix_labels = ["[dlg_main]", "[bgm_ducked]"]
        else:
            mix_labels.append("[bgm]")
        input_idx += 1

    if timeline.enable_sfx and timeline.sfx_volume > 0.005 and timeline.sfx_events:
        for s_idx, ev in enumerate(timeline.sfx_events[:12]):
            if ev.time < 0 or ev.time >= final_duration:
                continue
            sfx_file = assets.get(f"sfx_{ev.sfx_type}") or assets["sfx_whoosh"]
            inputs.extend(["-i", sfx_file])
            delay_ms = int(ev.time * 1000)
            vol = max(0.0, min(1.5, ev.volume * timeline.sfx_volume))
            lbl = f"sfx{s_idx}"
            filter_parts.append(
                f"[{input_idx}:a]aresample=44100,aformat=channel_layouts=stereo,"
                f"volume={vol:.3f},adelay={delay_ms}|{delay_ms}[{lbl}]"
            )
            mix_labels.append(f"[{lbl}]")
            input_idx += 1

    if len(mix_labels) == 1:
        # Just copy normalized dialogue
        if str(dialogue_wav) != str(out_path):
            dialogue_wav.replace(out_path)
        return str(out_path.resolve())

    n_mix = len(mix_labels)
    filter_parts.append(
        "".join(mix_labels) + f"amix=inputs={n_mix}:duration=first:dropout_transition=2:normalize=0,"
        "alimiter=limit=0.95[outa]"
    )

    cmd_mix = [
        hw.ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[outa]",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-t",
        f"{final_duration:.3f}",
        str(out_path),
    ]
    res = subprocess.run(cmd_mix, capture_output=True, text=True, timeout=90)
    if res.returncode != 0:
        # Safe fallback to dialogue audio if complex mix fails
        if dialogue_wav.exists():
            dialogue_wav.replace(out_path)
            return str(out_path.resolve())
        raise RuntimeError(f"Audio mix failed: {res.stderr}")
    if dialogue_wav.exists():
        try:
            dialogue_wav.unlink()
        except OSError:
            pass
    return str(out_path.resolve())
