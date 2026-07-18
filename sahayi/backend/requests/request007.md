# Request 007 — Dynamic language prompts + Firebase removal

## Changes

### Dynamic language (LLM reply in user's language)
- `agents/whatsapp_agent.py`: system prompt now says "Reply in the same language
  and script the user writes or speaks in." No more hardcoded Malayalam.
- `agents/main_companion.py`: same dynamic approach.
- `voice/twilio_handler.py`: greeting dict (9 languages), repeat-prompt dict (5),
  TTS uses `reply_language` from patient record.

### Firebase removed (MVP)
- `core/security.py`: rewritten — shared-token auth via `DASHBOARD_SHARED_TOKEN`.
  No Firebase import, no `firebase_admin` dependency.
- `core/config.py`: removed `firebase_project_id`, `service_account_file` fields,
  `_discover_service_account_file`, `_resolve_backend_path`.
- `core/bootstrap.py`: removed `firebase` from health snapshot.
- `requirements.txt`: removed `firebase-admin`.
- `api/routes_*.py`: updated docstrings ("Verified Firebase doctor payload" →
  "Verified doctor payload (shared-token auth)").
- `.env.example` / `.env`: removed Firebase vars, removed VERTEX AI vars.
- `AGENTS.md` / `README.md`: updated to reflect provider stack (Sarvam + Gemini
  vision + Twilio, shared-token auth, no Firebase).

## Verification
- `python -m py_compile` on all `.py` files: ALL COMPILED OK.
- No remaining `firebase_admin` imports outside docstrings.
