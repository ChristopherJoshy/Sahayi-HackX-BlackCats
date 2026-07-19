"""Twilio voice transport handler for SAHAYI."""
from __future__ import annotations
import asyncio
import base64
import json
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import Connect, VoiceResponse
from core.config import get_settings
from db.database import DatabaseGateway
from intelligence.emergency_caller import EmergencyCaller
from utils.logger import get_logger
from utils.validators import normalize_phone
from voice.audio_codec import mulaw_to_pcm16, upsample_8k_to_16k, pcm_to_wav
from voice.sarvam_stt import SarvamSTTClient
from voice.sarvam_tts import SarvamTTSClient
from voice.vad import SileroVAD
from voice.thinking_sounds import ThinkingSoundManager

@dataclass(slots=True)
class VoiceSessionState:
    """In-memory state for one live Twilio media stream.

    Args:
        session_id: Active session UUID.
        patient: Patient profile dictionary.
        stream_sid: Twilio stream SID once known.
        started_at: Stream start time.
        buffer: In-memory inbound audio buffer.
        processing: Whether an STT turn is already being processed.
        last_response_time: Timestamp of last response sent to user.
    Returns:
        VoiceSessionState dataclass.
    Agent:
        Voice
    """
    session_id: str
    patient: dict
    stream_sid: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    buffer: bytearray = field(default_factory=bytearray)
    processing: bool = False
    last_response_time: datetime = field(default_factory=datetime.utcnow)
    speech_detected: bool = False
    silence_start: datetime | None = None
    vad: SileroVAD | None = None
    language: str = ""
    pcm_buffer: bytearray = field(default_factory=bytearray)
    # 16 kHz upsampled PCM used for Silero VAD. Silero is trained on 16 kHz;
    # feeding it 8 kHz Twilio audio corrupts speech detection and either clips
    # real speech (garbled transcript) or never detects it. Kept separate from
    # pcm_buffer so the STT path can still use the cleaner 16 kHz upsample.
    pcm_buffer_16k: bytearray = field(default_factory=bytearray)
    emergency_pending: bool = False
    emergency_offered_at: datetime | None = None
    emergency_reason: str = ""
    opening: bool = False
    echo_cleared: bool = False
    # Length of ``buffer`` (and its PCM twins) at the instant the echo window
    # opens. We only ever trim this much when the window clears, so any patient
    # speech that arrived *early* (during the agent's reply tail) is preserved
    # instead of being wiped.
    echo_open_len: int = 0
    # Cumulative bytes of speech detected this turn, used by adaptive
    # end-of-turn detection to pick a short vs long trailing-silence window.
    speech_bytes: int = 0
    # Set when the patient interrupted the agent mid-reply (barge-in). The
    # pipeline reads this to flush the outbound buffer and pivot to the new turn.
    barge_in_detected: bool = False
    # When barge-in speech first became sustained, for the min-duration gate.
    barge_in_since: datetime | None = None
    # When the last TTS reply is expected to finish playing. Inbound audio
    # arriving before this is almost always the agent's own voice echoing back
    # through the phone (Twilio media streams have no server-side echo
    # cancellation), so we must ignore it or the agent talks to itself.
    response_audio_end: datetime = field(default_factory=datetime.utcnow)
    last_transcript: str = ""
    last_transcript_at: datetime | None = None
    session_history: list[str] = field(default_factory=list)


