"""Cross-version face & subject salience detector (OpenCV 4.x Haar, OpenCV 5.x YuNet, and offline salience fallback)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


class SubjectFaceDetector:
    """Detects faces or primary subject bounding boxes across OpenCV 4.x and 5.x."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self._haar = None
        self._yunet = None
        self._yunet_input_size: Tuple[int, int] = (320, 180)

        # 1. OpenCV 4.x Haar cascade if available
        if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
            xml = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            if xml.exists():
                self._haar = cv2.CascadeClassifier(str(xml))

        # 2. OpenCV 5.x FaceDetectorYN (YuNet) if ONNX model exists locally
        if self._haar is None and hasattr(cv2, "FaceDetectorYN"):
            model_dir = cache_dir or (Path.home() / ".cache" / "ai_clipper_models")
            model_path = model_dir / "face_detection_yunet_2023mar.onnx"
            if not model_path.exists():
                try:
                    import httpx

                    model_dir.mkdir(parents=True, exist_ok=True)
                    url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
                    resp = httpx.get(url, follow_redirects=True, timeout=6.0)
                    if resp.status_code == 200 and len(resp.content) > 50000:
                        model_path.write_bytes(resp.content)
                except Exception:
                    pass
            if model_path.exists():
                try:
                    self._yunet = cv2.FaceDetectorYN.create(
                        str(model_path), "", self._yunet_input_size, 0.72, 0.3, 5000
                    )
                except Exception:
                    self._yunet = None

    def detect_faces(self, bgr_frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Return list of (x, y, w, h) face bounding boxes in frame coordinates."""
        h, w = bgr_frame.shape[:2]
        if self._haar is not None:
            gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
            faces = self._haar.detectMultiScale(gray, scaleFactor=1.18, minNeighbors=4, minSize=(22, 22))
            return [(int(x), int(y), int(fw), int(fh)) for (x, y, fw, fh) in faces]

        if self._yunet is not None:
            if (w, h) != self._yunet_input_size:
                self._yunet.setInputSize((w, h))
                self._yunet_input_size = (w, h)
            _, faces = self._yunet.detect(bgr_frame)
            if faces is not None and len(faces) > 0:
                out: List[Tuple[int, int, int, int]] = []
                for f in faces:
                    fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                    if fw > 8 and fh > 8:
                        out.append((max(0, fx), max(0, fy), fw, fh))
                return out

        # 3. Offline YCrCb skin-region + structural contrast fallback
        ycrcb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycrcb, np.array([40, 133, 77]), np.array([245, 173, 127]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes: List[Tuple[int, int, int, int]] = []
        min_area = (w * h) * 0.01
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= min_area:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                if 0.5 <= (bw / max(1.0, float(bh))) <= 1.8:
                    boxes.append((bx, by, bw, bh))
        return boxes
