# Request 002 — Swap Gemini for OpenAI (LLM + vision)

## Change
- Replaced Google Gemini with OpenAI as the single LLM/vision provider.
- `core/ai.py`: `GeminiClient` (google-genai) → `OpenAIClient` (openai SDK), keeping the `ask_text` / `ask_json` / `ThinkingLevel` interface so the 6 agents are unchanged beyond the import.
- `agents/whatsapp_agent.py`: Gemini `generate_content` → OpenAI chat completions (text + image_url multimodal).
- `voice/vision.py`: Gemini Vision → OpenAI vision (`gpt-4o-mini`) for prescription extraction.
- `core/config.py`: swapped `gemini_api_key` / `gemini_model` / Vertex fields for `openai_api_key` / `openai_model`.
- `core/bootstrap.py`: health service `gemini` → `openai`.
- `requirements.txt`: dropped `google-genai`, added `openai>=1.40,<2`.
- `.env.example` + README updated. Sarvam stays for Malayalam STT/TTS (per decision).

## Rationale
Use one cheap provider (OpenAI `gpt-4o-mini`, ~$0.15/$0.60 per 1M tok, supports vision + function calling) for all reasoning/vision tasks.

## Verification
- `pip install "openai>=1.40,<2"` succeeded (openai-1.109.1).
- `python -m py_compile` on all touched modules: OK.
- `importlib` spec check for `openai`, `core.ai`, `voice.vision`, `agents.whatsapp_agent`: all resolve.

## Follow-up (Request 003)
Sarvam's OpenAI-compatible endpoint (`https://api.sarvam.ai/v1`) now backs all
agent text reasoning when `SARVAM_LLM_MODEL` is set. `core/ai.py` OpenAIClient is
provider-aware (Sarvam auth via `api-subscription-key` header). Vision stays on
OpenAI (`voice/vision.py`) since Sarvam has no image input. WhatsApp agent keeps
OpenAI (it mixes prescription images). Config + `.env.example` + README updated.
