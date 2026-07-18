# Request 003 — Route agent LLM text through Sarvam via OpenAI SDK

## Change
- `core/ai.py`: `OpenAIClient` is now provider-aware. When `SARVAM_LLM_MODEL` is
  set it targets Sarvam's OpenAI-compatible endpoint (`https://api.sarvam.ai/v1`)
  with auth via the `api-subscription-key` header; otherwise it uses OpenAI.
- `core/config.py`: added `sarvam_llm_model` setting (env `SARVAM_LLM_MODEL`).
- `sahayi/backend/.env.example`: added `SARVAM_LLM_MODEL=sarvam-30b`, clarified
  OpenAI is vision-only.
- `README.md`: updated provider description (Sarvam text LLM + STT/TTS; OpenAI vision only).
- `voice/vision.py` stays on OpenAI (Sarvam has no vision/image input).
- `agents/whatsapp_agent.py` stays on OpenAI (it mixes prescription images with text).

## Rationale
Sarvam offers cheaper, Indic-native LLMs (sarvam-30b/105b/m) over an OpenAI-compatible
API, so a single `openai` SDK path serves both providers. Vision must remain OpenAI.

## Verification
- `python -m py_compile` on `core/ai.py`, `core/config.py`, `core/bootstrap.py`,
  `agents/whatsapp_agent.py`, `voice/vision.py`: OK.
