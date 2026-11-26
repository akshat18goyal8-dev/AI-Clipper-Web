"""Visual intelligence: motion energy, scene transitions, flash/explosion bursts, and face tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from .face_detector import SubjectFaceDetector


@dataclass
class VisualAnalysisResult:
    duration: float
    timeline_times: np.ndarray  # 0.5s bins
    action_curve: np.ndarray  # 0..100 per bin
    face_centers: List[Tuple[float, float, float]]  # (time, norm_cx, norm_cy)


def analyze_visual(video_path: str, bin_sec: float = 0.5, sample_fps: float = 4.0) -> VisualAnalysisResult:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        t = np.array([0.0], dtype=np.float32)
        return VisualAnalysisResult(0.0, t, np.zeros(1, dtype=np.float32), [])

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / fps if total_frames > 0 else 0.0
    step = max(1, int(round(fps / sample_fps)))

    face_detector = SubjectFaceDetector()
    prev_gray: np.ndarray | None = None
    prev_hist: np.ndarray | None = None
    prev_mean_luma: float | None = None

    sample_times: List[float] = []
    sample_scores: List[float] = []
    face_centers: List[Tuple[float, float, float]] = []

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step == 0:
            t_sec = frame_idx / fps
            small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            luma = float(np.mean(gray))
            hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
            cv2.normalize(hist, hist)

            motion_score = 0.0
            scene_delta = 0.0
            flash_delta = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion_score = float(np.mean(diff)) / 255.0
                # Highlight sudden local peaks (explosions / fast action)
                high_motion_ratio = float(np.mean(diff > 28))
                motion_score = min(1.0, motion_score * 2.5 + high_motion_ratio * 1.4)
            if prev_hist is not None:
                corr = cv2.compareHist(hist, prev_hist, cv2.HISTCMP_CORREL)
                scene_delta = float(np.clip(1.0 - corr, 0.0, 1.0))
            if prev_mean_luma is not None:
                flash_delta = float(np.clip(abs(luma - prev_mean_luma) / 45.0, 0.0, 1.0))

            face_score = 0.0
            faces = face_detector.detect_faces(small)
            if len(faces) > 0:
                # Largest detected face
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + w * 0.5) / 320.0
                cy = (y + h * 0.5) / 180.0
                face_centers.append((t_sec, cx, cy))
                face_area = (w * h) / (320.0 * 180.0)
                face_score = float(np.clip(face_area * 5.0, 0.15, 0.8))

            raw = 0.48 * motion_score + 0.24 * scene_delta + 0.16 * flash_delta + 0.12 * face_score
            sample_times.append(t_sec)
            sample_scores.append(float(np.clip(raw * 100.0, 0.0, 100.0)))

            prev_gray = gray
            prev_hist = hist
            prev_mean_luma = luma

        frame_idx += 1

    cap.release()

    if not sample_times:
        t = np.array([0.0], dtype=np.float32)
        return VisualAnalysisResult(duration, t, np.zeros(1, dtype=np.float32), [])

    duration = max(duration, sample_times[-1])
    num_bins = max(1, int(np.ceil(duration / bin_sec)))
    times = np.arange(num_bins, dtype=np.float32) * bin_sec
    curve = np.zeros(num_bins, dtype=np.float32)
    s_times = np.array(sample_times)
    s_scores = np.array(sample_scores)
    for idx, t0 in enumerate(times):
        mask = (s_times >= t0) & (s_times < t0 + bin_sec)
        if np.any(mask):
            curve[idx] = float(np.max(s_scores[mask]))

    # Robust contrast normalization so calm videos don't flatline and chaotic videos still differentiate peaks
    if len(curve) > 3 and np.max(curve) > 0:
        p95 = float(np.percentile(curve, 95)) + 1e-5
        curve = np.clip((curve / max(p95, 25.0)) * 85.0, 0.0, 100.0)

    return VisualAnalysisResult(
        duration=duration,
        timeline_times=times,
        action_curve=curve.astype(np.float32),
        face_centers=face_centers,
    )
