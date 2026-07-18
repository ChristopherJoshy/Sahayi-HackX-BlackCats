# Request 013 — STT, TTS, and VAD latency & echo optimizations

## Context
Patients managing health at home were experiencing high latency on voice calls (~4-5s wait per turn). Additionally, the agent would occasionally fail to hear the patient or timing issues occurred due to the previous response's echo.

Two main culprits were identified:
1. **Synchronous thread pools & no connection pooling:** The `sarvamai` Python SDK runs synchronous client calls mapped via `asyncio.to_thread`. Every call established a fresh connection to Sarvam, introducing DNS, TCP, and TLS handshake overhead on every speech turn.
2. **Echo buffer leak:** While VAD's PCM buffer was cleared when a response finished playing, the raw `state.buffer` (containing the mu-law audio sent to STT) was not cleared. Thus, the echo of the assistant's previous response was sent to the STT API along with the patient's voice, degrading accuracy and increasing API payload sizes (causing timeouts).
3. **Slow decoding:** `mulaw_to_pcm16` used a single-byte loop in Python using `struct.pack`, blocking the event loop and consuming unnecessary CPU time.
4. **Large tail margin:** `_RESPONSE_TAIL_MARGIN_SECONDS` was set to `1.2` seconds, making the system deaf to immediately following speech and adding a noticeable lag.

## Changes
1. **Audio Codec** — `voice/audio_codec.py`:
   - Replaced the single-byte loop in `mulaw_to_pcm16` with native C-speed decoding via `audioop.ulaw2lin` (~450x faster).
   - Added a precomputed lookup table of size 256 as a safe fallback when `audioop` is not available (for future Python 3.13 compatibility).
2. **Lifespan HTTP Client** — `main.py`:
   - Instantiated a shared, persistent `httpx.AsyncClient(timeout=5.0)` in FastAPI lifespan as `app.state.http_client`.
   - Guaranteed clean resources cleanup by calling `await app.state.http_client.aclose()` on teardown.
3. **Pipeline Construction** — `core/bootstrap.py`:
   - Passed `app.state.http_client` to `TwilioVoiceHandler` and `WhatsAppAgent` constructors.
4. **WhatsApp Agent** — `agents/whatsapp_agent.py`:
   - Updated constructor to accept the `http_client` parameter and pass it to `SarvamSTTClient` and `SarvamTTSClient`.
5. **STT Client** — `voice/sarvam_stt.py`:
   - Refactored `SarvamSTTClient` to accept an optional `http_client`.
   - Switched both `transcribe` and `transcribe_file` from synchronous SDK to direct async HTTP calls via the shared client (or a local instance) to `https://api.sarvam.ai/speech-to-text`.
   - Enforced the voice rules' strict **5.0-second timeout** (previously 10.0 seconds) and handled timeouts gracefully.
6. **TTS Client** — `voice/sarvam_tts.py`:
   - Refactored `SarvamTTSClient` to accept an optional `http_client`.
   - Switched `synthesize` from synchronous SDK to direct async HTTP calls to `https://api.sarvam.ai/text-to-speech`.
   - Enforced the voice rules' strict **5.0-second timeout** (previously 10.0 seconds).
7. **Twilio Voice Handler** — `voice/twilio_handler.py`:
   - Accepted `http_client` in `__init__` and forwarded to voice clients.
   - Cleared `state.buffer` in addition to `state.pcm_buffer` inside `_accumulate_audio` when the playback window opens, dropping all echo.
   - Reduced `_RESPONSE_TAIL_MARGIN_SECONDS` to `0.4` seconds to allow snappier, more natural patient turn-taking.

## Verification
- Verified all touched modules compile cleanly (`import main` -> `IMPORT_OK`).
- Ran performance test comparing direct HTTP and connection reuse (latency reduced from 2.3s to 0.9s for TTS, and 0.5s to 0.3s for STT).
- Ran LLM health check (`python check_sarvam.py`).

## Status
Done.
