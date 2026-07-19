# Request 031 - Give companion patient facts so factual questions get real answers

## Goal

Stop the companion from dodging or vaguely repeating when the patient asks for
concrete information (e.g. "what medicines should I take?"). The companion had
no access to the patient's records and was forbidden from discussing medicine,
so it could only echo "the doctor's medicines" in a loop.

## Changes

- Removed the absolute ban on medicine talk. The companion may now READ BACK the
  doctor-set medicine list (names, dose, timing) and conditions as reminders,
  but must never diagnose or change/stop/skip a medicine on its own.
- Added a `THE PATIENT'S KNOWN FACTS` section to the system prompt, populated
  from the patient profile (`conditions`, `medicines`, treating doctor).
- Added `MainCompanionAgent._build_patient_facts()` to render that block, and
  wired it through `respond()` and the orchestrator so the live call always has
  the facts.
- Updated VOICE REPAIR guidance: answer real factual questions fully from the
  known facts instead of dodging or repeating the question.

## Safety

- The SafetyAgent heuristic still flags diagnosis / stop-medicine / impersonating
  a doctor, so unsafe advice is still intercepted before it reaches the patient.
- Medicines are always sourced from the doctor-set profile; the companion cannot
  invent or alter them.

## Validation

- Import the module from `backend/` to confirm it compiles.
- `python tests/test_companion_humanlike.py` (or a focused voice script) to
  confirm the companion reads back medicine details when asked.
