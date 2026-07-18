# ============================================
# AGENT: WhatsAppAgent
# ROLE: Hold a warm, friend-like WhatsApp conversation with patient or relative
# TRIGGERS: Incoming Twilio WhatsApp message (text, audio, or prescription image)
# OUTPUTS: Reply text and optional TTS audio bytes
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

import json
import httpx
import uuid
from typing import Any, Optional

from core.ai import OpenAIClient, ThinkingLevel
from core.config import get_settings
from intelligence.memory_manager import MemoryManager
from utils.logger import get_logger
from voice.sarvam_tts import SarvamTTSClient
from voice.sarvam_stt import SarvamSTTClient
from voice.vision import extract_prescription_from_url

# Warm companion prompt for the WhatsApp channel. Sahayi is a caring presence,
# never a clinical assistant. It matches the sender's language and tone.
_WHATSAPP_SYSTEM_PROMPT = """You are Sahayi — a warm, caring companion who checks in on people managing their health at home in rural Kerala. You are NOT a doctor and never give medical advice or diagnoses. You are like a kind neighbour or family member who messages to see how someone is doing.

How you speak:
- Talk like a close friend or family member would — casual, gentle, a little playful. Use the person's name. Match the warmth of someone who genuinely cares.
- Reply in the SAME language and script the person writes or speaks in. If they write Malayalam, reply in Malayalam. If Hindi, reply in Hindi. Never switch to English unless they do.
- Keep it short and natural for chat. One or two sentences is usually enough. Only go longer when they share something deeper or ask a question.
- Never say "I am an AI", "as an assistant", or anything clinical. Just be present and kind.
- If they mention something worrying (chest pain, breathlessness, fainting), stay calm and caring, and gently suggest it may be worth reaching out to their doctor.

If an image is sent, it is likely a prescription — note the medicines kindly and confirm you've saved them.
If a voice note is sent, listen to it and reply to what they said.

What you know about them (use it to sound familiar, never to lecture):
{memory_context}"""


class WhatsAppAgent:
    def __init__(self, database: Any, http_client: httpx.AsyncClient | None = None) -> None:
        self.database = database
        settings = get_settings()
        self.logger = get_logger("sahayi.whatsapp_agent")
        # Text reasoning routes through Sarvam's Indic LLM (OpenAI-compatible).
        self.llm = OpenAIClient(thinking_level=ThinkingLevel.LOW)
        self.memory = MemoryManager(database)
        self.tts = SarvamTTSClient(http_client)
        self.stt = SarvamSTTClient(http_client)

    async def handle_message(self, patient: dict, text: str, media_url: Optional[str] = None, media_type: Optional[str] = None, text_only: bool = False) -> tuple[str, Optional[bytes]]:
        wants_audio_reply = False
        detected_lang = patient.get("language")

        if media_url:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(media_url)
                    response.raise_for_status()
                    media_bytes = response.content

                    if media_type and media_type.startswith("audio/"):
                        wants_audio_reply = True
                        stt_result = await self.stt.transcribe_file(media_bytes, "audio.ogg", media_type, language_code="auto")
                        transcript = str(stt_result.get("text", "")).strip()
                        detected_lang = stt_result.get("language") or patient.get("language")
                        if transcript:
                            text = (text + "\n" + transcript).strip() if text else transcript
                    elif media_type and media_type.startswith("image/"):
                        # Vision is handled by Gemini; extract prescription text and
                        # fold it into the prompt so Sarvam can reply in the user's language.
                        prescription = await extract_prescription_from_url(str(media_url))
                        if prescription.raw_text:
                            text = (text + f"\n[Prescription image]: {prescription.raw_text}").strip()
            except Exception as e:
                self.logger.error(f"Failed to process media: {e}")

        # Pull recent signals and any remembered context for a familiar tone.
        recent_signals = await self.database.recent_signals(patient["id"], days=7)
        signals_text = ", ".join([f"Sev {s.severity} (Fatigue: {s.fatigue})" for s in recent_signals]) if recent_signals else "No recent signals."
        memory_context = await self.memory.get_context_string(patient["id"])

        sender_name = patient.get("sender_name", patient.get("name", "User"))
        sender_role = patient.get("is_relative", False) and "Patient's Relative" or "Patient"

        system_instruction = _WHATSAPP_SYSTEM_PROMPT.format(
            memory_context=memory_context or "Nothing remembered yet — get to know them gently."
        )

        patient_context = f"""
Person you are chatting with: {sender_name} ({sender_role})
Patient name: {patient.get('name')}
Language to reply in: {detected_lang or patient.get('language')}
Conditions: {patient.get('conditions')}
Current Medicines: {json.dumps(patient.get('medicines'))}
Recent Signals: {signals_text}
"""

        reply_text: str = ""
        fallback_reply = "ക്ഷമിക്കണം, എനിക്ക് ഇപ്പോൾ മറുപടി നൽകാൻ കഴിയുന്നില്ല."

        try:
            reply_text = await self.llm.ask_text(
                system_instruction, patient_context + "\nMessage from " + sender_name + ": " + (text or "Hello"), fallback_reply, ThinkingLevel.LOW
            )
            # Fire-and-forget memory extraction.
            import asyncio
            asyncio.create_task(self.memory.extract_and_store(patient["id"], text or "Hello", reply_text))
        except Exception as e:
            self.logger.error(f"WhatsApp generation failed: {e}")
            reply_text = fallback_reply

        audio_bytes = None
        if wants_audio_reply and not text_only:
            try:
                audio_bytes = await self.tts.synthesize(reply_text, detected_lang or None)
            except Exception as e:
                self.logger.error(f"TTS generation failed: {e}")

        return reply_text, audio_bytes

    async def extract_clinical_summary(self, text: str) -> str:
        """Extract only clinical facts from a relative's message for the doctor.

        Strips personal chatter and returns a short clinical summary (symptoms,
        missed doses, concerns, meds). Returns an empty string when nothing
        clinical is found, so the dashboard never shows raw personal messages.

        Args:
            text: Transcribed or typed relative message.
        Returns:
            Short clinical summary, or "" when no clinical content.
        Agent:
            WhatsAppAgent
        """

        if not text or not text.strip():
            return ""
        system = (
            "You extract ONLY clinical facts from a family member's message about a patient. "
            "Return a short bullet-free summary of: reported symptoms, missed medicines/doses, "
            "mood/concern, or new medicines. Use clinical terms, no personal chat. "
            "If there is nothing clinical, return exactly: NONE."
        )
        prompt = f"Message from family member: {text}"
        try:
            result = await self.llm.ask_text(system, prompt, fallback="", max_tokens=200)
        except Exception:
            return ""
        return result.strip() if result.strip().upper() != "NONE" else ""
