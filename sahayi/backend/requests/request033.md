# Request 033 - Fix silent mid-call TTS timeout dropping turns

## Goal

A production voice log showed the companion's medicine answer (151 chars) never
reached the patient: the Sarvam TTS call timed out at the hard 5s cap, returned
empty audio, and `twilio_handler` had no fallback for a mid-call TTS failure —
so the turn was silently dropped and the conversation degenerated into a vague
pivot ("അതെ അതെ" -> "പിന്നെ എന്തെങ്കിലും വിശേഷങ്ങൾ?").

## Changes

- `core/config.py`: removed the hard `min(..., 5.0)` ceiling on timeouts. TTS
  default raised to 12s (long medicine lists need more synth time); STT default
  8s. Both remain env-overridable (`TTS_TIMEOUT`, `STT_TIMEOUT`).
- `voice/twilio_handler.py`: added `_synthesize_with_fallback()` which retries
  once with a sentence-boundary-trimmed reply when TTS returns nothing, plus a
  last-resort "please repeat" prompt if TTS fails entirely — the call never goes
  silent mid-conversation now. Added helpers `_trim_to_sentence()` and
  `_repeat_prompt()`.

## Validation

- Syntax check passed; existing humanlike suite (13 tests) still passes.
- Manual: a long reply that exceeds the TTS window should now play the trimmed
  portion and/or ask the patient to repeat, instead of silence.
