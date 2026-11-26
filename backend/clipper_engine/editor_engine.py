"""Professional AI video editing & rendering engine (1080x1920 vertical, zooms, overlays, captions, sound)."""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .captions import write_ass_subtitles
from .hardware import detect_hardware
from .models import (
    ClipCandidate,
    ClipRenderResult,
    ContentCategory,
    EditTimeline,
    GraphicOverlay,
    ZoomKeyframe,
)
from .reframer import SubjectReframer
from .sound_design import build_final_audio_mix


def _load_pil_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    c = hex_color.lstrip("#")
    if len(c) != 6:
        return (255, 220, 0)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _compute_zoom_and_shake(t: float, keyframes: List[ZoomKeyframe]) -> Tuple[float, float, float]:
    scale = 1.0
    dx, dy = 0.0, 0.0
    for kf in keyframes:
        if kf.time <= t <= kf.time + kf.duration:
            prog = (t - kf.time) / max(0.05, kf.duration)
            if kf.easing == "punch":
                # Fast attack, smooth settle
                eased = math.sin(min(1.0, prog * 2.2) * math.pi * 0.5) * (1.0 - max(0.0, prog - 0.55) / 0.45 * 0.65)
            elif kf.easing == "ease_out":
                eased = math.sin(prog * math.pi)
            else:
                eased = 0.5 - 0.5 * math.cos(prog * 2 * math.pi)
            scale = max(scale, 1.0 + (kf.target_scale - 1.0) * max(0.0, eased))
            if kf.shake_intensity > 0 and prog < 0.45:
                decay = 1.0 - (prog / 0.45)
                dx += math.sin(t * 68.0) * kf.shake_intensity * decay * 2.5
                dy += math.cos(t * 54.0) * kf.shake_intensity * decay * 2.5
    return scale, dx, dy


def _draw_overlays(frame_bgr: np.ndarray, t: float, overlays: List[GraphicOverlay]) -> np.ndarray:
    active = [ov for ov in overlays if ov.time <= t <= ov.time + ov.duration]
    if not active:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    pil_img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_layer)

    for ov in active:
        local_t = t - ov.time
        fade_in = min(1.0, local_t / 0.16)
        fade_out = min(1.0, max(0.0, (ov.duration - local_t) / 0.18))
        alpha = int(240 * min(fade_in, fade_out))
        if alpha <= 5:
            continue

        accent_rgb = _hex_to_rgb(ov.accent_color)
        is_hook = ov.style == "hook_banner"
        font = _load_pil_font(44 if is_hook else 52)
        text = ov.text.strip()
        if not text:
            continue

        # Wrap text cleanly
        words = text.split()
        lines: List[str] = []
        cur = ""
        for wd in words:
            test = (cur + " " + wd).strip()
            if len(test) > (24 if is_hook else 18) and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = test
        if cur:
            lines.append(cur)
        wrapped = "\n".join(lines[:2])

        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=8)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x, pad_y = 36, 20
        box_w = min(w - 80, tw + pad_x * 2)
        box_h = th + pad_y * 2
        x0 = (w - box_w) // 2
        y0 = int(h * ov.position_y) - box_h // 2

        if is_hook:
            bg_col = (15, 23, 42, int(alpha * 0.90))
            border_col = (*accent_rgb, alpha)
            txt_col = (255, 255, 255, alpha)
        else:
            bg_col = (*accent_rgb, int(alpha * 0.92))
            border_col = (255, 255, 255, alpha)
            txt_col = (10, 12, 18, alpha)

        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=22, fill=bg_col, outline=border_col, width=4)
        draw.multiline_text(
            (w // 2, y0 + box_h // 2),
            wrapped,
            font=font,
            fill=txt_col,
            anchor="mm",
            align="center",
            spacing=8,
        )

    composited = Image.alpha_composite(pil_img, overlay_layer).convert("RGB")
    return cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)


