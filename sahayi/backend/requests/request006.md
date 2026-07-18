# Request 006 — Auto-detect spoken language for Sarvam STT/TTS

## Change
- `voice/sarvam_stt.py`: `transcribe` / `transcribe_file` now default
  `language_code="auto"` (Saaras v3 auto-detection). Response normalized to also
  return the detected `language` (e.g. `ml-IN`, `ta-IN`).
- `voice/sarvam_tts.py`: `synthesize` accepts an optional `language_code`;
  defaults to `SARVAM_LANGUAGE` when omitted.
- `voice/twilio_handler.py`: STT uses `auto`; detected language recorded on
  `VoiceSessionState.language` for observability. TTS reply uses the patient's
  configured language (assistant always replies in Malayalam).
- `agents/whatsapp_agent.py`: audio messages use `language_code="auto"` and the
  detected language is passed to TTS for the audio reply.
- `.env.example`: noted `SARVAM_LANGUAGE` is the default/fallback; STT auto-detects.

## Rationale
Let the system adapt to whatever language the patient speaks (Saaras supports 22
Indian languages). STT auto-detects for accuracy; the assistant still replies in
the patient's language (Malayalam default) so TTS output stays natural.

## Verification
- `python -m py_compile` on `voice/sarvam_stt.py`, `voice/sarvam_tts.py`,
  `voice/twilio_handler.py`, `agents/whatsapp_agent.py`: OK.
