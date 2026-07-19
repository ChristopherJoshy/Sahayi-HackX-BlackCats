# Request 032 - Human-like, listener-first companion

## Goal

The companion sounded robotic: it echoed the patient's own words, repeated
questions, and looped instead of holding a natural conversation. The biggest
driver was a starved token budget — Sarvam's reasoning model spends `max_tokens`
on internal reasoning before emitting the reply, so the old 120/160 cap returned
empty or truncated text (`finish_reason="length"`).

## Changes

- Raised the companion `max_tokens` to 8094 so the model emits a full reply
  (per the reasoning-budget note in `core/ai.py`).
- Improved `_limit_voice_reply`: cap raised to ~200 chars and it now prefers
  cutting at a sentence boundary (`।` / `.` / `?` / newline) so TTS plays a
  complete thought rather than a chopped fragment.
- Rewrote the system prompt:
  - Listener-first: react to the patient's MEANING and continue; never make the
    reply a repetition of their own sentence; never re-ask an answered question.
  - Added a `CONVERSATION FLOW` section: keep the chat alive like a caring
    relative, gently pivot to a NEW lighter subject when the talk stalls.
  - Added a `WINDING DOWN` section: after ~turn 6 or when the patient sounds
    done, warmly close instead of looping.
  - Added a `CONVERSATION STEER` slot for loop-detection directives.
- Orchestrator now injects a gentle steer into the companion when a loop is
  detected (instead of only logging), telling it to pivot to a fresh topic.

## Guardrails

- SafetyAgent heuristic (diagnosis / stop-medicine / impersonation) unchanged.
- Medicines still only read back from doctor-set `patient_facts`.

## Validation

- `python -m pytest tests` (or the standalone `test_*.py` scripts) from
  `sahayi/backend/`. New cases: no-echo, wind-down, stall-pivot, plus the
  existing humanlike suite.
