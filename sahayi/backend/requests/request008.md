# Request 008 — Companion overhaul: warm friend-like persona, memory, time-aware greetings, emergency cascade, latency + guardrails

## Changes

### Companion persona (friend, not nurse)
- `agents/main_companion.py`: replaced clinical system prompt with a warm
  companion prompt ("Sahayi" — a caring neighbour/grandchild, never an AI or
  medical assistant). Replies in the patient's language, short for simple
  check-ins, longer for deeper turns (dynamic `max_tokens`).
- `agents/whatsapp_agent.py`: same companion persona for WhatsApp; matches the
  sender's language and tone; handles patient + relative senders.

### Memory (hybrid: session + persistent notes)
- `db/models.py`: new `MemoryNote` table (patient_id, category, content).
- `db/clinical_gateway.py` + `db/database.py`: `MemoryGateway` mixin
  (`get_memory_notes`, `add_memory_note`, `prune_memory_notes`, keep ≤5).
- `intelligence/memory_manager.py` (new): extracts durable, relationship-building
  facts from each turn (fire-and-forget) and renders them into prompts so Sahayi
  sounds familiar across sessions without re-sending full history.

### Time-aware greetings
- `voice/twilio_handler.py`: `_on_start` now builds a time-of-day-aware greeting
  (morning/afternoon/evening) in the patient's language via `_build_greeting`.

### Emergency call cascade
- `intelligence/emergency_caller.py` (new): doctor → relative cascade via Twilio,
  with dashboard broadcasts at each stage.
- `voice/twilio_handler.py`: red-flag detection in `process_audio_turn`; Sahayi
  ASKS the patient before calling; if yes OR no reply within 30s → call doctor;
  if doctor unreachable → cascade to relatives. New `VoiceSessionState` fields
  `emergency_pending` / `emergency_offered_at`.
- `core/bootstrap.py`: constructs `EmergencyCaller` and injects into the handler.

### Latency + guardrails
- `core/ai.py`: added `max_tokens` param to `ask_text` / `_generate` so simple
  turns stay short and fast.
- `voice/twilio_handler.py`: trailing-silence trigger reduced 0.4s → 0.3s.
- `agents/orchestrator.py`: bounded live history (≤8 turns); loop detection
  (same transcript 3× in a row) steers the conversation elsewhere.
- `agents/main_companion.py`: live history window capped at `_MAX_HISTORY_TURNS`.

### Branding
- All `TEAM: Porottayum Beefum — Sahayi @ TECHASHY'26` headers →
  `TEAM: Black Cats — Sahayi @ HackX` (agents, rules.md, .env.example, README,
  frontend rules.md / .env.example).

## Verification
- `python -m py_compile` on all `.py` files: ALL COMPILED OK (exit 0).
- Doctor phone number already collected via `doctor_contact` in
  `PatientCreateRequest` (no frontend change required for emergency cascade).
