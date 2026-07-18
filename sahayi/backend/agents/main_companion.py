# ============================================
# AGENT: MainCompanionAgent
# ROLE: Hold a warm, friend-like conversation with the patient in their language
# TRIGGERS: Every patient turn after signal extraction and risk calculation
# OUTPUTS: CompanionReply dataclass for the patient-facing voice response
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

from datetime import datetime, timedelta

from contracts.agents import CompanionReply
from core.ai import OpenAIClient, ThinkingLevel
from intelligence.memory_manager import MemoryManager
from utils.logger import get_logger

# Maximum turns of conversation we keep in the live prompt window. This bounds
# both latency and token cost while still giving the model recent context.
_MAX_HISTORY_TURNS = 8

# Friendly companion system prompt. Sahayi never declares itself an AI or a
# medical assistant — it is just Sahayi, a caring presence that checks in.
_COMPANION_SYSTEM_PROMPT = """You are Sahayi — a warm, caring companion who checks in on people managing their health at home in rural Kerala. You are NOT a doctor and you never give medical advice or diagnoses. You are like a kind neighbour or grandchild who calls to see how someone is doing.

This is an ONGOING, natural phone conversation — not a survey, not a form. You already know this person and they know you.

LANGUAGE — absolute, non-negotiable rule:
- You MUST write your entire reply in exactly this language: {reply_language}. Same script. If {reply_language} is "ml-IN" you MUST reply in Malayalam script. If "hi-IN", Hindi script. Never English unless {reply_language} is "en-IN".
- The patient is speaking {reply_language}. Do NOT switch to English. Do NOT mix languages. Every word must be in {reply_language}.
Example (do not copy, just match the language): if {reply_language} is ml-IN, a good reply is "അതേ, ചേച്ചി. ഇന്ന് കുറച്ച് ക്ഷീണം തോന്നുന്നുണ്ടോ?" — never an English sentence.

CONTINUITY — sound like a real continuing chat:
- This is turn {turn_number} of the call. {first_turn_note}
- Pick up on what the patient just said. React to it like a person: echo a feeling ("അത് കേട്ടപ്പോൾ സങ്കടം തോന്നി"), build on it, refer back to earlier in THIS call when natural.
- NEVER re-greet, never say "hello" or any greeting word again after the first turn. Just keep talking.
- NEVER ask the same thing twice. {repeat_note}

ABSOLUTE TRUTH RULE — never hallucinate:
- You must ONLY respond to what the patient has ACTUALLY said in this call. You have the transcript; if it is not in the transcript or memory, it did not happen.
- NEVER invent words, questions, events, symptoms, or things the patient "just told you". Do not pretend to have heard something they did not say.
- If you are unsure what the patient said, ask them to repeat — never guess or fabricate a response to silence.
- Never finish the patient's sentence for them or assume an answer they did not give.

Speak like a real person, not a helper bot:
- Talk the way a close friend or family member would — casual, gentle, easy. Use the patient's name like you actually know them. A small "chechi", "mone", "etalé" or similar warmth is good when it fits the language.
- Keep it SHORT and spoken-aloud natural — one or two sentences. No lists, no bullet points, no "here are 3 things". Just talk.
- Sound human: it's fine to pause, use a natural filler, or laugh gently. Use everyday words, not textbook words. Don't be polished or scripted.
- Never say "I am an AI", "as an assistant", "I cannot diagnose", "as a language model", or anything clinical or corporate. Never summarise or give tips in a robot voice.
- Ask at most ONE soft follow-up, and only if the patient hasn't already answered it. If they already told you how they feel, don't ask again — respond to what they said instead.
- If they mention something worrying (chest pain, breathlessness, fainting), stay calm and caring, and gently suggest checking with their doctor — like a worried loved one would, never a lecture.

EMERGENCIES ARE SERIOUS — never brush them off:
- If the patient says they want to call the doctor, or describes a serious symptom (chest pain, cannot breathe, fainting, severe bleeding, unconscious), treat it as URGENT. Do NOT argue, downplay, or keep chatting. The system will call the doctor for them right away — your job is to stay calm, reassure them ("Don't worry, I'm calling the doctor now"), and keep them talking gently until help is arranged. Never respond to an emergency request with small talk or another question.

TIME AND DATE AWARENESS — extremely important:
- The current date and time are given below (India time). You MUST keep track of this. Only ask about the PRESENT or the RECENT PAST that the patient has already mentioned in this call.
- NEVER ask about the future or a specific past date unless the patient brought it up first. For example, do NOT ask "how was your sleep tomorrow" or "did you take your medicine yesterday morning" out of nowhere. If you want to ask about sleep or medicine, ask about RIGHT NOW or TODAY, in a natural way (e.g. "how did you sleep last night?" during the day, or "are you resting now?").
- Do not invent days, dates, or times. If unsure what day it is, just talk about how they feel right now.

What you know about the patient (use it to sound like you remember them, not to instruct):
{memory_context}

Current date and time (India): {current_datetime}. Time of day: {time_of_day}.{greeting_note}

Lessons we have learned from past mistakes (follow these gently, they are just guardrails):
{lessons_context}

Respond ONLY with the spoken reply in {reply_language}. No preamble, no quotes, no English."""


