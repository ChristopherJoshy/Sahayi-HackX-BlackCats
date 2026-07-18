# Repository Guidelines

## Project Structure
Application code lives under `sahayi/`. `sahayi/backend/` is a FastAPI service; `sahayi/frontend/` is a Vite + React app.

Backend layout (import paths matter — run from `sahayi/backend/` so `from api...`, `from agents...` resolve):
- `main.py` — entrypoint. Bootstraps services, starts APScheduler jobs (6h population, 10m overdue-summary), mounts routers (`voice`, `dashboard`, `patients`). Run with `uvicorn main:app`.
- `api/` — route modules only. `agents/` — one file per agent; `intelligence/` — all business logic; `db/database.py` — the only DB access point; `rag/` — vector store; `voice/` — Twilio/STT/TTS; `contracts/` — Pydantic models.
- `seed.py` loads demo data; `reset_db.py` / `fix_db.py` manage the SQLite DB (`sahayi.db`, git-ignored).
- `rules.md` is the authoritative backend rulebook. `GEMINI.md` adds the backend edit workflow.

Frontend layout: `src/pages/` screens, `src/components/` UI, `src/hooks/` stateful logic, `src/api/` backend calls, `src/styles/` Tailwind.

## Build, Test & Dev Commands
Backend (from `sahayi/backend/`):
- `python -m venv .venv` → `.\.venv\Scripts\Activate.ps1` → `pip install -r requirements.txt`
- `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- `python seed.py` to load the demo patient. Health check: `GET /health`.
- Tests are standalone scripts in `sahayi/backend/`: `python test_api.py`, `test_fastapi.py`, `test_payload.py`, `test_empty_payload.py`, `test_fastapi_override.py`. Run from `sahayi/backend/` (they import `from main import app`).

Frontend (from `sahayi/frontend/`): `npm install`, `npm run dev`, `npm run build`, `npm run preview`. `npm run build` is the minimum pre-merge sanity check.

## Environment
Both apps need a `.env` (never committed). Copy from `.env.example` in each dir. Backend requires API keys for Sarvam (LLM + STT/TTS), Gemini (vision only), Twilio; `DATABASE_URL` defaults to local SQLite. Auth is shared-token based (no Firebase). Frontend reads `VITE_API_BASE_URL` / `VITE_WS_URL` (currently hardcoded to an ngrok tunnel in the example — update to your backend).

## Hard Rules (from rules.md — non-negotiable)
- Agents live one-per-file in `agents/`; they never call each other directly — only via the orchestrator.
- All business logic in `intelligence/`; all DB access through `db/database.py` (never direct).
- Safety Agent must run before EVERY patient-facing response.
- Voice: STT/TTS calls get a 5s timeout with graceful failure; if STT confidence < 0.6, ask the patient to repeat. No audio is ever stored — only transcribed text.
- Doctor-facing summaries are observational, never diagnostic; risk scores must include the formula breakdown; PubMed/RAG results must be cited.
- Every function needs a docstring with args + returns + agent ownership; every agent file needs its header block.

## Backend Edit Workflow (from GEMINI.md)
When editing the backend, create `requests/request{id}.md` (increment `id` each time) describing the change, and commit these request files to git.

## Coding Style
Python: 4-space indent, snake_case, type hints, layered separation (routes / logic / db). React: 2-space indent, semicolons, double quotes, PascalCase components (`PatientCard.jsx`), camelCase hooks (`usePatientData.js`).

## Security
Do not commit `.env`, Firebase service-account JSON, SQLite DBs, `.venv/`, `node_modules/`, or lockfiles (all git-ignored). Keep real credentials local; start from `.env.example`.

## Providers
- **Sarvam AI**: text LLM (`sarvam-30b`, OpenAI-compatible via OpenAI SDK), STT (`saaras:v3`, auto-detects language), TTS (`bulbul:v3`). Auth: `api-subscription-key` header.
- **Gemini**: vision only (`gemini-2.0-flash-lite`), used for prescription image extraction. Auth: API key via `google-genai`.
- **Twilio**: voice/WhatsApp telephony.
- Auth: shared-token based (`DASHBOARD_SHARED_TOKEN`); no Firebase in MVP.
