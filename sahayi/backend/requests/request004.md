# Request 004 — Finalize best Sarvam models for STT/TTS/LLM

## Change
- LLM: `SARVAM_LLM_MODEL=sarvam-30b` (fastest + cheapest Indic LLM, fully implemented — no mock).
- STT: `saaras:v3` (current SOTA, 22 languages, <150ms) — already set.
- TTS: `bulbul:v3` (latest, best naturalness, Malayalam supported) — already set.
- `agents/whatsapp_agent.py`: text replies now route through the shared
  `OpenAIClient` (→ Sarvam `sarvam-30b`). Only prescription-image messages use
  OpenAI vision (Sarvam has no image input). This makes ALL text reasoning Sarvam.
- `.env.example` comments updated to reflect full Sarvam text routing.

## Model rationale (researched)
- sarvam-30b: ₹2.5/1M in, ₹10/1M out — cheapest, fastest, Indic-native.
- saaras:v3: recommended STT, 22 languages, streaming, code-mix robust.
- bulbul:v3: best TTS naturalness study (11 langs incl. ml-IN).
- Vision stays OpenAI (gpt-4o-mini) — Sarvam Vision is document-OCR only, not
  general multimodal chat.

## Verification
- `python -m py_compile` on `core/ai.py`, `core/config.py`, `agents/whatsapp_agent.py`,
  `voice/vision.py`: OK.
