# Request 035 - Fix doctor never actually gets called on emergency

## Goal

A live call showed the patient say "എനിക്ക് ഭയങ്കര ഹൃദയവേദന. ഡോക്ടറിനെ ഒന്ന്
വിളിക്കാമോ?" (terrible heart pain, can you call the doctor?). The companion only
replied "ശരി, ചേട്ടാ. ഞാൻ ഡോക്ടറെ വിളിക്കാം" (okay, I'll call the doctor) and the
actual emergency cascade NEVER fired. The patient was left without help.

## Root cause

`voice/twilio_handler.py` emergency detection used EXACT phrase markers:
- `_requests_doctor_call` only matched "ഡോക്ടറെ വിളിക്കൂ/വിളിക്കണം/വിളിച്ചോളൂ"
  etc. The patient said "ഡോക്ടറിനെ ഒന്ന് വിളിക്കാമോ" — dative "ഡോക്ടറിനെ" +
  "വിളിക്കാമോ" — so NO marker matched.
- `_is_red_flag` only matched "നെഞ്ച്"/"heart pain", missing "ഹൃദയവേദന"
  (heart pain, common phrasing).
- The gate also required `confidence >= 0.3`, but that field is Sarvam's
  language-ID probability (unreliable, default 0.85) — a wrong signal to gate
  emergencies on.

## Changes

- `_is_red_flag`: broad root-word/substring markers (ഹൃദയ, വേദന, ശ്വാസം, വീഴുക,
  etc.) so natural symptom variants are caught.
- `_requests_doctor_call`: broad substring matching on roots ഡോക്ട, വിളി,
  വൈദ്യൻ and English "doctor"/"call" so phrasings like "ഡോക്ടറിനെ വിളിക്കാമോ"
  are detected.
- Removed the `confidence >= 0.3` gate (never suppress an emergency on a
  language-ID score). A red-flag symptom combined with any mention of the
  doctor/calling is now treated as an explicit call request.
- Added `test_detection_catches_natural_call_phrasings` regression test.

## Validation

- `python tests/test_voice_pipeline.py` — all 7 cases pass, including the new
  regression and the existing emergency-cascade tests.
