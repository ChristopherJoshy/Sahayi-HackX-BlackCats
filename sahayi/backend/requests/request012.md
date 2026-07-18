# Request 012 — Relative ↔ AI two-way reporting, prescription meds via WhatsApp, relative voice notes

## Context
Relatives are already stored per patient and can message the AI over WhatsApp, but the
relationship was one-directional and clinical. Three gaps remained:

1. **No proactive AI → relative reporting.** The relative only heard back when *they* messaged.
   The doctor/AI never pushed care status to the family.
2. **Relative prescriptions weren't explicitly attributed.** Prescription images already merged
   into `patient.medicines`, but a relative-sent prescription was not surfaced to the doctor as a
   relative contribution.
3. **Relative voice notes had no clinical path.** A relative voice note was transcribed and the AI
   replied (sometimes with TTS), but the clinical content never reached the doctor, and the user
   wanted voice understood via STT only (no TTS to the relative).

Per the approved design: AI → relative proactive WhatsApp on risk/session events; relative → doctor
via a **clinical summary only** (no raw transcripts, honoring the dashboard privacy rule); relative
voice understood via STT with text-only replies.

## Changes
1. **Model** — `db/models.py`: new `RelativeUpdate` table (patient_id, relative_name, update_type
   `medication|voice_note|text|symptom`, clinical_summary, source_detail, created_at).
2. **Gateway** — `db/clinical_gateway.py`: `RelativeUpdateGateway` with `add_relative_update()` and
   `recent_relative_updates()`; registered in `DatabaseGateway` (`db/database.py`).
3. **AI → relative** — `agents/relative_reporter.py` (one file per agent): composes a short, warm,
   **clinical-only** summary and sends it to the primary relative via the existing `FamilyAlertAgent`
   WhatsApp path. Wired into the orchestrator: on each turn, if risk ≥ yellow threshold or a red flag
   is present, a background `report_event()` fires. Constructed in `core/bootstrap.py` and passed to
   `Orchestrator`.
4. **Relative → doctor** — `api/routes_voice.py` `incoming_whatsapp`:
   - Prescription image from a relative → merge into `patient.medicines` **and** store a
     `relative_updates` row (`medication`) + broadcast `relative_update` to the doctor.
   - Voice note or text from a relative → after the AI reply, extract clinical facts via
     `whatsapp_agent.extract_clinical_summary()` and store a `relative_updates` row
     (`voice_note`/`text`) + broadcast. Raw transcript is never stored or shown.
   - Relatives now get **text-only replies** (`text_only=True` ⇒ no TTS) per the STT-only requirement.
5. **WhatsApp agent** — `agents/whatsapp_agent.py`: `handle_message()` gains a `text_only` flag to
   suppress TTS; new `extract_clinical_summary()` pulls only clinical facts (returns "" for NONE).
6. **Doctor API + UI** — `api/routes_patients.py`: `GET /patients/{id}/relative-updates` returns
   clinical summaries only. Frontend: `api/sahayi.js` adds `getRelativeUpdates`; `PatientProfile.jsx`
   adds a "Relative Updates" panel (fetched on load + live via the `relative_update` socket event).

## Verification
- `py_compile` clean on all touched modules; `import main` → `IMPORT_OK`.
- `npm run build` passes (2344 modules, no warnings).
- Manual (needs live backend + WhatsApp/Twilio): relative sends a prescription image → meds update +
  doctor sees a Relative Updates row; relative sends a voice note → clinical summary row appears,
  reply is text-only; risk spike → relative receives a WhatsApp care update.

## Status
Done (code + import/build verified; live Twilio run pending).