def _draw_intro_outro(frame_bgr: np.ndarray, t: float, total_dur: float, timeline: EditTimeline) -> np.ndarray:
    text = ""
    if timeline.intro_text and t < 1.5:
        text = timeline.intro_text
    elif timeline.outro_text and t > max(0.0, total_dur - 1.8):
        text = timeline.outro_text
    if not text:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    pil_img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _load_pil_font(50)
    draw.rounded_rectangle([90, h // 2 - 80, w - 90, h // 2 + 80], radius=24, fill=(10, 14, 24, 215), outline=(56, 189, 248, 255), width=4)
    draw.text((w // 2, h // 2), text, font=font, fill=(255, 255, 255, 255), anchor="mm")
    return cv2.cvtColor(np.array(Image.alpha_composite(pil_img, layer).convert("RGB")), cv2.COLOR_RGB2BGR)


def render_clip(
    source_video: str,
    clip: ClipCandidate,
    output_mp4_path: str | Path,
    assets_dir: str | Path,
    use_gpu: bool = True,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> ClipRenderResult:
    """Render a fully edited 1080x1920 vertical clip with reframing, zooms, overlays, captions, and sound."""
    hw = detect_hardware(prefer_gpu=use_gpu)
    tl: EditTimeline = clip.timeline
    out_mp4 = Path(output_mp4_path)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    thumb_path = out_mp4.with_suffix(".jpg")

    cap = cv2.VideoCapture(source_video)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source video for rendering: {source_video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    out_fps = min(30.0, max(24.0, src_fps))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)

    trim_start = max(0.0, tl.trim_start)
    trim_end = max(trim_start + 1.0, tl.trim_end)
    clip_dur = min(60.0, trim_end - trim_start)
    trim_end = trim_start + clip_dur

    reframer = SubjectReframer(
        src_width=src_w,
        src_height=src_h,
        target_width=tl.target_width,
        target_height=tl.target_height,
        category=clip.category,
        mode=tl.reframe_mode,
        crop_offset_x=tl.crop_offset_x,
        crop_offset_y=tl.crop_offset_y,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        raw_video_path = tmp_dir / "video_only.mp4"
        audio_wav_path = tmp_dir / "audio_mix.wav"
        ass_path = tmp_dir / "captions.ass"

        # 1. Write dynamic ASS subtitles
        has_captions = len(tl.captions) > 0
        if has_captions:
            write_ass_subtitles(tl.captions, tl.caption_style, ass_path, tl.target_width, tl.target_height)

        # 2. Mix normalized dialogue + SFX + ducked background music
        if progress_cb:
            progress_cb(0.15, "Mixing dialogue, sound effects, and background music...")
        build_final_audio_mix(
            source_video=source_video,
            timeline=tl,
            out_wav_path=audio_wav_path,
            assets_dir=assets_dir,
            final_duration=clip_dur,
        )

        # 3. Render vertical reframed + smart-zoomed + overlaid frames directly into FFmpeg pipe
        encoder = hw.preferred_video_encoder if use_gpu else "libx264"
        enc_args = ["-c:v", encoder]
        if encoder == "libx264":
            enc_args.extend(["-preset", "medium", "-crf", "20"])
        elif encoder == "h264_nvenc":
            enc_args.extend(["-preset", "p4", "-cq", "21"])
        elif encoder == "h264_amf":
            enc_args.extend(["-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"])
        elif encoder == "h264_qsv":
            enc_args.extend(["-global_quality", "21"])

        vf_filters: List[str] = []
        if has_captions:
            # Escape Windows path backslashes and colons for FFmpeg ass filter
            ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
            vf_filters.append(f"ass='{ass_escaped}'")

        pipe_cmd = [
            hw.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{tl.target_width}x{tl.target_height}",
            "-r",
            f"{out_fps:.3f}",
            "-i",
            "-",
            "-i",
            str(audio_wav_path),
            *(["-vf", ",".join(vf_filters)] if vf_filters else []),
            *enc_args,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(out_mp4),
        ]

        proc = subprocess.Popen(pipe_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        cap.set(cv2.CAP_PROP_POS_MSEC, trim_start * 1000.0)

        total_out_frames = max(1, int(round(clip_dur * out_fps)))
        frame_step = src_fps / out_fps
        src_pos_acc = 0.0
        last_frame: Optional[np.ndarray] = None
        thumb_saved = False

        for out_idx in range(total_out_frames):
            t_rel = out_idx / out_fps
            # Advance source capture accurately to match out_fps
            target_src_offset = int(round(out_idx * frame_step))
            while src_pos_acc <= target_src_offset:
                ret, frm = cap.read()
                src_pos_acc += 1.0
                if ret:
                    last_frame = frm
                else:
                    break
            if last_frame is None:
                break

            zoom_scale, shake_dx, shake_dy = _compute_zoom_and_shake(t_rel, tl.zoom_keyframes)
            v_frame = reframer.reframe_frame(last_frame, zoom_scale=zoom_scale, shake_dx=shake_dx, shake_dy=shake_dy)
            v_frame = _draw_overlays(v_frame, t_rel, tl.overlays)
            v_frame = _draw_intro_outro(v_frame, t_rel, clip_dur, tl)

            if not thumb_saved and (out_idx >= min(total_out_frames - 1, int(out_fps * 0.8))):
                cv2.imwrite(str(thumb_path), v_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                thumb_saved = True

            assert proc.stdin is not None
            try:
                proc.stdin.write(v_frame.tobytes())
            except BrokenPipeError:
                break

            if progress_cb and out_idx % max(1, total_out_frames // 10) == 0:
                pct = 0.20 + 0.75 * (out_idx / total_out_frames)
                progress_cb(pct, f"Rendering vertical frames ({out_idx}/{total_out_frames})...")

        cap.release()
        if proc.stdin:
            proc.stdin.close()
        stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
        retcode = proc.wait()

        # Automatic CPU fallback if hardware encoder failed mid-stream
        if retcode != 0 and encoder != "libx264":
            return render_clip(source_video, clip, output_mp4_path, assets_dir, use_gpu=False, progress_cb=progress_cb)
        if retcode != 0:
            raise RuntimeError(f"FFmpeg render failed ({encoder}): {stderr_out}")

        if not thumb_saved and last_frame is not None:
            v_thumb = reframer.reframe_frame(last_frame)
            cv2.imwrite(str(thumb_path), v_thumb, [cv2.IMWRITE_JPEG_QUALITY, 90])

    if progress_cb:
        progress_cb(1.0, "Clip export complete")

    return ClipRenderResult(
        clip_id=clip.clip_id,
        title=clip.title,
        output_path=str(out_mp4.resolve()),
        thumbnail_path=str(thumb_path.resolve()),
        duration=round(clip_dur, 2),
        width=tl.target_width,
        height=tl.target_height,
        encoder_used=encoder,
        score=clip.breakdown.total_score,
        explanation=clip.breakdown.explanation,
        timeline=tl,
    )
