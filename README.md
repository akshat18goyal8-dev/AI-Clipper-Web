# AI Clipper 2.0 — Web Studio

A full-stack commercial web application powered by **Next.js (TypeScript + Tailwind CSS)**, **Python FastAPI**, **SQLAlchemy (PostgreSQL / SQLite)**, **Redis + background job workers**, **FFmpeg**, **OpenCV**, and **faster-whisper**.

---

## Core Features

- **Modern Dark SaaS Studio**: Responsive sidebar web UI (`Dashboard`, `New Project`, `Live Stream Monitor`, `My Clips`, `Clip Editor`, `Export History`, `Settings`) with JWT + bcrypt user authentication.
- **Server-Side AI Video Processing**:
  - Upload videos from your computer (`multipart/form-data`).
  - Process supported YouTube, Twitch VODs, and direct video URLs.
  - Real-time job progress via REST polling & WebSockets (`/ws/jobs/{project_id}`).
- **Live Stream Intelligence Monitor**:
  - Connect Twitch, YouTube Live, or HLS `.m3u8` streams with configurable rolling buffer (`40–300s`) and trigger sensitivity.
  - Live telemetry meters for Audio Excitement, Visual Action, Live Chat Surge, and Combined Highlight Score.
- **Professional AI Video Editing Engine**:
  - 7 Editing Presets × 4 AI Editing Intensities (`MINIMAL`, `MODERATE`, `HIGH ENERGY`, `VIRAL STYLE`).
  - Automatic 9:16 vertical reframing (`1080×1920`) with smart subject tracking, blurred ambient fill, or gaming split focus.
  - Dynamic word-by-word animated ASS captions (English & Hindi), context-aware opening hooks, smart zooms, noise-reduced voice normalization, SFX, and auto-ducked background music.
- **Interactive Web Clip Editor**:
  - HTML5 vertical video preview, timeline trim start/end, split half, duration presets (`10s`–`60s`), crop X/Y pan sliders, editable caption cue list & typography controls, hook/intro/outro editors, audio volume sliders, Undo/Redo stack, Apply & Preview Render, and Batch ZIP Export.

---

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** and `npm`
- **FFmpeg & FFprobe** installed on system `PATH`
- Optional for production scale: **PostgreSQL 16** and **Redis 7** (or Docker + Docker Compose). *For local development without Docker, the backend automatically uses local SQLite + in-process ThreadPoolExecutor fallback.*

---

## Local Development Setup

### 1. Backend (FastAPI + AI Engine)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Run backend tests:
```powershell
$env:PYTHONPATH="."
pytest -v tests
```

### 2. Frontend (Next.js + Tailwind CSS)

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser, create an account, and start generating AI-edited vertical clips.

---

## Production Deployment (Docker Compose)

1. Copy `.env.example` to `.env` and set strong secrets (`JWT_SECRET_KEY`, database credentials, optional `YOUTUBE_API_KEY` / `TWITCH_OAUTH_TOKEN`).
2. Launch the full stack (PostgreSQL + Redis + FastAPI + Next.js):
   ```bash
   docker compose up --build -d
   ```

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete API, database, background job, and AI pipeline specification.

---

## License

Licensed under the [MIT License](LICENSE).
