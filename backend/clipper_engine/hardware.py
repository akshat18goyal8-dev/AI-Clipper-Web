"""Hardware acceleration probing with safe CPU fallback."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from typing import List, Optional

from .models import HardwareCapabilities


def _resolve_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    return name


def _test_ffmpeg_encoder(ffmpeg_path: str, encoder: str) -> bool:
    """Run a tiny 2-frame synthetic test encode to confirm encoder actually works on this host."""
    try:
        cmd = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=128x128:d=0.1",
            "-frames:v",
            "2",
            "-c:v",
            encoder,
            "-f",
            "null",
            "-",
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=8)
        return res.returncode == 0
    except Exception:
        return False


@lru_cache(maxsize=1)
def detect_hardware(prefer_gpu: bool = True) -> HardwareCapabilities:
    ffmpeg_path = _resolve_binary("ffmpeg")
    ffprobe_path = _resolve_binary("ffprobe")
    cpu_count = os.cpu_count() or 4

    torch_cuda = False
    cuda_name: Optional[str] = None
    try:
        import torch

        if torch.cuda.is_available():
            torch_cuda = True
            cuda_name = torch.cuda.get_device_name(0)
    except Exception:
        pass

    available_hw: List[str] = []
    if prefer_gpu:
        for enc in ("h264_nvenc", "h264_amf", "h264_qsv"):
            if _test_ffmpeg_encoder(ffmpeg_path, enc):
                available_hw.append(enc)

    preferred_encoder = available_hw[0] if (prefer_gpu and available_hw) else "libx264"
    whisper_device = "cuda" if (prefer_gpu and torch_cuda) else "cpu"
    whisper_compute = "float16" if whisper_device == "cuda" else "int8"

    return HardwareCapabilities(
        cpu_count=cpu_count,
        torch_cuda_available=torch_cuda,
        cuda_device_name=cuda_name,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        preferred_video_encoder=preferred_encoder,
        available_hw_encoders=available_hw,
        whisper_device=whisper_device,
        whisper_compute_type=whisper_compute,
    )
