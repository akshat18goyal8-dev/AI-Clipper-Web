"""Integration tests for AI Clipper 2.0 Web FastAPI backend."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from clipper_engine import detect_hardware


def _make_test_mp4(path: Path) -> Path:
    hw = detect_hardware(prefer_gpu=False)
    res = subprocess.run(
        [
            hw.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=24:duration=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=10",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, res.stderr
    return path


def test_web_auth_upload_edit_and_export(tmp_path: Path):
    client = TestClient(app)

    # 1. Health check
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"

    # 2. Register + Login
    email = f"creator_{int(time.time() * 1000)}@example.com"
    reg = client.post("/api/auth/register", json={"email": email, "full_name": "Test Creator", "password": "secret123"})
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Upload video & wait for background AI pipeline
    mp4 = _make_test_mp4(tmp_path / "web_sample.mp4")
    with mp4.open("rb") as f:
        up = client.post(
            "/api/projects/upload",
            headers=headers,
            files={"file": ("web_sample.mp4", f, "video/mp4")},
            data={
                "category": "Gaming",
                "preset": "Gaming Viral Style",
                "intensity": "HIGH ENERGY",
                "preferred_duration": "10",
                "max_clips": "1",
            },
        )
    assert up.status_code == 200
    project_id = up.json()["project_id"]

    status_data = None
    for _ in range(90):
        r = client.get(f"/api/projects/{project_id}", headers=headers)
        assert r.status_code == 200
        status_data = r.json()
        if status_data["status"] in ("completed", "failed"):
            break
        time.sleep(1.0)
    assert status_data and status_data["status"] == "completed", status_data

    # 4. List clips & update timeline in Clip Editor
    clips = client.get("/api/clips", headers=headers).json()
    assert len(clips) >= 1
    clip = clips[0]
    cid = clip["clip_id"]
    tl = clip["timeline"]
    tl["hook_text"] = "EDITED HOOK!"
    tl["outro_text"] = "SUBSCRIBE!"

    put_res = client.put(f"/api/clips/{cid}/timeline", headers=headers, json=tl)
    assert put_res.status_code == 200

    ren_res = client.post(f"/api/clips/{cid}/render", headers=headers)
    assert ren_res.status_code == 200
    assert ren_res.json()["width"] == 1080
    assert ren_res.json()["height"] == 1920

    # 5. Stream rendered video & batch export ZIP
    vid_res = client.get(f"/api/clips/{cid}/video?token={token}")
    assert vid_res.status_code == 200
    assert len(vid_res.content) > 10000

    zip_res = client.post("/api/clips/batch-export", headers=headers, json={"clip_ids": [cid]})
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"
