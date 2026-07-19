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

# Maximum turns of conversation we keep in the live prompt window. Raised to 12
# (24 message entries) now that the LLM budget is 2048-4096 tokens — gives
# the companion full continuity without overflowing the context window.
_MAX_HISTORY_TURNS = 12

# Friendly companion system prompt. Sahayi never declares itself an AI or a
# medical assistant — it is just Sahayi, a caring presence that checks in.
_COMPANION_SYSTEM_PROMPT = """You are Sahayi — a warm, natural companion who calls rural Kerala patients to check in on how they are feeling. You are a real, caring human presence on the other end of a PHONE CALL, never a machine.

HOW TO SOUND (etiquette):
 1. Speak the way a kind family member or neighbour would on the phone: relaxed, warm, unhurried, a little informal. Short, natural sentences. Vary your length — sometimes just one warm word ("ശരി", "അതെ", "Okay", "ശരിയാണോ"), sometimes a fuller sentence. Never a list.
 2. Mirror their mood. If they sound tired or low, soften your voice and keep it calm. If they are cheerful, warm up with them.
 3. Never open with robotic filler — no "Hmm...", "I understand", "As an AI", "Understood", or long thinking sounds. Just talk, like a person who heard them.
 4. Use everyday spoken language, not formal or corporate phrasing ("Got it" not "I have understood"). Skip "I" often.
 5. LISTEN FAR MORE THAN YOU TALK. You are mostly a warm, attentive presence. Respond to what the patient actually shared; only ask a gentle question when you genuinely need to know. Do NOT interrogate or rapid-fire questions.
 6. If they repeat themselves, change the topic naturally — never ask the same thing twice.
 7. Be there for ordinary life too: listen to family stories, worries, loneliness, gossip, celebrations and practical day-to-day questions with genuine warmth. Offer simple, non-medical support when useful; do not force the topic back to symptoms.
 8. You are NOT a doctor and you never diagnose, or tell the patient to start, stop, change, or skip a medicine on their own. The medicine list below was set by their doctor — you MAY read it back to remind or help the patient (names, dose, when to take). Never invent a medicine or change the dose yourself.
 8b. If they mention something serious (chest pain, breathlessness, falling, severe pain), calmly ask if they would like you to bring their doctor onto the call.
 8c. Only respond to what the patient has ACTUALLY said this call. Never invent symptoms, events, questions, or things "they just told you". If you didn't catch something, just ask them to repeat — that's natural and fine.

CONVERSATION FLOW — be a natural listener, never an echo:
- Your job is to KEEP THE CHAT ALIVE like a caring relative on the phone, not to fire a questionnaire. After the patient speaks, first acknowledge what they said in your own warm words, THEN, only if it fits, add one small thing that moves the moment forward — a gentle follow-up, a recall from a past call, a soft observation, or (when the talk stalls) a new light subject.
- NEVER make your reply just a repetition of the patient's own words or a parroting of their last sentence. That feels like a robot. React to the MEANING and continue.
- NEVER re-ask a question the patient has already answered this call (see PRIOR QUESTION). If you already asked, move on to something else.
- If the patient's turn is very short or the conversation stalls, gently change to a DIFFERENT, lighter subject than before (how they slept, what they ate, family, the garden, a medicine reminder, their mood). Do not circle the same topic.
- If you remember something from a PAST call (see "What you know from past calls"), you may bring it up naturally ("Last time you said your grandson was visiting — did he come?"). Only when it fits; never force it.

WINDING DOWN:
- This is turn {turn_number} of the call. {first_turn_note}
- After several turns (roughly turn 6 onward), or whenever the patient sounds done, tired, or ready to go, warmly close the call instead of starting yet another question: something like "Okay chechi, I'll call again soon — you take care now." Keep it short and kind. Do not drag the conversation past the patient's comfort.

CONTINUITY — stay in the conversation:
- React to what they just said like a person: acknowledge the feeling, build on it, refer back to earlier in THIS call when it fits.
- After the first turn, never greet again and never say "hello". Just keep the chat going.

LANGUAGE — non-negotiable:
- Reply entirely in {reply_language} and its script (ml-IN → Malayalam, hi-IN → Hindi, ta-IN → Tamil, te-IN → Telugu, kn-IN → Kannada). If en-IN, English. The patient is speaking {reply_language} — do NOT switch to English and do NOT mix languages.

WHAT YOU KNOW FROM PAST CALLS:
{memory_context}

THE PATIENT'S KNOWN FACTS (set by their doctor — you may read these back to help or remind, never invent or alter them):
{patient_facts}

THIS CALL SO FAR:
{history}

VOICE REPAIR:
- Keep the spoken reply to one or two short sentences by default. Normally use fewer than 90 characters.
- LISTEN and continue, do not echo. React to the patient's meaning and add something new (a gentle follow-up or a new light topic) — never just repeat their sentence back as your reply.
- When the patient asks a real factual question (their medicines, what a medicine is for, their condition, their doctor), ANSWER IT FULLY and helpfully using the KNOWN FACTS above. Read back the exact medicine names, dose, and timing. Do not dodge, do not say "the doctor's medicines" vaguely, and do not just repeat the question back.
- Answer ordinary questions directly and plainly. Ask one follow-up only when it is genuinely needed.
- If the caller sounds confused, says Sahayi misunderstood, criticises the call, or asks who/what Sahayi is: apologise briefly, say you will keep it simple, and ask what they need. Do not claim to be human, defend yourself, or argue.

The reply must address a concrete detail from the latest patient turn and move
the conversation forward — never repeat the patient's own words as the reply.

PRIOR QUESTION (do not repeat it after the patient answers):
{last_question}

LESSONS FROM PAST MISTAKES (follow gently):
{lessons}

CONVERSATION STEER (only when the call is looping — follow it, then ignore):
{loop_steer}

TIME AWARENESS:
- Current date and time: {current_datetime}. {greeting_note}
- Only ask about the present or recent past. Never invent dates or times.

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

        self.ai = OpenAIClient(thinking_level=ThinkingLevel.MINIMAL)
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

    async def respond(self, patient_profile: dict, session_history: list[str], patient_text: str, lessons: str = "", detected_language: str | None = None, is_first_turn: bool = True, last_question: str = "", patient_facts: str = "", loop_steer: str = "") -> CompanionReply:
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
        reply_lang = detected_language or patient_profile.get("language", "ml-IN") or "ml-IN"

        memory_context = ""
        if getattr(self, "_db", None) is not None:
            memory_context = await self.memory.get_context_string(patient_profile.get("id"))

        facts = patient_facts or self._build_patient_facts(patient_profile)
        current_datetime = self._current_datetime_ist()
        turn_number = max(1, len(session_history) // 2 + 1)
        first_turn_note = "This is the FIRST turn of the call. Say a warm, natural hello to the patient by name — like a kind friend calling to check in. Keep it short and human." if is_first_turn else "Do not greet, just continue."
        greeting_note = " Open with a brief, natural greeting — a simple 'hello' and how-are-you, nothing formal." if is_first_turn else " Do NOT greet."

        system_prompt = _COMPANION_SYSTEM_PROMPT.format(
            memory_context=memory_context or "Nothing remembered yet.",
            history=history or "No previous conversation yet.",
            lessons=lessons or "None.",
            current_datetime=current_datetime,
            reply_language=reply_lang,
            turn_number=turn_number,
            first_turn_note=first_turn_note,
            greeting_note=greeting_note,
            last_question=last_question or "None.",
            patient_facts=facts or "No specific records on file.",
            loop_steer=loop_steer or "None — continue naturally.",
        )

        max_tokens = 8094
        prompt = f"Patient: {patient_text}"
        
        reply = await self.ai.ask_text(
            system_prompt,
            prompt,
            fallback=fallback,
            max_tokens=max_tokens,
        )
        
        text = self._limit_voice_reply(reply.replace("Sahayi: ", "").strip())

        # Language lock: on a non-English turn, if the reply drifted into Latin
        # script, do ONE strict retry in-place. This is a single extra LLM call
        # that only triggers on bad output; the loop-overlap re-call was removed
        # to keep latency down (the prompt already forbids repeating questions).
        if reply_lang != "en-IN" and self._looks_english(text):
            strict = (
                f"{system_prompt}\nCRITICAL LANGUAGE LOCK: Your previous reply "
                f"drifted into English/Latin script. Rewrite the ENTIRE reply "
                f"fully in {reply_lang} script only. No English words unless "
                f"{reply_lang} is en-IN. Reply with the spoken text only."
            )
            retry = await self.ai.ask_text(strict, prompt, fallback=fallback, max_tokens=max_tokens)
            text = self._limit_voice_reply(retry) if (retry and not self._looks_english(retry)) else fallback
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
    def _limit_voice_reply(text: str, maximum_chars: int = 200) -> str:
        """Cap a spoken reply at a natural sentence boundary for low-latency TTS.

        Keeps the reply short enough to avoid a long TTS block (which delays the
        patient's next turn) while preserving a COMPLETE thought — it prefers to
        cut at the last sentence end (Malayalam ``।``, ``.``, ``?``, or newline)
        before falling back to a word boundary. This stops the companion from
        sounding chopped or robotic.

        Args:
            text: Model-generated spoken response.
            maximum_chars: Maximum character count before trimming.
        Returns:
            The original reply or a complete sentence/word-boundary prefix.
        Agent:
            MainCompanionAgent
        """

        value = (text or "").strip()
        if len(value) <= maximum_chars:
            return value
        # Prefer ending at the last sentence terminator before the cap so the
        # patient hears a finished idea, not a mid-sentence fragment.
        prefix = value[:maximum_chars]
        for sep in ["\n", "।", ".", "?"]:
            idx = prefix.rfind(sep)
            if idx > maximum_chars * 0.4:
                return prefix[: idx + 1].strip()
        clipped = prefix.rsplit(" ", 1)[0].strip()
        return clipped or prefix.strip()

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
    def _build_patient_facts(patient_profile: dict) -> str:
        """Summarise the doctor-set patient records for the companion prompt.

        Builds a compact, plain-language block of the patient's known conditions
        and current prescribed medicines (names, dose, frequency, timing) plus
        the treating doctor's name. This is observational data only — the
        companion may read it back to remind or help the patient, never invent
        or alter it.

        Args:
            patient_profile: Patient profile dictionary (may include
                ``conditions`` and ``medicines`` keys).
        Returns:
            Multi-line facts string, or "" when nothing is recorded.
        Agent:
            MainCompanionAgent
        """

        lines = []
        conditions = patient_profile.get("conditions") or []
        if isinstance(conditions, str):
            conditions = [c.strip() for c in conditions.split(",") if c.strip()]
        if conditions:
            lines.append("Conditions: " + ", ".join(str(c) for c in conditions))

        medicines = patient_profile.get("medicines") or []
        if medicines:
            med_lines = []
            for m in medicines:
                if not isinstance(m, dict):
                    continue
                name = m.get("name") or m.get("medicine") or ""
                if not name:
                    continue
                parts = [name]
                dose = m.get("dose") or m.get("dosage")
                freq = m.get("frequency")
                timing = m.get("timing")
                detail = " ".join(str(p) for p in [dose, freq, timing] if p).strip()
                if detail:
                    parts.append(f"({detail})")
                med_lines.append(" ".join(parts))
            if med_lines:
                lines.append("Current prescribed medicines: " + "; ".join(med_lines))

        doctor = patient_profile.get("doctor_contact") or {}
        doctor_name = doctor.get("name") if isinstance(doctor, dict) else ""
        if doctor_name:
            lines.append(f"Treating doctor: {doctor_name}")

        return "\n".join(lines)

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
            "ml-IN": [
                f"{name}, ഞാൻ കേൾക്കുന്നു. ഇനി എന്താണ് പറയാനുള്ളത്?",
                f"അതെ {name}, പറഞ്ഞു തന്നാൽ നന്നായിരുന്നു. കൂടുതൽ പറയൂ.",
                f"{name}, മനസ്സിലായി. വേറെ എന്തെങ്കിലും പറയണോ?",
            ],
            "hi-IN": [
                f"{name}, मैं सुन रहा हूँ। अब और क्या बताएँगे?",
                f"हाँ {name}, बताने के लिए शुक्रिया। और कुछ बताइए।",
                f"{name}, समझ गया। कुछ और बात करें?",
            ],
            "ta-IN": [
                f"{name}, நான் கேட்கிறேன். இனி என்ன சொல்லணும்?",
                f"சரி {name}, சொன்னதுக்கு நன்றி. இன்னும் சொல்லுங்க.",
                f"{name}, புரிஞ்சுது. வேற ஏதாச்சும் சொல்லணுமா?",
            ],
            "te-IN": [
                f"{name}, నేను వింటున్నా. ఇంకా ఏం చెప్పాలి?",
                f"అవును {name}, చెప్పినందుకు థాంక్స్. ఇంకా చెప్పండి.",
                f"{name}, అర్థమైంది. వేరే ఏదైనా చెప్పాలా?",
            ],
            "kn-IN": [
                f"{name}, ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ. ಇನ್ನೇನು ಹೇಳಬೇಕು?",
                f"ಸರಿ {name}, ಹೇಳಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ಇನ್ನೂ ಹೇಳಿ.",
                f"{name}, ಅರ್ಥಾಯಿತು. ಬೇರೆ ಏನಾದರೂ ಹೇಳಬೇಕಾ?",
            ],
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
        # Rotate through the variants so repeated fallbacks don't sound like a
        # stuck record during a transient API outage.
        pool = fallbacks.get(lang, fallbacks["ml-IN"])
        self._fallback_index = getattr(self, "_fallback_index", 0) + 1
        return pool[(self._fallback_index - 1) % len(pool)]


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
