# Fix doctor/patient state sharing during emergency cascade

The outbound doctor call during an emergency cascade was inadvertently sharing the active patient's `VoiceSessionState` inside `TwilioVoiceHandler.sessions`, because both the patient's incoming stream and the doctor's outbound stream used the same UUID `session_id` as the dictionary key.

This led to the following issues:
- When the doctor connected, it overwrote `state.stream_sid` with its own SID.
- The patient's background processing loop (`process_audio_turn`) was still active. It saw `state.opening = True` (triggered by the doctor's connect event), generated the patient's standard opening greeting ("Are you ok?"), and dispatched it to the doctor's `stream_sid`.
- The `process_doctor_turn` method crashed on subsequent interactions because it attempted to append to `state.session_history`, an attribute that wasn't defined on `VoiceSessionState`.

### Changes made
1.  **Isolated the doctor's state**: Appended `_doctor` to the `session_id` when accessing `self.sessions` inside `handle_doctor_stream_event` and `process_doctor_turn`.
2.  **Added `session_history` attribute**: Added `session_history: list[str] = field(default_factory=list)` to `VoiceSessionState` to fix the `AttributeError`.
