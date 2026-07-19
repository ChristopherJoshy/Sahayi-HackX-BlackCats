"""End-to-end voice pipeline test: does a spoken turn actually fire?

The earlier fixes assumed the accumulate->turn path worked. This test builds
the real TwilioVoiceHandler with mocked deps and feeds synthetic 8 kHz mu-law
audio (loud speech then silence) to prove:
  1. handle_stream_event survives media frames (VAD doesn't crash the loop)
  2. end-of-turn detection fires (ready=True) after the user stops speaking
  3. process_audio_turn runs the STT->orchestrator->TTS pipeline and yields
     outbound media (so the user actually hears a reply)

Run from sahayi/backend:
    python tests/test_voice_pipeline.py

Agent: Test harness.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import struct
from datetime import datetime, timedelta

import tests.stubs as stubs

stubs.install_stubs()

from voice.twilio_handler import TwilioVoiceHandler, VoiceSessionState  # noqa: E402
from voice.audio_codec import pcm16_to_mulaw  # noqa: E402
from contracts.agents import TurnResult  # noqa: E402

settings = stubs.settings
settings.sarvam_api_key = "test-key"


# ---------------------------------------------------------------------------
# Mock collaborators
# ---------------------------------------------------------------------------
class FakeDB:
    async def get_patient_by_id(self, pid):
        return None
    async def create_call_session(self, *a, **k):
        return None
    async def finalize_call_session(self, *a, **k):
        return None


class FakeSockets:
    async def broadcast(self, *a, **k):
        return None


class FakeOrchestrator:
    session_risks: dict = {}

    async def handle_turn(self, patient, session_id, text, detected_language=None, is_opening=False):
        captured = text

        class _Reply:
            text = f"You said: {captured}"
        class _Res:
            reply = _Reply()
        return _Res()


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


class FakeHttpClient:
    """Answers Sarvam STT + TTS so the pipeline produces real output."""
    def __init__(self):
        self.last_stt_payload = None

    async def post(self, url, headers=None, files=None, data=None, json=None, timeout=None):
        if "speech-to-text" in url:
            self.last_stt_payload = data
            return _FakeResp(200, {
                "transcript": "നന്ദി", "language_code": "ml-IN", "language_probability": 0.9,
            })
        if "text-to-speech" in url:
            # Return a small valid mu-law payload (silence) so TTS "succeeds".
            return _FakeResp(200, {
                "audio": base64.b64encode(b"\x7f" * 160).decode(),
                "audio_format": "mulaw",
            })
        return _FakeResp(200, {})


def _mulaw_frame(pcm16_chunk: bytes) -> dict:
    mulaw = pcm16_to_mulaw(pcm16_chunk)
    return {"event": "media", "media": {"payload": base64.b64encode(mulaw).decode()}}


class _Clock:
    """Controllable wall clock so the end-of-turn silence timer is testable
    without sleeping in realtime (Twilio delivers frames ~20ms apart)."""
    def __init__(self):
        import datetime as _dt
        self._t = _dt.datetime(2026, 1, 1, 0, 0, 0)
        self._dt = _dt
    def now(self):
        return self._t
    def advance(self, seconds: float):
        self._t = self._t + self._dt.timedelta(seconds=seconds)
    def install(self):
        import voice.twilio_handler as th
        self._orig = th.datetime.utcnow
        th.datetime = self._dt
        th.datetime.utcnow = self.now


def _loud_speech_frames(seconds: float, sr: int = 8000) -> list[dict]:
    n = int(sr * seconds)
    samples = [int(18000 * math.sin(2 * math.pi * 3 * i / sr)) for i in range(n)]
    pcm = struct.pack("<" + "h" * n, *samples)
    # Twilio sends ~160 bytes (20ms) per media event (320 bytes of 8k PCM).
    return [_mulaw_frame(pcm[i:i + 320]) for i in range(0, len(pcm), 320)]


def _silence_frames(seconds: float, sr: int = 8000) -> list[dict]:
    n = int(sr * seconds)
    pcm = struct.pack("<" + "h" * n, *([0] * n))
    return [_mulaw_frame(pcm[i:i + 320]) for i in range(0, len(pcm), 320)]


async def _build():
    http = FakeHttpClient()
    handler = TwilioVoiceHandler(FakeDB(), FakeOrchestrator(), FakeSockets(), http_client=http)
    # Avoid the thinking-sounds background task doing real work.
    handler.thinking_sounds = type("T", (), {"get_thinking_payloads": lambda *a, **k: None, "initialize": lambda: None})()
    return handler, http


async def _run():
    clock = _Clock()
    clock.install()
    handler, http = await _build()
    sid = "s1"
    handler.sessions[sid] = VoiceSessionState(
        session_id=sid,
        patient={"id": 1, "name": "Test", "language": "ml-IN", "doctor_uid": "d1"},
    )
    state = handler.sessions[sid]
    state.opening = False
    state.processing = False
    # Bypass the echo window so VAD runs immediately.
    state.response_audio_end = clock.now()

    fired = False
    events = []

    # Feed speech (~20ms per frame via the clock), then silence.
    for f in _loud_speech_frames(1.5):
        et, immediate, ready = await handler.handle_stream_event(sid, json.dumps(f))
        events.append(et)
        clock.advance(0.02)
        if ready:
            fired = True
            break
    # End-of-turn must NOT fire mid-speech; it fires only after silence.
    assert not fired, "turn fired while the user was still speaking"

    for f in _silence_frames(1.5):
        et, immediate, ready = await handler.handle_stream_event(sid, json.dumps(f))
        clock.advance(0.02)
        if ready:
            fired = True
            break
    assert fired, f"turn never fired after the user stopped speaking; events={events[:3]}"

    # Now run the actual processing pipeline and collect outbound media.
    out_chunks = []
    async for out in handler.process_audio_turn(sid):
        if out:
            out_chunks.append(out)
    assert out_chunks, "process_audio_turn yielded no outbound audio"
    assert any(o.get("event") == "media" for o in out_chunks), "no media event produced"
    print("STT received language_code:", http.last_stt_payload.get("language_code"))
    print("Outbound events:", len(out_chunks))


def test_voice_turn_fires_after_speech():
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Regression: a garbled/empty first reply must STILL speak, not go silent.
# A quiet first utterance used to yield should_repeat=False + empty text,
# fall through to an empty TTS, and the call would die after the greeting.
# ---------------------------------------------------------------------------
class _EmptySTTClient(FakeHttpClient):
    async def post(self, url, headers=None, files=None, data=None, json=None, timeout=None):
        if "speech-to-text" in url:
            return _FakeResp(200, {
                "transcript": "", "language_code": "ml-IN", "language_probability": 0.9,
            })
        return await super().post(url, headers=headers, files=files, data=data, json=json, timeout=timeout)


async def _run_empty():
    http = _EmptySTTClient()
    handler = TwilioVoiceHandler(FakeDB(), FakeOrchestrator(), FakeSockets(), http_client=http)
    handler.thinking_sounds = type("T", (), {"get_thinking_payloads": lambda *a, **k: None, "initialize": lambda: None})()
    sid = "s2"
    handler.sessions[sid] = VoiceSessionState(
        session_id=sid,
        patient={"id": 1, "name": "Test", "language": "ml-IN", "doctor_uid": "d1"},
    )
    state = handler.sessions[sid]
    state.opening = False
    state.processing = False
    state.response_audio_end = (state.response_audio_end)  # echo window already passed

    # Feed loud speech + trailing silence so end-of-turn fires.
    clock = _Clock()
    clock.install()
    state.response_audio_end = clock.now()  # echo window already passed
    fired = False
    for f in _loud_speech_frames(1.5):
        et, immediate, ready = await handler.handle_stream_event(sid, json.dumps(f))
        clock.advance(0.02)
        if ready:
            fired = True
            break
    for f in _silence_frames(1.5):
        et, immediate, ready = await handler.handle_stream_event(sid, json.dumps(f))
        clock.advance(0.02)
        if ready:
            fired = True
            break
    assert fired, "turn never fired on garbled speech"

    out_chunks = []
    async for out in handler.process_audio_turn(sid):
        if out:
            out_chunks.append(out)
    # Must produce audio — a "please repeat" line, NOT silence.
    assert out_chunks, "garbled first reply produced no speech (call would die)"
    assert any(o.get("event") == "media" for o in out_chunks)


def test_voice_turn_speaks_on_empty_transcript():
    asyncio.run(_run_empty())


def test_playback_gate_drops_echo_frames():
    """Frames received while TTS plays must not enter the next STT buffer."""
    async def run() -> None:
        handler, _ = await _build()
        state = VoiceSessionState(
            session_id="echo", patient={"id": 1, "language": "ml-IN"}
        )
        handler.sessions[state.session_id] = state
        state.response_audio_end = datetime.utcnow() + timedelta(seconds=5)
        _, _, ready = await handler.handle_stream_event(
            state.session_id, json.dumps(_loud_speech_frames(0.02)[0])
        )
        assert not ready
        assert not state.buffer
    asyncio.run(run())


def test_emergency_trigger_schedules_cascade_once():
    """The emergency trigger must schedule its coroutine without nesting create_task."""
    class FakeEmergencyCaller:
        def __init__(self):
            self.calls = []

        async def trigger_cascade(self, patient, session_id):
            self.calls.append((patient["id"], session_id))

    async def run() -> None:
        handler, _ = await _build()
        fake = FakeEmergencyCaller()
        handler.emergency_caller = fake
        state = VoiceSessionState(
            session_id="emergency", patient={"id": 17, "language": "ml-IN"}
        )
        handler._trigger_emergency(state)
        await asyncio.sleep(0)
        assert fake.calls == [(17, "emergency")]

    asyncio.run(run())


def test_emergency_silence_does_not_authorize_call():
    """An empty response to an emergency offer must not create a doctor call."""
    class FakeEmergencyCaller:
        def __init__(self):
            self.calls = []

        async def trigger_cascade(self, patient, session_id):
            self.calls.append((patient["id"], session_id))

    async def run() -> None:
        handler, _ = await _build()
        fake = FakeEmergencyCaller()
        handler.emergency_caller = fake
        state = VoiceSessionState(
            session_id="no-consent", patient={"id": 18, "language": "ml-IN"},
            emergency_pending=True,
        )
        await handler._resolve_emergency_response(state, "", "ml-IN")
        await asyncio.sleep(0)
        assert not fake.calls

    asyncio.run(run())


def test_detection_catches_natural_call_phrasings():
    """Regression: natural Malayalam call requests must be detected.

    The live log showed the patient say "എനിക്ക് ഭയങ്കര ഹൃദയവേദന. ഡോക്ടറിനെ
    ഒന്ന് വിളിക്കാമോ?" (terrible heart pain, can you call the doctor?) which the
    old exact-phrase markers missed, so the companion only role-played calling.
    Broad root-word matching must catch it.
    """
    phrase = "എനിക്ക് ഭയങ്കര ഹൃദയവേദന. ഡോക്ടറിനെ ഒന്ന് വിളിക്കാമോ?"
    assert TwilioVoiceHandler._requests_doctor_call(phrase) is True
    assert TwilioVoiceHandler._is_red_flag(phrase) is True
    # "ഡോക്ടറിനെ വിളിക്കാമോ" (dative + "വിളിക്കാമോ") is the variant that broke before.
    assert TwilioVoiceHandler._requests_doctor_call("ഡോക്ടറിനെ ഒന്ന് വിളിക്കാമോ?") is True
    # Heart pain without an explicit "call" must still be a red flag.
    assert TwilioVoiceHandler._is_red_flag("എനിക്ക് നെഞ്ച് വേദനിക്കുന്നു") is True


if __name__ == "__main__":
    for name in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        name()
        print(f"PASS {name.__name__}")
