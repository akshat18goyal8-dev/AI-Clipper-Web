"""Smart vertical 9:16 subject-tracking reframer (1080x1920)."""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from .face_detector import SubjectFaceDetector
from .models import ContentCategory


class SubjectReframer:
    """Computes smooth, subject-aware 9:16 framing transforms per frame."""

    def __init__(
        self,
        src_width: int,
        src_height: int,
        target_width: int = 1080,
        target_height: int = 1920,
        category: ContentCategory = ContentCategory.GENERAL,
        mode: str = "smart_track",
        crop_offset_x: float = 0.0,
        crop_offset_y: float = 0.0,
    ):
        self.src_w = src_width
        self.src_h = src_height
        self.dst_w = target_width
        self.dst_h = target_height
        self.category = category
        self.mode = mode
        self.offset_x = float(np.clip(crop_offset_x, -1.0, 1.0))
        self.offset_y = float(np.clip(crop_offset_y, -1.0, 1.0))

        self.face_detector = SubjectFaceDetector()
        self._smooth_cx = 0.5
        self._smooth_cy = 0.45
        self._prev_gray: np.ndarray | None = None
        self._frame_counter = 0

    def _detect_subject_center(self, frame: np.ndarray) -> Tuple[float, float]:
        """Detect primary face or salient motion center (normalized 0..1)."""
        small_w, small_h = 320, max(180, int(320 * self.src_h / max(1, self.src_w)))
        small = cv2.resize(frame, (small_w, small_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        target_cx, target_cy = self._smooth_cx, self._smooth_cy
        detected = False

        # Run face detection every 4 frames for speed & stability
        if self._frame_counter % 4 == 0:
            faces = self.face_detector.detect_faces(small)
            if len(faces) > 0:
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                target_cx = (x + w * 0.5) / small_w
                # Keep headroom slightly above face center
                target_cy = (y + h * 0.42) / small_h
                detected = True

        # If no face detected, use motion saliency center-of-mass
        if not detected and self._prev_gray is not None:
            diff = cv2.absdiff(gray, self._prev_gray)
            mask = diff > 24
            if np.sum(mask) > 40:
                ys, xs = np.where(mask)
                target_cx = float(np.mean(xs)) / small_w
                target_cy = float(np.mean(ys)) / small_h

        self._prev_gray = gray
        self._frame_counter += 1

        # Exponential smoothing to prevent jittery camera jumps
        alpha = 0.14 if detected else 0.06
        self._smooth_cx = (1.0 - alpha) * self._smooth_cx + alpha * target_cx
        self._smooth_cy = (1.0 - alpha) * self._smooth_cy + alpha * target_cy
        return self._smooth_cx, self._smooth_cy

    def reframe_frame(
        self,
        frame: np.ndarray,
        zoom_scale: float = 1.0,
        shake_dx: float = 0.0,
        shake_dy: float = 0.0,
    ) -> np.ndarray:
        """Transform input frame into crisp 1080x1920 vertical output."""
        h, w = frame.shape[:2]
        target_ar = self.dst_w / float(self.dst_h)
        src_ar = w / float(max(1, h))

        cx_norm, cy_norm = self._detect_subject_center(frame)
        cx_norm = float(np.clip(cx_norm + self.offset_x * 0.35, 0.1, 0.9))
        cy_norm = float(np.clip(cy_norm + self.offset_y * 0.35, 0.1, 0.9))

        if self.mode == "blur_fill" and src_ar > 1.1:
            return self._render_blur_fill(frame, zoom_scale, shake_dx, shake_dy)

        if self.mode == "split_gaming" and src_ar > 1.2:
            return self._render_split_gaming(frame, cx_norm, zoom_scale, shake_dx, shake_dy)

        # Smart dynamic 9:16 crop-and-pan
        if src_ar >= target_ar:
            crop_h = int(h / max(1.0, zoom_scale))
            crop_w = int(crop_h * target_ar)
        else:
            crop_w = int(w / max(1.0, zoom_scale))
            crop_h = int(crop_w / target_ar)

        crop_w = max(64, min(w, crop_w))
        crop_h = max(64, min(h, crop_h))

        x0 = int(cx_norm * w - crop_w * 0.5 + shake_dx)
        y0 = int(cy_norm * h - crop_h * 0.5 + shake_dy)
        x0 = max(0, min(w - crop_w, x0))
        y0 = max(0, min(h - crop_h, y0))

        cropped = frame[y0 : y0 + crop_h, x0 : x0 + crop_w]
        return cv2.resize(cropped, (self.dst_w, self.dst_h), interpolation=cv2.INTER_LANCZOS4)

    def _render_blur_fill(
        self,
        frame: np.ndarray,
        zoom_scale: float,
        shake_dx: float,
        shake_dy: float,
    ) -> np.ndarray:
        """Intelligent blurred ambient fill + sharp zoomed foreground (zero plain black bars)."""
        h, w = frame.shape[:2]
        # Background blurred full-height fill
        bg_scale = self.dst_h / float(h)
        bg_w = int(w * bg_scale)
        bg_full = cv2.resize(frame, (max(self.dst_w, bg_w), self.dst_h), interpolation=cv2.INTER_LINEAR)
        x_mid = max(0, (bg_full.shape[1] - self.dst_w) // 2)
        bg = bg_full[:, x_mid : x_mid + self.dst_w]
        bg = cv2.GaussianBlur(bg, (51, 51), 0)
        bg = (bg.astype(np.float32) * 0.42).astype(np.uint8)

        # Foreground centered slightly above center (leaves room for bottom captions)
        fg_w = self.dst_w
        fg_h = int(fg_w * h / float(w))
        if zoom_scale > 1.001:
            zw = int(w / zoom_scale)
            zh = int(h / zoom_scale)
            zx0 = max(0, min(w - zw, int((w - zw) * 0.5 + self.offset_x * zw * 0.3 + shake_dx)))
            zy0 = max(0, min(h - zh, int((h - zh) * 0.5 + self.offset_y * zh * 0.3 + shake_dy)))
            src_fg = frame[zy0 : zy0 + zh, zx0 : zx0 + zw]
        else:
            src_fg = frame

        fg = cv2.resize(src_fg, (fg_w, fg_h), interpolation=cv2.INTER_LANCZOS4)
        y_top = max(80, int((self.dst_h - fg_h) * 0.40))
        y_end = min(self.dst_h, y_top + fg_h)
        bg[y_top:y_end, :fg_w] = fg[: y_end - y_top, :]
        return bg

    def _render_split_gaming(
        self,
        frame: np.ndarray,
        cx_norm: float,
        zoom_scale: float,
        shake_dx: float,
        shake_dy: float,
    ) -> np.ndarray:
        """Top 62% focused gameplay action + bottom 38% blurred context/facecam zone."""
        h, w = frame.shape[:2]
        canvas = self._render_blur_fill(frame, zoom_scale=1.0, shake_dx=0.0, shake_dy=0.0)

        # Top main gameplay window (1080 x 1180) focused around active center
        top_h = 1140
        top_ar = self.dst_w / float(top_h)
        crop_h = int(h / max(1.0, zoom_scale))
        crop_w = min(w, int(crop_h * top_ar))
        x0 = max(0, min(w - crop_w, int(cx_norm * w - crop_w * 0.5 + shake_dx)))
        y0 = max(0, min(h - crop_h, int((h - crop_h) * 0.5 + shake_dy)))
        top_crop = cv2.resize(frame[y0 : y0 + crop_h, x0 : x0 + crop_w], (self.dst_w, top_h), interpolation=cv2.INTER_LANCZOS4)

        canvas[120 : 120 + top_h, :] = top_crop
        # Subtle divider accent line
        cv2.line(canvas, (0, 120 + top_h), (self.dst_w, 120 + top_h), (40, 230, 170), 3)
        return canvas
