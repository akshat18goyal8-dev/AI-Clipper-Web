"""Extensible video input & streaming platform integration layer."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import yt_dlp

from .hardware import detect_hardware
from .models import MediaSourceInfo, PlatformType


class MediaInputError(RuntimeError):
    """Raised when a video source or stream URL cannot be accessed or is unsupported."""

    def __init__(self, message: str, requires_credentials: bool = False, missing_fields: Optional[list[str]] = None):
        super().__init__(message)
        self.requires_credentials = requires_credentials
        self.missing_fields = missing_fields or []


def classify_source(source: str) -> PlatformType:
    s = source.strip()
    if not re.match(r"^https?://", s, re.IGNORECASE):
        return PlatformType.LOCAL_FILE
    host = urlparse(s).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return PlatformType.YOUTUBE
    if "twitch.tv" in host:
        return PlatformType.TWITCH
    if any(s.lower().split("?")[0].endswith(ext) for ext in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")):
        return PlatformType.DIRECT_URL
    return PlatformType.OTHER_STREAM


def probe_media_file(path: str) -> Dict[str, Any]:
    hw = detect_hardware()
    cmd = [
        hw.ffprobe_path,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if res.returncode != 0 or not res.stdout.strip():
        raise MediaInputError(f"Failed to probe media file '{path}': {res.stderr.strip() or 'invalid or corrupted media'}")
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v_stream:
        raise MediaInputError(f"No video stream found in '{path}'.")

    fps_raw = v_stream.get("r_frame_rate") or v_stream.get("avg_frame_rate") or "30/1"
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / max(float(den), 1.0)
    except Exception:
        fps = 30.0

    duration = float(data.get("format", {}).get("duration") or v_stream.get("duration") or 0.0)
    return {
        "width": int(v_stream.get("width", 1920)),
        "height": int(v_stream.get("height", 1080)),
        "fps": max(1.0, min(fps, 120.0)),
        "duration": duration,
        "has_audio": a_stream is not None,
    }


def resolve_video_input(
    source: str,
    download_dir: str | Path,
    youtube_api_key: Optional[str] = None,
    twitch_oauth_token: Optional[str] = None,
) -> MediaSourceInfo:
    """Resolve a local file, direct video URL, or supported platform URL to a local media path."""
    platform = classify_source(source)
    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)

    if platform == PlatformType.LOCAL_FILE:
        p = Path(source).expanduser()
        if not p.exists() or not p.is_file():
            raise MediaInputError(f"Local video file not found: {source}")
        meta = probe_media_file(str(p))
        return MediaSourceInfo(
            source_input=source,
            resolved_path=str(p.resolve()),
            platform=platform,
            title=p.stem,
            duration=meta["duration"],
            width=meta["width"],
            height=meta["height"],
            fps=meta["fps"],
            has_audio=meta["has_audio"],
            is_live=False,
        )

    # Direct HTTP(S) media file download via yt-dlp or FFmpeg
    out_tmpl = str(download_path / "%(id)s.%(ext)s")
    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source, download=False)
            if not info:
                raise MediaInputError(f"Could not extract media metadata from URL: {source}")

            if info.get("is_live"):
                raise MediaInputError(
                    "This URL points to an active live stream. Open it in Live Stream Monitor to capture highlights in real time."
                )

            info_dl = ydl.extract_info(source, download=True)
            resolved = ydl.prepare_filename(info_dl)
            # Adjust merged extension if needed
            mp4_candidate = Path(resolved).with_suffix(".mp4")
            if mp4_candidate.exists():
                resolved = str(mp4_candidate)
            if not Path(resolved).exists():
                raise MediaInputError(f"Download completed but output file was not created for {source}")

            meta = probe_media_file(resolved)
            return MediaSourceInfo(
                source_input=source,
                resolved_path=str(Path(resolved).resolve()),
                platform=platform,
                title=info_dl.get("title") or "Downloaded Video",
                duration=meta["duration"],
                width=meta["width"],
                height=meta["height"],
                fps=meta["fps"],
                has_audio=meta["has_audio"],
                is_live=False,
                metadata={
                    "uploader": info_dl.get("uploader"),
                    "channel": info_dl.get("channel"),
                    "id": info_dl.get("id"),
                    "webpage_url": info_dl.get("webpage_url"),
                    "youtube_api_configured": bool(youtube_api_key),
                    "twitch_oauth_configured": bool(twitch_oauth_token),
                },
            )
    except MediaInputError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        lower = msg.lower()
        if any(k in lower for k in ("sign in", "login", "private", "members-only", "cookies", "401", "403", "age")):
            raise MediaInputError(
                f"Platform requires authentication or access permissions for this URL ({platform.value}). "
                f"Configure valid platform credentials/cookies or ensure the video is publicly accessible. Details: {msg}",
                requires_credentials=True,
                missing_fields=["Platform Cookies / OAuth Token"],
            ) from exc
        if "drm" in lower:
            raise MediaInputError(
                "This stream/video is DRM-protected and cannot be processed.",
                requires_credentials=False,
            ) from exc
        raise MediaInputError(f"Unsupported or unreachable video URL ({platform.value}): {msg}") from exc
    except Exception as exc:
        raise MediaInputError(f"Failed to ingest URL '{source}': {exc}") from exc


def resolve_live_stream_url(source: str) -> Dict[str, Any]:
    """Resolve an active live stream URL into a playable HLS/media stream URL + metadata."""
    platform = classify_source(source)
    if platform == PlatformType.LOCAL_FILE:
        raise MediaInputError("Live Stream Monitor requires a live stream URL (e.g. YouTube Live, Twitch, or HLS .m3u8 URL).")

    if source.lower().split("?")[0].endswith(".m3u8"):
        return {
            "stream_url": source,
            "platform": platform,
            "title": "Direct HLS Live Stream",
            "channel": "",
            "video_id": "",
        }

    ydl_opts: Dict[str, Any] = {
        "format": "best[height<=1080]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source, download=False)
            if not info:
                raise MediaInputError(f"Unable to inspect stream URL: {source}")
            stream_url = info.get("url")
            if not stream_url and info.get("formats"):
                stream_url = info["formats"][-1].get("url")
            if not stream_url:
                raise MediaInputError("No playable stream manifest returned by platform.")
            return {
                "stream_url": stream_url,
                "platform": platform,
                "title": info.get("title") or "Live Stream",
                "channel": info.get("channel") or info.get("uploader") or info.get("uploader_id") or "",
                "video_id": info.get("id") or "",
                "is_live": bool(info.get("is_live", True)),
            }
    except MediaInputError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        lower = msg.lower()
        if any(k in lower for k in ("sign in", "login", "private", "401", "403", "subscriber")):
            raise MediaInputError(
                f"Live stream access requires authentication/permissions ({platform.value}). Details: {msg}",
                requires_credentials=True,
                missing_fields=["TWITCH_OAUTH_TOKEN / YOUTUBE_API_KEY"],
            ) from exc
        raise MediaInputError(f"Failed to connect to live stream '{source}': {msg}") from exc