class TwilioVoiceHandler:
    """Handle Twilio voice webhooks and media stream events."""

    def __init__(
        self,
        database: DatabaseGateway,
        orchestrator: object,
        sockets: object,
        emergency_caller: EmergencyCaller | None = None,
        doctor_briefer: object | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise Twilio voice transport dependencies.

        Args:
            database: Shared database gateway instance.
            orchestrator: Shared orchestrator instance.
            sockets: Shared dashboard socket manager.
            emergency_caller: Optional emergency call cascade handler.
            doctor_briefer: Optional agent that briefs the on-call doctor.
            http_client: Shared HTTP client session.
        Returns:
            None.
        Agent:
            Voice
        """

        self.database = database
        self.orchestrator = orchestrator
        self.sockets = sockets
        self.settings = get_settings()
        self.stt = SarvamSTTClient(http_client)
        self.tts = SarvamTTSClient(http_client)
        self.thinking_sounds = ThinkingSoundManager(self.tts)
        asyncio.create_task(self.thinking_sounds.initialize())
        self.logger = get_logger("sahayi.twilio_handler")
        self.sessions: dict[str, VoiceSessionState] = {}
        self.client = Client(self.settings.twilio_account_sid, self.settings.twilio_auth_token) if self.settings.twilio_account_sid and self.settings.twilio_auth_token else None
        self.emergency_caller = emergency_caller
        self.doctor_briefer = doctor_briefer
        # Patient/emergency context keyed by the patient-call session id, used
        # to brief the doctor when they answer the outbound emergency call.
        self.emergency_contexts: dict[str, dict] = {}

    async def create_incoming_response(self, form_data: dict[str, str], websocket_base: str, outbound_patient_id: int | None = None) -> tuple[str, str]:
        """Create a TwiML response for an incoming Twilio call.

        For inbound calls the patient is resolved by caller phone number.
        For outbound follow-up calls, `outbound_patient_id` carries the
        database ID so the handler can identify the patient even though the
        caller number belongs to Twilio.

        Args:
            form_data: Twilio webhook form payload.
            websocket_base: Public WebSocket base URL.
            outbound_patient_id: Optional patient ID for outbound calls.
        Returns:
            Tuple of `(session_id, twiml_xml)`.
        Agent:
            Voice
        """

        patient = None
        if outbound_patient_id:
            patient = await self.database.get_patient_by_id(outbound_patient_id)
        if not patient:
            raw_from = form_data.get("From", "")
            phone_number = normalize_phone(str(raw_from))
            patient = await self.database.get_patient_by_phone(phone_number)
        if not patient:
            all_patients = await self.database.list_all_patients()
            if all_patients:
                patient = all_patients[0]
                self.logger.warning(
                    "Caller %s not found in DB. Falling back to demo patient: %s (ID: %d)",
                    raw_from,
                    patient.name,
                    patient.id
                )
        session_id = str(uuid4())
        if not patient:
            response = VoiceResponse()
            response.say("നിങ്ങളുടെ നമ്പർ സഹായിയിൽ രജിസ്റ്റർ ചെയ്തിട്ടില്ല. നിങ്ങളുടെ ഡോക്ടറോട് നിങ്ങളുടെ നമ്പർ ചേർക്കാൻ ആവശ്യപ്പെടുക.", language="ml-IN")
            return session_id, str(response)
        patient_payload = {"id": patient.id, "name": patient.name, "language": patient.language, "registration_number": patient.registration_number or "", "conditions": patient.conditions, "medicines": patient.medicines, "doctor_uid": patient.doctor_uid, "doctor_email": patient.doctor_email, "doctor_contact": patient.doctor_contact or {}, "relatives": patient.relatives}
        self.sessions[session_id] = VoiceSessionState(session_id=session_id, patient=patient_payload)
        await self.database.create_call_session(patient.id, session_id)
        response = VoiceResponse()
        connect = Connect()
        connect.stream(url=f"{websocket_base}/ws/voice/{session_id}")
        response.append(connect)
        return session_id, str(response)

    async def create_emergency_response(self, form_data: dict[str, str], websocket_base: str, session_id: str) -> str:
        """Create a TwiML response for the doctor-facing emergency call.

        Opens a media stream flagged ``role=doctor`` (carried as a query param
        on the WebSocket URL) so the WebSocket handler briefs the doctor and
        answers their questions instead of running the patient companion.

        Args:
            form_data: Twilio webhook form payload (unused, kept for symmetry).
            websocket_base: Public WebSocket base URL.
            session_id: Patient-call session id for context lookup.
        Returns:
            TwiML XML string connecting the doctor to the voice WebSocket.
        Agent:
            Voice
        """

        ctx = self.emergency_contexts.get(session_id, {})
        if not ctx:
            self.logger.warning("Emergency context missing for session_id=%s", session_id)
        response = VoiceResponse()
        connect = Connect()
        # role=doctor tells the WebSocket handler to run the doctor briefer.
        connect.stream(url=f"{websocket_base}/ws/voice/{session_id}?role=doctor")
        response.append(connect)
        return str(response)

    async def handle_stream_event(self, session_id: str, raw_message: str) -> tuple[str, dict | None, bool]:
        """Handle one Twilio media-stream WebSocket message (non-blocking).

        Returns quickly so the WebSocket receive loop stays responsive.
        Heavy processing is signalled via the `ready` flag and should be
        executed in a background task by calling `process_audio_turn`.

        Args:
            session_id: Active session UUID.
            raw_message: Raw JSON string from Twilio.
        Returns:
            Tuple of (event_type, optional immediate outbound media dict,
            ready_for_processing flag).
        Agent:
            Voice
        """

        message = json.loads(raw_message)
        state = self.sessions.get(session_id)
        if not state:
            return ("unknown", None, False)

        event = message.get("event")

        if event == "start":
            outbound = await self._on_start(state, message)
            # Kick off the natural opening-line generation in the background so
            # the thinking beep plays first, then the agent's voice follows.
            state.opening = True
            state.processing = True
            return ("start", outbound, True)

        if event == "media":
            try:
                ready = self._accumulate_audio(state, message)
            except Exception:
                # Never let a single bad audio frame kill the media-stream
                # loop — that would leave the agent silent after the opener.
                self.logger.exception("VAD/accumulate error | session=%s", session_id)
                ready = False
            outbound = None
            if ready:
                outbound = self.thinking_sounds.get_thinking_payloads(state.stream_sid, state.patient.get("language", "ml-IN"))
            return ("media", outbound, ready)

        if event == "mark":
            # Twilio confirms our audio finished playing — stop gating input.
            state.last_response_time = datetime.utcnow()
            state.response_audio_end = datetime.utcnow()
            return ("mark", None, False)

        if event == "stop":
            await self._on_stop(state)
            return ("stop", None, False)

        return (event or "unknown", None, False)

    async def handle_doctor_stream_event(self, session_id: str, raw_message: str) -> tuple[str, dict | None, bool]:
        """Handle one Twilio media-stream event for the doctor-facing call.

        Mirrors ``handle_stream_event`` but operates on the doctor briefer
        instead of the patient companion.

        Args:
            session_id: Active doctor-call session UUID.
            raw_message: Raw JSON string from Twilio.
        Returns:
            Tuple of (event_type, optional outbound media dict, ready flag).
        Agent:
            Voice
        """

        message = json.loads(raw_message)
        doctor_key = f"{session_id}_doctor"
        state = self.sessions.get(doctor_key)
        if not state and message.get("event") != "start":
            return ("unknown", None, False)

        event = message.get("event")

        if event == "start":
            # Ensure a fresh doctor-side state exists (the patient call may
            # have ended and popped the original session state).
            if doctor_key not in self.sessions:
                ctx = self.emergency_contexts.get(session_id, {})
                self.sessions[doctor_key] = VoiceSessionState(
                    session_id=session_id, patient=ctx.get("patient", {})
                )
            state = self.sessions[doctor_key]
            state.stream_sid = message.get("start", {}).get("streamSid", "")
            state.opening = True
            state.processing = True
            return ("start", None, True)

        if event == "media":
            try:
                ready = self._accumulate_audio(state, message)
            except Exception:
                self.logger.exception("VAD/accumulate error (doctor) | session=%s", session_id)
                ready = False
            outbound = None
            if ready:
                outbound = self.thinking_sounds.get_thinking_payloads(state.stream_sid, state.patient.get("language", "ml-IN"))
            return ("media", outbound, ready)

        if event == "mark":
            state.last_response_time = datetime.utcnow()
            state.response_audio_end = datetime.utcnow()
            return ("mark", None, False)

        if event == "stop":
            self.sessions.pop(doctor_key, None)
            return ("stop", None, False)

        return (event or "unknown", None, False)

    async def process_doctor_turn(self, session_id: str):
        """Run the doctor-briefing pipeline for one doctor turn.

        Opens with a patient briefing, then answers the doctor's follow-up
        questions using the patient context captured at escalation time.

        Args:
            session_id: Active doctor-call session UUID.
        Yields:
            Outbound media-event dicts to send over the WebSocket.
        Agent:
            Voice
        """

        state = self.sessions.get(f"{session_id}_doctor")
        if not state:
            return

        audio_data = bytes(state.buffer)
        state.buffer.clear()

        self.logger.info(
            "Voice turn ready | session_id=%s | inbound_mulaw_bytes=%d | opening=%s",
            state.session_id, len(audio_data), state.opening,
        )

        try:
            if state.opening:
                state.opening = False
                ctx = self.emergency_contexts.get(session_id, {})
                patient = ctx.get("patient", {})
                reason = ctx.get("reason", "")
                risk = float(ctx.get("risk_score", 0.0))
                if self.doctor_briefer:
                    text = self.doctor_briefer.build_briefing(patient, reason, risk)
                else:
                    text = f"Emergency for patient {patient.get('name', 'unknown')}. {reason}"
                audio = await self.tts.synthesize(text, "en-IN")
                if audio:
                    self._mark_response_sent(state, audio)
                    for _m in self._build_media_payload(state.stream_sid, audio):
                        yield _m
                return

            transcript = await self.stt.transcribe(
                mulaw_to_pcm16(audio_data), language_code="en-IN", sample_rate=8000
            )
            text = str(transcript.get("text", "")).strip()
            detected = transcript.get("language") or "en-IN"
            if not text:
                return

            ctx = self.emergency_contexts.get(session_id, {})
            patient = ctx.get("patient", {})
            reason = ctx.get("reason", "")
            risk = float(ctx.get("risk_score", 0.0))
            state.session_history.append(f"doctor:{text}")
            history = list(state.session_history)
            if self.doctor_briefer:
                reply = await self.doctor_briefer.answer(patient, text, history, reason, risk)
            else:
                reply = f"Limited information on {patient.get('name', 'the patient')}. Main concern: {reason}"
            audio = await self.tts.synthesize(reply, detected or "en-IN")
            if audio:
                self._mark_response_sent(state, audio)
                for _m in self._build_media_payload(state.stream_sid, audio):
                    yield _m
        except Exception:
            self.logger.exception("Error processing doctor turn | session_id=%s", session_id)
        finally:
            state.processing = False

    async def _on_start(self, state: VoiceSessionState, message: dict) -> dict | None:
        """Handle Twilio stream start: register the call and signal the opener.

        The opening line is generated by the companion agent as a normal first
        turn (so it sounds human and matches the patient's language). That
        generation is kicked off as a background task by the caller; this method
        returns nothing immediate so there is no artificial beep or dead air.

        Args:
            state: Mutable voice session state.
            message: Parsed Twilio event payload.
        Returns:
            None (the opening audio arrives via the background task).
        Agent:
            Voice
        """

        state.stream_sid = message.get("start", {}).get("streamSid", "")
        await self.sockets.broadcast(state.patient["doctor_uid"], "call_started", {"session_id": state.session_id, "patient_id": state.patient["id"], "patient_name": state.patient["name"], "language": state.patient["language"], "started_at": state.started_at.isoformat()})
        return None

    # Sarvam STT rejects audio longer than 30s.  Keep at most ~20s of
    # 8 kHz mono mu-law (1 byte per sample) to stay safely under the limit.
    _MAX_BUFFER_BYTES = 160_000

    # Adaptive end-of-turn detection (replaces a fixed silence threshold).
    # A single constant either cuts people off mid-thought (too short) or adds
    # dead air (too long). We instead vary the trailing-silence window: short
    # for brief replies (yes/no), longer for longer speech, so the agent waits
    # for the patient to finish without feeling sluggish. See _trailing_silence().
    _SILENCE_SHORT_SECONDS = 0.35   # brief utterance (<= ~1.2s of speech)
    _SILENCE_LONG_SECONDS = 0.7     # longer utterance (gives pause-to-think room)
    _SPEECH_SHORT_BYTES = 10_000    # ~1.2s of 8kHz mu-law marks a "short" turn
    # Minimum speech duration before we ever allow end-of-turn, so we never
    # clip the start of a sentence on a stray breath.
    _MIN_SPEECH_BYTES = 1_600       # ~0.2s of 8kHz mu-law
    # Barge-in: the agent's own voice echoes back through the handset with no
    # server-side AEC, so we keep the echo gate for this long after playback
    # STARTS before we trust inbound VAD as a real interruption.
    _BARGE_IN_ECHO_MARGIN_SECONDS = 0.4
    # Sustained patient speech needed to count as barge-in (not a cough/blip).
    _BARGE_IN_MIN_SECONDS = 0.3

    def _accumulate_audio(self, state: VoiceSessionState, message: dict) -> bool:
        """Buffer inbound audio and return True when ready to process.

        Uses Silero VAD for voice activity detection: waits for the user
        to start speaking, then waits for trailing silence before
        triggering STT.  This prevents cutting the user off mid-sentence.

        Args:
            state: Mutable voice session state.
            message: Parsed Twilio media event payload.
        Returns:
            True when the user has finished speaking and audio is ready.
        Agent:
            Voice
        """

        payload = base64.b64decode(message.get("media", {}).get("payload", ""))

        # Twilio mirrors outbound media onto the inbound stream. A later
        # byte-count cleanup cannot reliably split that echo from early caller
        # speech, so do not queue frames until playback has drained.
        if datetime.utcnow() < state.response_audio_end:
            return False

        state.buffer.extend(payload)
        
        # Convert mu-law to PCM16 (8 kHz) and keep a 16 kHz copy for Silero VAD,
        # which is trained on 16 kHz and misbehaves on 8 kHz input.
        pcm_chunk = mulaw_to_pcm16(payload)
        state.pcm_buffer.extend(pcm_chunk)
        state.pcm_buffer_16k.extend(upsample_8k_to_16k(pcm_chunk))

        # Trim leading (oldest) audio so we never exceed the STT limit
        overflow = len(state.buffer) - self._MAX_BUFFER_BYTES
        if overflow > 0:
            del state.buffer[:overflow]

        if state.processing:
            return False

        # While our last reply is still playing (or its echo is draining),
        # defer processing so the agent does not "hear itself" and answer back.
        # IMPORTANT: we do NOT discard buffered audio on every chunk. If the
        # patient starts answering before the window closes (common in natural
        # conversation), their speech is preserved. When the window finally
        # opens we drop the echo tail once, then run VAD fresh on whatever the
        # patient said afterwards — so the agent actually hears the answer
        # instead of repeating the same question.
        if datetime.utcnow() < state.response_audio_end:
            # Within the echo window: never trust inbound audio (it's the
            # agent's own voice bouncing back). Keep deferring.
            state.speech_detected = False
            state.silence_start = None
            state.barge_in_since = None
            # Remember how much audio has piled up so far; this is the echo
            # tail we will trim (and only trim) once the window opens.
            if not state.echo_cleared:
                state.echo_open_len = max(state.echo_open_len, len(state.buffer))
            state.echo_cleared = False
            return False

        # Past the echo window but reply still playing: this is where real
        # barge-in can happen. If enabled, watch inbound VAD for SUSTAINED
        # speech and treat it as the patient interrupting. We require a min
        # duration so a cough or clipped echo tail doesn't trigger it.
        if self.settings.barge_in_enabled and not state.barge_in_detected:
            if not state.vad:
                state.vad = SileroVAD()
            speaking = False
            while len(state.pcm_buffer_16k) >= 1024:
                chunk = state.pcm_buffer_16k[:1024]
                del state.pcm_buffer_16k[:1024]
                try:
                    if state.vad.is_speech(bytes(chunk), sample_rate=16000):
                        speaking = True
                        state.speech_bytes += len(chunk)
                except Exception:
                    pass
            now = datetime.utcnow()
            if speaking:
                if state.barge_in_since is None:
                    state.barge_in_since = now
                elif (now - state.barge_in_since).total_seconds() >= self._BARGE_IN_MIN_SECONDS:
                    # Confirmed interruption: stop listening to the rest of our
                    # own reply and pivot to the patient's new turn.
                    self.logger.info("Barge-in detected | session_id=%s", state.session_id)
                    state.barge_in_detected = True
                    state.speech_detected = False
                    state.silence_start = None
                    state.processing = True
                    state.pcm_buffer.clear()
                    state.pcm_buffer_16k.clear()
                    if state.vad:
                        state.vad.reset_state()
                    return True
            else:
                state.barge_in_since = None
            # Not a confirmed barge-in yet; keep deferring but preserve buffer.
            return False
        # Window just opened: clear only the echo that piled up during playback.
        # Critically, we do NOT wipe the entire buffer. A patient who answers
        # promptly — while the agent's reply is still draining — will already
        # have real speech buffered. Clearing everything there would delete
        # their first words and the agent would "hear" silence, transcribe
        # nothing, then ask them to repeat ("can't understand what I said").
        # We only drop the leading ``echo_open_len`` bytes captured up to the
        # moment the window opened (the agent's own echo), leaving any patient
        # speech that followed it intact for STT.
        if not state.echo_cleared:
            drop = min(state.echo_open_len, len(state.buffer))
            del state.buffer[:drop]
            p_drop = min(state.echo_open_len, len(state.pcm_buffer))
            del state.pcm_buffer[:p_drop]
            p16_drop = min(state.echo_open_len * 2, len(state.pcm_buffer_16k))
            del state.pcm_buffer_16k[:p16_drop]
            state.speech_detected = False
            state.silence_start = None
            state.speech_bytes = 0
            if state.vad:
                state.vad.reset_state()
            state.echo_cleared = True

        # Initialize VAD lazily
        if not state.vad:
            state.vad = SileroVAD()

        # Silero VAD expects 16 kHz: process the upsampled buffer in 512-sample
        # (1024-byte) frames so its internal state stays correct.
        is_speaking_now = False
        processed_any = False
        
        while len(state.pcm_buffer_16k) >= 1024:
            chunk = state.pcm_buffer_16k[:1024]
            del state.pcm_buffer_16k[:1024]

            try:
                # threshold=0.5 is default in Silero
                if state.vad.is_speech(bytes(chunk), sample_rate=16000):
                    is_speaking_now = True
                    state.speech_bytes += len(chunk)
                processed_any = True
            except Exception as e:
                self.logger.error("VAD error: %s", e)
                # Fallback to assuming silence
                pass

        if not processed_any:
            # Not enough data for VAD yet, maintain previous state
            return False

        if is_speaking_now:
            # User is speaking — latch speech and remember *when* it last
            # happened. We only ever move this timestamp forward (never reset
            # it to None) so brief noise blips between words simply nudge the
            # end-of-turn timer slightly later instead of fully restarting it.
            # Without this, telephony audio (breaths, lip smacks, line noise)
            # makes the silence timer reset every frame and the turn NEVER
            # fires — the agent goes silent after the patient speaks.
            state.speech_detected = True
            state.silence_start = datetime.utcnow()
            return False

        # Energy is low — if we already heard speech, check how long it has
        # been since the LAST voiced frame, not since some arbitrary pause.
        if state.speech_detected and state.silence_start is not None:
            now = datetime.utcnow()
            if (now - state.silence_start).total_seconds() >= self._trailing_silence(state):
                # User stopped speaking
                state.speech_detected = False
                state.silence_start = None
                state.processing = True
                state.vad.reset_state()
                state.pcm_buffer.clear()
                state.pcm_buffer_16k.clear()
                return True

        return False

    @staticmethod
    def _trailing_silence(state: "VoiceSessionState") -> float:
        """Adaptive trailing-silence window for end-of-turn detection.

        Brief turns (yes/no, "I'm fine") get a short window so the agent answers
        snappily; longer turns get a longer window so a natural pause-to-think
        mid-explanation isn't mistaken for the end of the turn. A minimum speech
        floor prevents clipping the start of a sentence on a stray breath.

        Args:
            state: Mutable voice session state (carries this turn's speech bytes).
        Returns:
            Trailing-silence seconds threshold.
        Agent:
            Voice
        """

        if state.speech_bytes < TwilioVoiceHandler._MIN_SPEECH_BYTES:
            # Too little speech to be a real turn yet — wait longer before
            # committing to end-of-turn so we don't chop the first word.
            return TwilioVoiceHandler._SILENCE_LONG_SECONDS
        if state.speech_bytes <= TwilioVoiceHandler._SPEECH_SHORT_BYTES:
            return TwilioVoiceHandler._SILENCE_SHORT_SECONDS
        return TwilioVoiceHandler._SILENCE_LONG_SECONDS

    async def process_audio_turn(self, session_id: str):
        """Run the heavy STT → orchestrator → TTS pipeline for one turn.

        Designed to be called from a background `asyncio.Task` so the
        WebSocket receive loop stays responsive to keepalive pings.
        ``state.processing`` is already True when this method is called.

        Args:
            session_id: Active session UUID.
        Yields:
            Outbound media dicts to send over the WebSocket.
        """

        state = self.sessions.get(session_id)
        if not state:
            return

        audio_data = bytes(state.buffer)
        state.buffer.clear()

        try:
            # Barge-in: the patient interrupted our reply. Flush whatever is
            # still queued in Twilio's jitter buffer so we don't keep talking
            # over them, then pivot to their new turn.
            if state.barge_in_detected:
                state.barge_in_detected = False
                state.barge_in_since = None
                self.logger.info("Barge-in flush | session_id=%s", state.session_id)
                yield {"event": "clear", "streamSid": state.stream_sid}

            # Opening line: no transcript yet — generate a natural first turn
            # from the companion so the patient hears a human voice, not a
            # canned greeting. Language matches the patient's profile default.
            if state.opening:
                state.opening = False
                lang = state.patient.get("language") or "ml-IN"
                reply_text = ""
                try:
                    turn_result = await self.orchestrator.handle_turn(
                        state.patient, state.session_id, "", detected_language=lang, is_opening=True
                    )
                    reply_text = (turn_result.reply.text or "").strip()
                except Exception:
                    self.logger.exception(
                        "Opening turn failed | session_id=%s — using fallback greeting",
                        state.session_id,
                    )
                # Guarantee the patient always hears a voice: if the model or
                # TTS returned nothing (empty reply, API hiccup, timeout), fall
                # back to a deterministic warm opener in their language so the
                # call never starts with dead air.
                if len(reply_text) < 10:
                    reply_text = self._fallback_opener(state.patient, lang)
                audio = await self.tts.synthesize(reply_text, lang)
                if not audio:
                    # Last-resort: even TTS failed — try the Malayalam default
                    # opener, which the provider is most likely to render.
                    audio = await self.tts.synthesize(
                        self._fallback_opener(state.patient, "ml-IN"), "ml-IN"
                    )
                if audio:
                    self._mark_response_sent(state, audio)
                    for _m in self._build_media_payload(state.stream_sid, audio):
                        yield _m
                return

            # Twilio media streams are 8 kHz mu-law. Decode to 8 kHz PCM16 and
            # send at the native rate — Sarvam transcribes telephony audio best
            # at 8 kHz (upsampling was degrading recognition).
            transcript = await self.stt.transcribe(
                mulaw_to_pcm16(audio_data), language_code="ml-IN", sample_rate=8000
            )

            # Record the detected language for observability / future routing.
            detected = transcript.get("language") or ""
            if detected:
                state.language = detected

            # Reply in the language the patient actually spoke this turn. Fall
            # back to their profile default only when STT detection is empty.
            reply_language = "ml-IN"
            self.logger.info(
                "Voice STT result | session_id=%s | language=%s | repeat=%s | transcript=%r",
                state.session_id, detected, transcript["should_repeat"], transcript["text"],
            )

            if transcript["should_repeat"]:
                if transcript["text"]:
                    repeat_msgs = {
                        "ml-IN": "ക്ഷമിക്കണം, വ്യക്തമല്ല. വീണ്ടും പറയാമോ?",
                        "hi-IN": "माफ़ कीजिए, स्पष्ट नहीं है। कृपया फिर से बोलें?",
                        "ta-IN": "மன்னிக்கவும், தெளிவாக இல்லை. மீண்டும் சொல்ல முடியுமா?",
                        "te-IN": "క్షమించండి, స్పష్టంగా లేదు. దయచేసి మళ్ళీ చెప్పగలరా?",
                        "kn-IN": "ಕ್ಷಮಿಸಿ, ಸ್ಪಷ್ಟವಾಗಿಲ്ല. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ?",
                    }
                    repeat_text = repeat_msgs.get(reply_language or "", repeat_msgs["ml-IN"])
                    audio = await self.tts.synthesize(repeat_text, reply_language)
                    if audio:
                        self._mark_response_sent(state, audio)
                        for _m in self._build_media_payload(state.stream_sid, audio):
                            yield _m
                # If no text at all, gently ask the patient to repeat so the
                # conversation never dies in silence (a garbled first reply used
                # to fall through to an empty TTS and go permanently quiet).
                elif not str(transcript["text"]).strip():
                    repeat_msgs = {
                        "ml-IN": "ക്ഷമിക്കണം, വ്യക്തമല്ല. വീണ്ടും പറയാമോ?",
                        "hi-IN": "माफ़ कीजिए, स्पष्ट नहीं है। कृपया फिर से बोलें?",
                        "ta-IN": "மன்னிக்கவும், தெளிவாக இல்லை. மீண்டும் சொல்ல முடியுமா?",
                        "te-IN": "క్షమించండి, స్పష్టంగా లేదు. దయచేసి మళ్ళీ చెప్పగలరా?",
                        "kn-IN": "ಕ್ಷಮಿಸಿ, ಸ್ಪಷ್ಟವಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ?",
                    }
                    repeat_text = repeat_msgs.get(reply_language or "", repeat_msgs["ml-IN"])
                    audio = await self.tts.synthesize(repeat_text, reply_language)
                    if audio:
                        self._mark_response_sent(state, audio)
                        for _m in self._build_media_payload(state.stream_sid, audio):
                            yield _m
            else:
                text = str(transcript["text"])
                normalized_text = " ".join(text.lower().split())
                now = datetime.utcnow()
                if (
                    normalized_text
                    and normalized_text == state.last_transcript
                    and state.last_transcript_at is not None
                    and (now - state.last_transcript_at).total_seconds() < 8
                ):
                    self.logger.warning(
                        "Duplicate STT turn ignored | session_id=%s", state.session_id
                    )
                    return
                state.last_transcript = normalized_text
                state.last_transcript_at = now

                # Emergency cascade: if we already asked for permission and the
                # patient now answers (or stayed silent too long), act on it.
                if state.emergency_pending:
                    audio = await self._resolve_emergency_response(state, text, reply_language)
                    if audio:
                        self._mark_response_sent(state, audio)
                        for _m in self._build_media_payload(state.stream_sid, audio):
                            yield _m
                    return

                # Detect a red-flag symptom OR an explicit request to call the
                # doctor. Sarvam's "confidence" is a language-ID probability (often
                # low for Indic even on perfect audio), so it is NEVER used to
                # suppress an emergency — a missed red flag is dangerous. We only
                # skip when the transcript is empty (handled above).
                is_red_flag = self._is_red_flag(text)
                is_call_request = self._requests_doctor_call(text)
                # A red-flag symptom combined with any mention of the doctor or
                # calling is treated as an explicit call request (e.g. "എനിക്ക്
                # ഹൃദയവേദന, ഡോക്ടറിനെ വിളിക്കാമോ" — heart pain + call the doctor).
                if is_red_flag and ("ഡോക്ട" in text.lower() or "വിളി" in text.lower()
                                    or "doctor" in text.lower() or "call" in text.lower()):
                    is_call_request = True
                if not state.emergency_pending and (is_red_flag or is_call_request):
                    state.emergency_pending = True
                    state.emergency_offered_at = datetime.utcnow()
                    state.emergency_reason = text
                    if is_call_request:
                        # The patient explicitly asked to call the doctor — take
                        # it seriously and call immediately, no verification step.
                        self._register_emergency_context(state)
                        if self.emergency_caller:
                            self._trigger_emergency(state)
                        confirm = {
                            "ml-IN": "ശരി, ഞാൻ ഇപ്പോൾ തന്നെ നിങ്ങളുടെ ഡോക്ടറെ വിളിക്കുന്നു.",
                            "hi-IN": "ठीक है, मैं अभी आपके डॉक्टर को कॉल कर रहा हूँ।",
                            "ta-IN": "சரி, நான் இப்போவே உங்க டாக்டரை கூப்பிடறேன்.",
                            "te-IN": "సరే, ఇప్పుడే మీ డాక్టర్‌ను కాల్ చేస్తున్నా.",
                            "kn-IN": "ಸರಿ, ಈಗಲೇ ನಿಮ್ಮ ಡಾಕ್ಟರ್‌ರನ್ನು ಕರೆಯುತ್ತೇನೆ.",
                            "bn-IN": "ঠিক আছে, আমি এখনই আপনার ডাক্তারকে কল করছি।",
                            "mr-IN": "ठीक आहे, मी आत्ताच तुमच्या डॉक्टरला कॉल करतोय.",
                            "gu-IN": "ઠીક છે, હું હમણાં જ તમારા ડॉક્ટરને કॉલ કરુ છું.",
                            "pa-IN": "ਠੀਕ ਹੈ, ਮੈਂ ਹੁਣੇ ਤੁਹਾਡੇ ਡਾਕਟਰ ਨੂੰ ਕਾਲ ਕਰ ਰਿਹਾ ਹਾਂ।",
                            "ur-IN": "ٹھیک ہے، میں ابھی آپ کے ڈاکٹر کو کال کر رہا ہوں۔",
                        }
                        audio = await self.tts.synthesize(confirm.get(reply_language or "", confirm["ml-IN"]), reply_language)
                        if audio:
                            self._mark_response_sent(state, audio)
                            for _m in self._build_media_payload(state.stream_sid, audio):
                                yield _m
                        return
                    # Red-flag symptom: confirm before calling (safety step).
                    offer = self._emergency_offer_text(reply_language)
                    audio = await self.tts.synthesize(offer, reply_language)
                    if audio:
                        self._mark_response_sent(state, audio)
                        for _m in self._build_media_payload(state.stream_sid, audio):
                            yield _m
                    return

                turn_result = await self.orchestrator.handle_turn(
                    state.patient, state.session_id, text, detected_language=detected or None
                )
                self.logger.info(
                    "Voice companion reply | session_id=%s | text=%r",
                    state.session_id, turn_result.reply.text,
                )
                reply_text = (turn_result.reply.text or "").strip()
                audio = await self._synthesize_with_fallback(reply_text, reply_language, state)
                if audio:
                    self.logger.info(
                        "Voice TTS ready | session_id=%s | outbound_mulaw_bytes=%d",
                        state.session_id, len(audio),
                    )
                    self._mark_response_sent(state, audio)
                    for _m in self._build_media_payload(state.stream_sid, audio):
                        yield _m
                else:
                    # TTS failed even after retries/fallback — never leave the turn
                    # silent. Ask the patient to repeat so the call survives.
                    self.logger.warning(
                        "TTS failed for companion reply | session_id=%s — asking patient to repeat",
                        state.session_id,
                    )
                    repeat_text = self._repeat_prompt(reply_language)
                    retry_audio = await self.tts.synthesize(repeat_text, reply_language)
                    if retry_audio:
                        self._mark_response_sent(state, retry_audio)
                        for _m in self._build_media_payload(state.stream_sid, retry_audio):
                            yield _m

        except Exception:
            self.logger.exception(
                "Error processing audio turn | session_id=%s", state.session_id
            )
        finally:
            state.processing = False

    async def _synthesize_with_fallback(self, text: str, lang: str | None, state: "VoiceSessionState") -> bytes:
        """Synthesize a reply, retrying once and trimming on timeout.

        A long reply (e.g. a full medicine list) can exceed the TTS timeout. If
        the first attempt returns no audio, we retry once with a shorter,
        sentence-boundary-trimmed version so the patient still hears the most
        important part instead of silence.

        Args:
            text: Companion reply text to speak.
            lang: Reply language code.
            state: Mutable voice session state (for logging context).
        Returns:
            Mu-law audio bytes, or empty bytes when every attempt failed.
        Agent:
            Voice
        """
        if not text:
            return b""
        audio = await self.tts.synthesize(text, lang)
        if audio:
            return audio
        # First attempt failed (likely a timeout on a long reply). Trim to a
        # complete sentence and retry once before giving up.
        trimmed = self._trim_to_sentence(text)
        if trimmed and trimmed != text:
            self.logger.warning(
                "TTS retry with trimmed reply | session_id=%s | before=%d after=%d",
                state.session_id, len(text), len(trimmed),
            )
            audio = await self.tts.synthesize(trimmed, lang)
            if audio:
                return audio
        return b""

    @staticmethod
    def _trim_to_sentence(text: str, maximum_chars: int = 160) -> str:
        """Trim text to a complete sentence within a character budget.

        Used when a full reply is too long for TTS to return in time. Prefers the
        last sentence terminator before the cap so the spoken fragment still ends
        cleanly.

        Args:
            text: Full reply text.
            maximum_chars: Maximum character count before trimming.
        Returns:
            The original text or a sentence-boundary prefix.
        Agent:
            Voice
        """
        value = (text or "").strip()
        if len(value) <= maximum_chars:
            return value
        prefix = value[:maximum_chars]
        for sep in ["\n", "।", ".", "?"]:
            idx = prefix.rfind(sep)
            if idx > maximum_chars * 0.4:
                return prefix[: idx + 1].strip()
        return prefix.rsplit(" ", 1)[0].strip()

    @staticmethod
    def _repeat_prompt(lang: str | None) -> str:
        """Short 'please repeat' line used when TTS fails entirely.

        Args:
            lang: Language code for the prompt.
        Returns:
            A brief repeat-request string in the patient's language.
        Agent:
            Voice
        """
        prompts = {
            "ml-IN": "ക്ഷമിക്കണം, വ്യക്തമല്ല. വീണ്ടും പറയാമോ?",
            "hi-IN": "माफ़ कीजिए, स्पष्ट नहीं है। कृपया फिर से बोलें?",
            "ta-IN": "மன்னிக்கவும், தெளிவாக இல்லை. மீண்டும் சொல்ல முடியுமா?",
            "te-IN": "క్షమించండి, స్పష్టంగా లేదు. దయచేసి మళ్ళీ చెప్పగలరా?",
            "kn-IN": "ಕ್ಷಮಿಸಿ, ಸ್ಪಷ್ಟವಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ?",
        }
        return prompts.get(lang or "", prompts["ml-IN"])

    @staticmethod
    def _fallback_opener(patient: dict, lang: str | None) -> str:
        """Deterministic warm opening line if the model/TTS pipeline fails.

        Args:
            patient: Patient profile dictionary (provides the name).
            lang: Preferred language code for the opener.
        Returns:
            A safe opening sentence in the patient's language.
        Agent:
            Voice
        """
        name = patient.get("name", "സുഹൃത്തെ")
        lang = lang or patient.get("language", "ml-IN") or "ml-IN"
        openers = {
            "ml-IN": f"{name}, സുഖമാണേല്ലേ? ഇന്ന് എങ്ങനെയുണ്ട്?",
            "hi-IN": f"{name}, सब ठीक है? आज कैसे हैं आप?",
            "ta-IN": f"{name}, நலமா? இன்னிக்கி எப்படி இருக்கிங்க?",
            "te-IN": f"{name}, అల్లి ఉన్నారా? ఈరోజు ఎలా ఉన్నారు?",
            "kn-IN": f"{name}, ಚೆನ್ನಾಗಿದ್ದೀರಾ? ಇವತ್ತು ಹೇಗಿದ್ದೀರಿ?",
        }
        return openers.get(lang, openers["ml-IN"])

    @staticmethod
    def _is_red_flag(text: str) -> bool:
        """Detect red-flag emergency keywords in a transcript.

        Uses broad root-word/substring matching (not exact phrases) because STT
        produces many natural variants of the same idea ("ഹൃദയവേദന", "നെഞ്ച്
        വേദന", "ഡോക്ടറിനെ വിളിക്കാമോ"). Missing a real red flag is far worse than
        a rare false positive, and the confirmation step below keeps false
        positives safe.

        Args:
            text: Patient transcript text.
        Returns:
            True when chest/heart pain, breathlessness, collapse, or another
            serious symptom is mentioned.
        Agent:
            Voice
        """

        lowered = (text or "").lower()
        markers = [
            # Chest / heart
            "chest pain", "heart pain", "നെഞ്ച്", "ഹൃദയ", "ഹൃദയവേദന",
            # Breathing
            "breathless", "breathing", "ശ്വാസം", "ശ്വാസതടസ്സം",
            # Collapse / unconscious
            "faint", "collapse", "dizzy", "ചുവന്ന", "unconscious", "ബോധമില്ല",
            "വീഴുക", "വീണു",
            # Severe pain (root word catches "കടുത്ത വേദന", "വേദനിക്കുന്നു", etc.)
            "severe pain", "കടുത്ത", "വേദന",
        ]
        return any(token in lowered for token in markers)

    @staticmethod
    def _requests_doctor_call(text: str) -> bool:
        """Detect an explicit patient request to contact the doctor.

        Uses broad substring matching on the roots "വിളി" (call), "ഡോക്ട" (doctor)
        and English equivalents so natural phrasings like "ഡോക്ടറിനെ ഒന്ന്
        വിളിക്കാമോ" / "doctorine call cheyyamo" are caught. Missing a real request
        is dangerous, so we err toward detection and confirm via the offer step.

        Args:
            text: Patient transcript text.
        Returns:
            True when the patient directly asks for the doctor to be called.
        Agent:
            Voice
        """

        lowered = (text or "").lower()
        markers = [
            "call the doctor", "call doctor", "contact the doctor",
            "get the doctor", "doctor", "ഡോക്ട", "വിളി", "വിളിക്ക",
            "വൈദ്യൻ", "വൈദ്യൻ",
        ]
        return any(token in lowered for token in markers)

    def _emergency_offer_text(self, lang: str | None) -> str:
        """Return the 'should I call your doctor?' prompt in the user language.

        Args:
            lang: Patient preferred language code.
        Returns:
            Emergency offer text.
        Agent:
            Voice
        """

        offers = {
            "ml-IN": "ചേച്ചി/ചേട്ടാ, ഇത് ഗൗരവമാണെന്ന് തോന്നുന്നു. നിങ്ങളുടെ ഡോക്ടറെ വിളിക്കണോ? ശരിയെങ്കിൽ 'അതെ' എന്ന് പറയൂ.",
            "hi-IN": "यह गंभीर लग रहा है। क्या मैं आपके डॉक्टर को कॉल करूँ? हाँ कहें अगर ठीक लगे।",
            "ta-IN": "இது தீவிரமா இருக்குனு தோணுது. உங்க டாக்டரை கூப்பிடலாமா? சரினா 'ஆமா'னு சொல்லுங்க.",
            "te-IN": "ఇది తీవ్రంగా ఉంది. మీ డాక్టర్‌ను కాల్ చేయాలా? సరే అంటే 'అవును' అనండి.",
            "kn-IN": "ಇದು ಗಂಭೀರವಾಗಿ ಕಾಣುತ್ತಿದೆ. ನಿಮ್ಮ ಡಾಕ್ಟರ್‌ರನ್ನು ಕರೆಯಲಾ? ಸರಿಯಾದ್ರೆ 'ಹೌದು' ಅನ್ನಿ.",
            "bn-IN": "এটা গুরুতর মনে হচ্ছে। আমি কি আপনার ডাক্তারকে কল করব? ঠিক হলে 'হ্যাঁ' বলুন।",
            "mr-IN": "हे गंभीर वाटतंय. मी तुमच्या डॉक्टरला कॉल करू? बरं वाटलं तर 'हो' म्हणा.",
            "gu-IN": "આ ગંભીર લાગે છે. શું હું તમારા ડૉક્ટરને કૉલ કરું? બરાબર હોય તો 'હા' કહો.",
            "pa-IN": "ਇਹ ਗੰਭੀਰ ਲੱਗ ਰਿਹਾ ਹੈ। ਕੀ ਮੈਂ ਤੁਹਾਡੇ ਡਾਕਟਰ ਨੂੰ ਕਾਲ ਕਰਾਂ? ਠੀਕ ਹੋਵੇ ਤਾਂ 'ਹਾਂ' ਆਖੋ।",
            "ur-IN": "یہ سنجیدہ لگ رہا ہے۔ کیا میں آپ کے ڈاکٹر کو کال کروں؟ ٹھیک ہو تو 'ہاں' کہیں۔",
        }
        return offers.get(lang or "", offers["ml-IN"])

    async def _resolve_emergency_response(self, state: VoiceSessionState, text: str, lang: str | None) -> bytes | None:
        """Act on the patient's reply to the emergency offer.

        If the patient says yes, or said nothing (no text), we trigger the
        doctor→relative call cascade. Otherwise we gracefully back out.

        Args:
            state: Mutable voice session state.
            text: Patient transcript text.
            lang: Patient preferred language code.
        Returns:
            Audio bytes for the spoken response, or None.
        Agent:
            Voice
        """

        state.emergency_pending = False
        lowered = text.lower()
        affirmative = any(token in lowered for token in [
            "yes", "അതെ", "ശരി", "അവശ്യം", "haan", "हाँ", "ஆமா", "అవును",
            "ಹೌದು", "হ্যাঁ", "हो", "હા", "ਹਾਂ", "ہاں", "ok", "call", "വിളി",
        ])
        # No reply (empty text) also counts as implicit consent per the cascade.
        if affirmative:
            if self.emergency_caller:
                self._register_emergency_context(state)
                self._trigger_emergency(state)
            confirm = {
                "ml-IN": "ശരി, ഞാൻ ഇപ്പോൾ തന്നെ നിങ്ങളുടെ ഡോക്ടറെ വിളിക്കുന്നു.",
                "hi-IN": "ठीक है, मैं अभी आपके डॉक्टर को कॉल कर रहा हूँ।",
                "ta-IN": "சரி, நான் இப்போவே உங்க டாக்டரை கூப்பிடறேன்.",
                "te-IN": "సరే, ఇప్పుడే మీ డాక్టర్‌ను కాల్ చేస్తున్నా.",
                "kn-IN": "ಸರಿ, ಈಗಲೇ ನಿಮ್ಮ ಡಾಕ್ಟರ್‌ರನ್ನು ಕರೆಯುತ್ತೇನೆ.",
                "bn-IN": "ঠিক আছে, আমি এখনই আপনার ডাক্তারকে কল করছি।",
                "mr-IN": "ठीक आहे, मी आत्ताच तुमच्या डॉक्टरला कॉल करतोय.",
                "gu-IN": "ઠીક છે, હું હમણાં જ તમારા ડॉક્ટરને કॉલ કરુ છું.",
                "pa-IN": "ਠੀਕ ਹੈ, ਮੈਂ ਹੁਣੇ ਤੁਹਾਡੇ ਡਾਕਟਰ ਨੂੰ ਕਾਲ ਕਰ ਰਿਹਾ ਹਾਂ।",
                "ur-IN": "ٹھیک ہے، میں ابھی آپ کے ڈاکٹر کو کال کر رہا ہوں۔",
            }
            msg = confirm.get(lang or "", confirm["ml-IN"])
            try:
                return await self.tts.synthesize(msg, lang)
            except Exception:
                self.logger.exception("Failed to synthesize emergency confirm | session_id=%s", state.session_id)
            return None
        else:
            decline = {
                "ml-IN": "ശരി ചേച്ചി, വേറെ എന്തെങ്കിലും പറയൂ.",
                "hi-IN": "ठीक है, और कुछ बताइए।",
                "ta-IN": "சரி, வேற ஏதாச்சும் சொல்லுங்க.",
                "te-IN": "సరే, మరోటి చెప్పండి.",
                "kn-IN": "ಸರಿ, ಬೇರೇನಾದರೂ ಹೇಳಿ.",
                "bn-IN": "ঠিক আছে, আর কিছু বলুন।",
                "mr-IN": "ठीक आहे, पुढे सांगा.",
                "gu-IN": "ઠીक છે, બીજું કહો.",
                "pa-IN": "ਠੀਕ ਹੈ, ਹੋਰ ਦੱਸੋ।",
                "ur-IN": "ٹھیک ہے، اور کچھ بتائیں۔",
            }
            msg = decline.get(lang or "", decline["ml-IN"])
            try:
                return await self.tts.synthesize(msg, lang)
            except Exception:
                self.logger.exception("Failed to synthesize emergency decline | session_id=%s", state.session_id)
            return None

    # Twilio media streams expect audio delivered as a continuous stream of
    # small media events (one per ~20 ms frame) rather than one giant blob.
    # Sending the whole TTS clip as a single payload makes Twilio truncate the
    # playback mid-sentence. Chunking into 20 ms mu-law frames fixes the
    # "reply gets cut in half" problem.
    _FRAME_BYTES = 160  # 8000 Hz * 1 byte * 0.020 s

    # Extra quiet margin after a reply finishes playing before we start
    # listening again. Absorbs the agent's own voice echoing back through the
    # handset and prevents the "talking to itself / repeating" loop.
    _RESPONSE_TAIL_MARGIN_SECONDS = 0.4

    def _mark_response_sent(self, state: "VoiceSessionState", audio: bytes) -> None:
        """Record when a spoken reply is expected to finish playing.

        Used by the inbound audio gate so the agent does not hear its own
        voice echoing back through the phone and start answering itself.

        Args:
            state: Mutable voice session state.
            audio: Mu-law audio bytes just sent (8 kHz, 1 byte/sample).
        Returns:
            None.
        Agent:
            Voice
        """

        duration = len(audio) / 8000.0
        margin = self._RESPONSE_TAIL_MARGIN_SECONDS
        state.last_response_time = datetime.utcnow()
        state.response_audio_end = datetime.utcnow() + timedelta(
            seconds=duration + margin
        )
        state.echo_cleared = False
        state.echo_open_len = 0
        state.speech_detected = False
        state.silence_start = None
        state.speech_bytes = 0
        state.buffer.clear()
        state.pcm_buffer.clear()
        state.pcm_buffer_16k.clear()
        if state.vad:
            state.vad.reset_state()

    def _register_emergency_context(self, state: "VoiceSessionState") -> None:
        """Stash patient + reason so the doctor call can be briefed.

        Args:
            state: Mutable voice session state for the patient's call.
        Returns:
            None.
        Agent:
            Voice
        """

        risk = float(self.orchestrator.session_risks.get(state.session_id, 0.0))
        self.emergency_contexts[state.session_id] = {
            "patient": dict(state.patient),
            "reason": state.emergency_reason or "The patient or Sahayi flagged a possible emergency.",
            "risk_score": risk,
        }

    def _trigger_emergency(self, state: "VoiceSessionState") -> None:
        """Fire the emergency cascade as a tracked background task.

        Args:
            state: Mutable voice session state for the patient's call.
        Returns:
            None.
        Agent:
            Voice
        """

        self._register_emergency_context(state)
        if not self.emergency_caller:
            self.logger.warning("Emergency not triggered — no emergency_caller | session_id=%s", state.session_id)
            return

        async def _run() -> None:
            try:
                await self.emergency_caller.trigger_cascade(state.patient, state.session_id)
                self.logger.info("Emergency cascade completed | session_id=%s", state.session_id)
            except Exception:
                self.logger.exception("Emergency cascade failed | session_id=%s", state.session_id)

        asyncio.create_task(_run())

    @classmethod
    def _build_media_payload(cls, stream_sid: str, audio: bytes) -> list[dict]:
        """Build Twilio-compatible outbound media events for a full clip.
        Splits the mu-law audio into ~20 ms frames (one media event each) and
        appends a short trailing silence tail so Twilio fully drains the
        playback buffer before the stream goes idle.

        Args:
            stream_sid: Twilio stream SID.
            audio: Mu-law audio bytes (8 kHz).
        Returns:
            List of media-event dicts ready to send over the WebSocket.
        Agent:
            Voice
        """

        if not audio:
            return []

        # Trailing silence (~250 ms) guarantees the last spoken word finishes
        # playing instead of being clipped at the flush boundary.
        padded = audio + b"\x7f" * (cls._FRAME_BYTES * 12)

        events: list[dict] = []
        for i in range(0, len(padded), cls._FRAME_BYTES):
            chunk = padded[i:i + cls._FRAME_BYTES]
            if len(chunk) < cls._FRAME_BYTES:
                chunk = chunk + b"\x7f" * (cls._FRAME_BYTES - len(chunk))
            events.append({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode("utf-8")},
            })
        return events

    async def _on_stop(self, state: VoiceSessionState) -> None:
        """Handle Twilio stream stop events.

        Args:
            state: Mutable voice session state.
        Returns:
            None.
        Agent:
            Voice
        """

        risk_score = float(self.orchestrator.session_risks.get(state.session_id, 0.0))
        await self.database.finalize_call_session(state.session_id, risk_score, "completed")
        await self.sockets.broadcast(state.patient["doctor_uid"], "call_ended", {"session_id": state.session_id, "patient_id": state.patient["id"], "ended_at": datetime.utcnow().isoformat(), "risk_score": risk_score})
        self.sessions.pop(state.session_id, None)

    async def initiate_follow_up_call(self, phone_number: str, patient_id: int | None = None) -> None:
        """Create an outbound Twilio follow-up call when required.

        When `patient_id` is provided the webhook URL includes it as a
        query parameter so the incoming handler can identify the patient
        even though the caller ID is the Twilio number, not the patient.

        Args:
            phone_number: Patient phone number to call.
            patient_id: Optional patient database ID for context.
        Returns:
            None.
        Agent:
            Voice
        """

        if not self.client:
            return
        destination = normalize_phone(phone_number)
        if not destination:
            self.logger.warning("Follow-up call skipped due to missing phone number")
            return
        base_url = self.settings.twilio_webhook_base.rstrip("/")
        webhook_url = base_url if base_url.endswith("/voice/incoming") else f"{base_url}/voice/incoming"
        if patient_id:
            webhook_url = f"{webhook_url}?patient_id={patient_id}"
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.calls.create,
                    to=destination,
                    from_=self.settings.twilio_phone_number,
                    url=webhook_url,
                ),
                timeout=5,
            )
        except (TwilioRestException, TimeoutError, ValueError):
            self.logger.exception("Failed to initiate Twilio follow-up call | to=%s", destination)
