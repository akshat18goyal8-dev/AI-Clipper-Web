# Architecture — AI Clipper 2.0 Web Studio

## System Components

```
AI-Clipper-Web/
├── backend/
│   ├── app/
│   │   ├── config.py        # Env config (PostgreSQL/SQLite, Redis, JWT, CORS)
│   │   ├── db.py            # SQLAlchemy ORM (User, UserSettings, Project, Clip, ExportRecord)
│   │   ├── auth.py          # JWT bearer auth + bcrypt password hashing
│   │   ├── tasks.py         # JobBroker (ThreadPoolExecutor + Redis telemetry + LiveMonitor)
│   │   └── main.py          # FastAPI REST + WebSocket endpoints + ZIP batch export
│   ├── clipper_engine/      # Shared AI video analysis, reframing, caption & render engine
│   ├── tests/               # End-to-end FastAPI TestClient integration tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── lib/api.ts       # Typed REST client & token storage
│   │   ├── components/
│   │   │   └── ClipEditor.tsx # Interactive web Clip Editor with Undo/Redo & re-render
│   │   └── app/
│   │       ├── layout.tsx
│   │       ├── globals.css
│   │       └── page.tsx     # Auth + 7-view Studio Dashboard
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml       # PostgreSQL + Redis + FastAPI + Next.js
└── .env.example
```

## Key API Endpoints

- `GET /api/health` — Hardware capabilities, Redis connectivity, presets/categories/tracks.
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` — User accounts & JWT issuance.
- `POST /api/projects/upload`, `POST /api/projects/url` — File upload & URL ingestion jobs.
- `GET /api/projects/{id}`, `WS /ws/jobs/{id}` — Real-time job progress tracking.
- `POST /api/live/start`, `POST /api/live/stop`, `GET /api/live/status` — Live stream rolling buffer monitor.
- `GET /api/clips`, `PUT /api/clips/{id}/timeline`, `POST /api/clips/{id}/render`, `POST /api/clips/batch-export` — Clip inspection, editing, server-side re-rendering, and ZIP export.
- `GET /api/exports`, `GET/PUT /api/settings` — Export audit log & per-user AI/credential settings.
