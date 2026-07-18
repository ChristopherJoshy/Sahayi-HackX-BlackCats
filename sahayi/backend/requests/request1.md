# Request 1: Humanize Voice AI and Reduce Latency

## Goal
Transform Sahayi from a noticeably-AI voice assistant into a deeply human, warm, fast, and reliable phone companion for elderly patients in rural Kerala.

## Changes

1. **Voice Pipeline & VAD**:
   - Lowered VAD silence threshold from 0.5 to 0.35 in `vad.py` to prevent cutting off slow-speaking elderly patients.
   - Reduced trailing silence margin in `twilio_handler.py` and implemented dynamic echo trimming.
   - Introduced `thinking_sounds.py` to play natural human filler sounds (e.g., "hmm", "ആ...") immediately after VAD triggers, eliminating dead silence during STT/LLM processing.

2. **Sarvam AI Optimizations**:
   - Switched STT `mode` to `codemix` in `sarvam_stt.py` to better handle Manglish/Hinglish.
   - Added `speed` parameter to `sarvam_tts.py` to allow slower, more natural speech pacing for elderly users (default 0.92x).
   - Increased API timeouts (7s STT, 8s TTS) to prevent silent failures under load.

3. **Orchestrator & Safety**:
   - Removed the blocking `SafetyAgent` LLM call from the hot path in `orchestrator.py`. Real-time safety now relies on a fast heuristic, saving 1-3 seconds of latency per turn.
   - Made the `SafetyAgent` heuristic fallback language-aware so Malayalam users don't get English errors.
   - Added AI loop detection in `orchestrator.py` to prevent the agent from asking the same question repeatedly.

4. **Main Companion & Memory**:
   - Increased the companion LLM temperature from 0.1 to 0.55 in `ai.py` (and `main_companion.py`) for more natural variation.
   - Enriched the system prompt with explicit instructions to use human filler words and mirror emotional tone.
   - Increased the `MemoryManager` note limit from 5 to 15 to improve long-term recall.

5. **Configuration**:
   - Added new settings in `config.py` for TTS speed, timeouts, and VAD thresholds.
