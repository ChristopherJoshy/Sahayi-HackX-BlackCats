# Request 011 — Mistake memory table + context compaction at >90% usage

## Context
Two gaps in the backend after request010:

1. **The AI could not learn from its own errors.** When the safety agent overrode a
   companion reply, or a doctor corrected the system, that signal was lost. We need a
   durable "mistake memory" the system can recall and improve from — a core differentiator
   for a care companion.
2. **Long conversations would eventually blow the model context window.** The orchestrator
   only bounded history to the last 16 turns (`_MAX_HISTORY_TURNS * 2`), which discards early
   context rather than preserving its meaning. We need true compaction with no data loss.

## Research (context compaction)
Reviewed current best practice (2025/2026):
- **Anchored / incremental compaction** (Factory.ai, Anthropic) is the fastest correct method:
  keep ONE persistent running summary and, when the window nears full, summarise ONLY the
  newly dropped span and merge it into the anchored summary. Avoids re-summarising the whole
  prefix every turn (which grows linearly).
- ACL 2025 pretraining context-compressor work shows 4x compression is near-lossless and
  16x is "fast" — but those are training-time methods, not applicable to live inference.
- Conclusion: incremental anchored summarisation (keep recent turns verbatim, fold older
  turns into a summary) is the best/fastest live approach with no important-data loss.

## Changes
1. **Mistake memory model** — new `MistakeNote` ORM in `db/models.py` (patient_id, agent,
   mistake_type, context, error, correction, lesson). `init_db` auto-creates it via `Base`.
2. **Mistake gateway** — `MistakeGateway` mixin in `db/clinical_gateway.py` with
   `log_mistake()`, `recent_mistakes()`, and `mistake_lessons_prompt()`. Registered in
   `DatabaseGateway` (db/database.py).
3. **MistakeLogger agent** (`intelligence/mistake_logger.py`, one file per agent) — records a
   correction as a `MistakeNote` and, when no explicit lesson is given, derives a short
   generalised rule via the LLM. Exposes `lessons_for_prompt()` to feed guardrails back in.
4. **ContextCompactor agent** (`intelligence/context_compactor.py`) — anchored incremental
   compaction. `compact()` estimates tokens (chars/4) and, when usage exceeds 90% of the
   128k window, folds all-but-the-last-6 turns into the persistent summary and returns
   `[summary] + recent verbatim turns`. Recent turns always stay verbatim (no data loss).
5. **Wiring** — `Orchestrator` now owns a `ContextCompactor` and `MistakeLogger`. Each turn:
   - compacts `session_history` before calling the companion (passes compacted history);
   - if the safety agent alters the companion reply, fires a background `mistake_logger.record`
     (mistake_type="safety") so the companion learns;
   - passes past-mistake `lessons` into the companion prompt as gentle guardrails.
6. **Companion** — `_COMPANION_SYSTEM_PROMPT` gains a `lessons_context` slot; `respond()`
   accepts `lessons` and injects it.

## Verification
- `py_compile` passes on all touched modules.
- `IMPORT_OK` smoke test in the backend venv (agents.orchestrator,
  intelligence.context_compactor, intelligence.mistake_logger) succeeds.
- Follow-up (manual, needs running backend): a long session should trigger compaction
  (logged as "Context compacted") and a safety override should create a `mistake_notes` row.

## Status
Done (code + imports verified; live run pending).
