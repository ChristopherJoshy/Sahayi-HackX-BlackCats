# Request 015 — Guarantee a spoken opening line (fix "AI not talking")

## Problem
After recent changes the companion could go silent at call start: if the
opening `orchestrator.handle_turn(is_opening=True)` raised (e.g. safety-agent
or companion-agent hiccup) or returned an empty reply, `process_audio_turn`
produced no audio and the patient heard dead air. Because the exception was
swallowed by the existing `except Exception`, the failure was invisible.

## Root-cause verification
Reproduced the opening branch in isolation with a mock orchestrator that
returns empty text: before the fix the turn yielded 0 media events; after the
fix it falls back to a deterministic warm opener and yields 32 media events.

## Change
`voice/twilio_handler.py` — `process_audio_turn` opening branch:

- Wrap `orchestrator.handle_turn` in try/except; on failure log and continue
  with an empty reply instead of aborting the turn.
- If the model reply is empty (or TTS returns nothing), synthesize a
  deterministic, language-correct opener via new `_fallback_opener()` helper so
  the patient ALWAYS hears a voice at call start.
- Added last-resort: if TTS still returns nothing for the patient language, try
  the Malayalam default opener (most likely to render).

The echo/loop guard and the rest of the pipeline are unchanged.

## Verification
- `import main` -> IMPORT_OK.
- Unit-style check: opening turn with empty model reply now yields audio.
- NOTE: "call ends instantly" is most likely environmental (dead ngrok tunnel
  or wrong `WEBSOCKET_BASE`/`TWILIO_WEBHOOK_BASE` in `.env`). Confirm the
  tunnel URL in `.env` matches where uvicorn is reachable and that
  `/ws/voice/{session_id}` is publicly reachable.
