# SAHAYI

**SAHAYI** is an AI-assisted remote patient monitoring platform for rural Kerala.
A multi-agent backend (FastAPI + Sarvam AI + Gemini Vision) conducts voice
check-ins with patients over Twilio, surfaces risk and anomalies to doctors on a
real-time dashboard, and backs every doctor-facing summary with cited RAG / PubMed
evidence. Built for **HackX** by team *Black Cats*.

## How it works

- **Voice loop** — Patients call in; Sarvam STT auto-detects their language (22
  Indian languages), the Indic LLM reasons over the patient record and replies in
  the same language, and TTS reads the response back. No audio is stored, only
  transcribed text.
- **Agents** — Each capability (safety, population intelligence, hypothesis,
  research, etc.) is one agent file under `agents/`. Agents never call each other
  directly; the orchestrator routes between them. The **Safety Agent runs before
  every patient-facing response**.
- **Dashboard** — Doctors see live patients, risk feeds, a knowledge graph, and
  hypothesis/research panels via a WebSocket connection.

## Repository layout

```
sahayi/
  backend/        FastAPI service (Python)
    main.py       App entrypoint, scheduler, routers
    api/          Route modules (voice, dashboard, patients)
    agents/       One file per agent
    intelligence/ All business logic
    db/           db/database.py is the ONLY DB access point
    rag/          Vector store + PubMed client
    voice/        Twilio / STT / TTS
    contracts/    Pydantic models
    seed.py       Loads demo patient (Thankamma)
    tests         test_*.py standalone scripts
  frontend/       Vite + React app
    src/pages/      Screens
    src/components/ UI
    src/hooks/      Stateful logic
    src/api/        Backend calls
    src/auth/       Firebase auth
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- API keys for **Sarvam AI** (text LLM + Malayalam STT/TTS), **Gemini** (cheap vision only), and **Twilio**

## Backend setup

```powershell
cd sahayi/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env        # then fill in your keys
python seed.py              # creates + seeds sahayi.db
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Verify it is up:

```
GET http://127.0.0.1:8000/health
```

Useful scripts:
- `python seed.py` — create the DB and load the demo patient.
- `python reset_db.py` / `python fix_db.py` — manage the local SQLite DB.
- `python test_api.py` (also `test_fastapi.py`, `test_payload.py`,
  `test_empty_payload.py`, `test_fastapi_override.py`) — run from `sahayi/backend/`.

## Frontend setup

```powershell
cd sahayi/frontend
npm install
cp .env.example .env        # set VITE_API_BASE_URL / VITE_WS_URL to your backend
npm run dev
```

Build (minimum pre-merge sanity check): `npm run build`.

## Configuration

Copy `.env.example` in **both** `sahayi/backend/` and `sahayi/frontend/`. Never
commit `.env`. The backend `.env.example` documents every variable: Sarvam text
LLM + STT/TTS (`SARVAM_LLM_MODEL`, e.g. `sarvam-30b`; STT auto-detects the
spoken language), Gemini key for **cheap vision only** (`GEMINI_VISION_MODEL`,
e.g. `gemini-2.0-flash-lite`; Sarvam has no vision), Twilio numbers + webhook
base (ngrok during dev), SQLite `DATABASE_URL`, Chroma persistence, and
risk-scoring thresholds. Auth is shared-token based (`DASHBOARD_SHARED_TOKEN`);
no Firebase in MVP.

## Hard rules (for contributors)

See `AGENTS.md` and `sahayi/backend/rules.md`. The non-negotiables:

- Agents never call each other directly — only via the orchestrator.
- All business logic in `intelligence/`; all DB access through `db/database.py`.
- Safety Agent runs before every patient-facing response.
- Doctor summaries are **observational, never diagnostic**; risk scores must show
  the formula; RAG / PubMed results must be cited.
- When editing the backend, create `requests/request{id}.md` (increment `id`) and
  commit it (per `GEMINI.md`).