class MainCompanionAgent:
    """Agent that crafts the patient-facing reply as a warm companion."""

    def __init__(self) -> None:
        """Initialise the companion dependencies.

        Args:
            None: Uses the shared Sarvam (OpenAI-compatible) helper and logger.
        Returns:
            None.
        Agent:
            MainCompanionAgent
        """

        self.gemini = OpenAIClient(thinking_level=ThinkingLevel.MINIMAL)
        self.memory = MemoryManager(self._database_placeholder())
        self.logger = get_logger("sahayi.main_companion")

    def _database_placeholder(self):
        # Resolved lazily via set_database to avoid import-time DB coupling.
        return _DatabaseProxy()

    def set_database(self, database) -> None:
        """Inject the database gateway after construction.

        Args:
            database: Shared database gateway instance.
        Returns:
            None.
        Agent:
            MainCompanionAgent
        """

        self._db = database
        self.memory.database = database

    async def respond(self, patient_profile: dict, session_history: list[str], patient_text: str, lessons: str = "", detected_language: str | None = None, is_first_turn: bool = True, last_question: str = "") -> CompanionReply:
        """Generate a warm, companion-style reply in the patient's language.

        Args:
            patient_profile: Patient profile dictionary.
            session_history: Prior conversation turns for context.
            patient_text: Latest patient turn.
            lessons: Compact past-mistake lessons to gently follow.
            detected_language: Language the patient actually spoke this turn
                (from STT). Overrides the profile default so the reply always
                matches what the patient said.
            is_first_turn: Whether this is the opening turn of the call.
            last_question: The question Sahayi asked on the previous turn, so it
                is never repeated when the patient has already answered.
        Returns:
            Typed companion reply.
        Agent:
            MainCompanionAgent
        """

        self.logger.info("Main companion activated | patient_id=%s | trigger=patient_turn", patient_profile.get("id"))
        history = " | ".join(session_history[-_MAX_HISTORY_TURNS:])
        fallback = self._fallback_reply(patient_profile, patient_text, detected_language)
        # Always reply in the language the patient actually spoke this turn,
        # falling back to the profile default only when detection is missing.
        reply_lang = detected_language or patient_profile.get("language", "ml-IN") or "ml-IN"

        memory_context = ""
        if getattr(self, "_db", None) is not None:
            memory_context = await self.memory.get_context_string(patient_profile.get("id"))

        time_of_day = self._time_of_day()
        current_datetime = self._current_datetime_ist()
        turn_number = max(1, len(session_history) // 2 + 1)
        first_turn_note = (
            "This is the FIRST turn of a brand-new call. Start by warmly wishing the patient "
            "using the time of day (good morning / evening etc. in their language) and their name, "
            "then naturally weave in something you remember about them from past calls if you have any. "
            "Keep it to one or two sentences — like a loved one calling to check in."
            if is_first_turn else
            "This is NOT the first turn — do not greet or re-wish, just continue the chat."
        )
        greeting_note = (
            " Open the call with a warm time-of-day wish (e.g. good morning/evening in their language) and their name."
            if is_first_turn else
            " Do NOT greet — the call already started."
        )
        repeat_note = (
            "There is no previous question yet."
            if not last_question else
            f"The patient was already asked this last turn: \"{last_question}\". "
            f"If they clearly answered it, do NOT ask it again — respond to their answer instead."
        )
        system_prompt = _COMPANION_SYSTEM_PROMPT.format(
            memory_context=memory_context or "Nothing remembered yet — get to know them gently.",
            time_of_day=time_of_day,
            current_datetime=current_datetime,
            lessons_context=lessons or "None yet.",
            reply_language=reply_lang,
            turn_number=turn_number,
            first_turn_note=first_turn_note,
            greeting_note=greeting_note,
            repeat_note=repeat_note,
        )

        # Give the model enough room to finish a full sentence so the spoken
        # reply is never cut off mid-thought. Short turns stay brief via the
        # prompt, but the token budget must not truncate the TTS clip.
        max_tokens = 220 if len(patient_text.split()) <= 6 else 320

        prompt = f"Patient profile: {patient_profile}\nConversation so far: {history}\nLatest from patient: {patient_text}"
        text = await self.gemini.ask_text(
            system_prompt,
            prompt,
            fallback,
            max_tokens=max_tokens,
        )

        # Hard language lock: sarvam-30b occasionally drifts to English. If the
        # target is a non-English Indic language and the reply is mostly Latin
        # script / ASCII English, force a strict retry, then fall back to a
        # templated reply in the correct language so the patient never hears English.
        if reply_lang != "en-IN" and self._looks_english(text):
            self.logger.warning("Language drift detected (English in %s reply) — enforcing %s", reply_lang, reply_lang)
            strict = system_prompt + "\n\nCRITICAL: your last reply was in the wrong language. You MUST reply ONLY in " + reply_lang + ". No English words at all."
            retry = await self.gemini.ask_text(strict, prompt, fallback, max_tokens=max_tokens)
            text = retry if not self._looks_english(retry) else fallback

        # Fire-and-forget memory extraction so it never blocks the reply.
        if getattr(self, "_db", None) is not None:
            import asyncio
            asyncio.create_task(self.memory.extract_and_store(patient_profile.get("id"), patient_text, text))
        return CompanionReply(text=text, used_context=[patient_profile.get("name", ""), history, patient_text])

    @staticmethod
    def _looks_english(text: str) -> bool:
        """Heuristically detect whether a reply drifted into English/Latin script.

        Used only to enforce a hard language lock for non-English target
        languages — it is deliberately conservative and never triggers for
        en-IN or for ASCII-free Indic replies.

        Args:
            text: Candidate reply text.
        Returns:
            True when the text is predominantly Latin/English script.
        Agent:
            MainCompanionAgent
        """

        stripped = (text or "").strip()
        if not stripped:
            return False
        # Count characters outside the common Indic Unicode ranges. This catches
        # drift to Latin script while ignoring punctuation/digits/spaces.
        non_indic = 0
        total = 0
        for ch in stripped:
            if ch.isspace() or ch in ".,!?;:()[]{}'\"-":
                continue
            total += 1
            # Indic blocks: Malayalam, Devanagari, Tamil, Telugu, Kannada, Bengali,
            # Gujarati, Punjabi, Urdu, Oriya, etc. (covers all Sarvam Indic codes).
            if not (
                "\u0D00" <= ch <= "\u0D7F"  # Malayalam
                or "\u0900" <= ch <= "\u097F"  # Devanagari (hi, mr, ne, etc.)
                or "\u0B80" <= ch <= "\u0BFF"  # Tamil
                or "\u0C00" <= ch <= "\u0C7F"  # Telugu
                or "\u0C80" <= ch <= "\u0CFF"  # Kannada
                or "\u0980" <= ch <= "\u09FF"  # Bengali/Assamese
                or "\u0A80" <= ch <= "\u0AFF"  # Gujarati
                or "\u0A00" <= ch <= "\u0A7F"  # Punjabi (Gurmukhi)
                or "\u0600" <= ch <= "\u06FF"  # Arabic/Urdu
                or "\u0B00" <= ch <= "\u0B7F"  # Oriya
            ):
                non_indic += 1
        if total == 0:
            return False
        return non_indic / total > 0.5

    @staticmethod
    def last_question(reply_text: str) -> str:
        """Extract the question Sahayi just asked, if any, for repeat-suppression.

        Args:
            reply_text: The companion's reply this turn.
        Returns:
            The trailing question sentence (stripped of the leading "Sahayi: "),
            or "" when the reply contained no question.
        Agent:
            MainCompanionAgent
        """

        if not reply_text or "?" not in reply_text:
            return ""
        # Take the last sentence containing a question mark.
        parts = reply_text.split("?")
        last = parts[-2] if len(parts) >= 2 else parts[0]
        sentence = last.split("।")[-1].split(".")[-1].strip()
        return sentence + "?" if sentence else ""

    @staticmethod
    def _time_of_day() -> str:
        """Return a coarse IST time-of-day label for prompt personalisation.

        Args:
            None: Uses the current UTC time with a +5:30 IST offset.
        Returns:
            One of 'morning', 'afternoon', 'evening', 'night'.
        Agent:
            MainCompanionAgent
        """

        hour = (datetime.utcnow().hour + 5) % 24
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 22:
            return "evening"
        return "night"

    @staticmethod
    def _current_datetime_ist() -> str:
        """Return the current date and time in India (IST) for prompt context.

        Args:
            None: Computes IST from the current UTC time with a +5:30 offset.
        Returns:
            Human-readable IST date-time string (e.g. "Monday, 19 July 2026, 4:30 PM IST").
        Agent:
            MainCompanionAgent
        """

        ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
        return ist.strftime("%A, %d %B %Y, %I:%M %p IST")

    def _fallback_reply(self, patient_profile: dict, patient_text: str, detected_language: str | None = None) -> str:
        """Build a deterministic warm fallback reply.

        Args:
            patient_profile: Patient profile dictionary.
            patient_text: Latest patient turn.
            detected_language: Language the patient spoke; overrides default.
        Returns:
            Safe fallback text in the patient's language.
        Agent:
            MainCompanionAgent
        """

        name = patient_profile.get("name", "സുഹൃത്തെ")
        lang = detected_language or patient_profile.get("language", "ml-IN") or "ml-IN"
        # When this is the opening line (no patient text yet), use a soft,
        # natural check-in that doesn't reference itself or sound canned.
        if not patient_text or not patient_text.strip():
            openers = {
                "ml-IN": f"{name}, സുഖമാണേല്ലേ? ഇന്ന് എങ്ങനെയുണ്ട്?",
                "hi-IN": f"{name}, सब ठीक है? आज कैसे हैं आप?",
                "ta-IN": f"{name}, நலமா? இன்னிக்கி எப்படி இருக்கிங்க?",
                "te-IN": f"{name}, అల్లి ఉన్నారా? ఈరోజు ఎలా ఉన్నారు?",
                "kn-IN": f"{name}, ಚೆನ್ನಾಗಿದ್ದೀರಾ? ಇವತ್ತು ಹೇಗಿದ್ದೀರಿ?",
            }
            return openers.get(lang, openers["ml-IN"])
        fallbacks = {
            "ml-IN": f"{name}, ഞാൻ കേൾക്കുന്നു. ഇനി എന്താണ് പറയാനുള്ളത്?",
            "hi-IN": f"{name}, मैं सुन रहा हूँ। अब और क्या बताएँगे?",
            "ta-IN": f"{name}, நான் கேட்கிறேன். இனி என்ன சொல்லணும்?",
            "te-IN": f"{name}, నేను వింటున్నా. ఇంకా ఏం చెప్పాలి?",
            "kn-IN": f"{name}, ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ. ಇನ್ನೇನು ಹೇಳಬೇಕು?",
        }
        if any(word in patient_text.lower() for word in ["pain", "നെഞ്ച്", "breathless", "ശ്വാസം"]):
            urgent = {
                "ml-IN": f"{name}, ഞാൻ കേട്ടു. ഇത് ശ്രദ്ധിക്കേണ്ടതാണ്. നിങ്ങളുടെ ഡോക്ടറെ വിളിക്കണമോ എന്ന് പറയൂ.",
                "hi-IN": f"{name}, मैंने सुना। इसे देखना ज़रूरी है। बताइए क्या डॉक्टर को कॉल करूँ?",
                "ta-IN": f"{name}, நான் கேட்டேன். இதை பார்க்கணும். டாக்டரை கூப்பிடணுமா சொல்லுங்க.",
                "te-IN": f"{name}, విన్నా. దీన్ని చూడాలి. డాక్టర్‌ను కాల్ చేయాలా చెప్పండి.",
                "kn-IN": f"{name}, ಕೇಳಿದೆ. ನೋಡಬೇಕಾದ್ದು. ಡಾಕ್ಟರ್‌ರನ್ನು ಕರೆಯಲಾ ಹೇಳಿ.",
            }
            return urgent.get(lang, urgent["ml-IN"])
        return fallbacks.get(lang, fallbacks["ml-IN"])


class _DatabaseProxy:
    """Minimal placeholder so MemoryManager can be constructed without a DB.

    The real gateway is injected via ``set_database`` before any call.
    """

    async def get_memory_notes(self, patient_id: int) -> list:
        return []

    async def add_memory_note(self, patient_id: int, category: str, content: str):
        return None

    async def prune_memory_notes(self, patient_id: int, keep: int = 5) -> None:
        return None
