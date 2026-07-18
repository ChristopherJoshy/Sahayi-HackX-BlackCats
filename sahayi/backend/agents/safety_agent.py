# ============================================
# AGENT: SafetyAgent
# ROLE: Review all patient-facing responses for unsafe or unsupported advice
# TRIGGERS: Every companion response before it is returned to the patient
# OUTPUTS: SafetyReview dataclass with safe fallback when needed
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

from contracts.agents import SafetyReview
from core.ai import OpenAIClient, ThinkingLevel
from utils.logger import get_logger

SAFE_FALLBACKS = {
    "ml-IN": "ക്ഷമിക്കണം, കൃത്യമായ വൈദ്യോപദേശത്തിന് ദയവായി നിങ്ങളുടെ ഡോക്ടറെ സമീപിക്കുക.",
    "hi-IN": "माफ़ करें, सटीक चिकित्सा सलाह के लिए कृपया अपने डॉक्टर से संपर्क करें।",
    "en-IN": "I understand. For specific medical advice, please speak with your doctor.",
    "ta-IN": "மன்னிக்கவும், குறிப்பிட்ட மருத்துவ ஆலோசனைக்கு தயவுசெய்து உங்கள் மருத்துவரை அணுகவும்.",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ನಿರ್ದಿಷ್ಟ ವೈದ್ಯಕೀಯ ಸಲಹೆಗಾಗಿ ದಯವಿಟ್ಟು ನಿಮ್ಮ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
    "bn-IN": "দুঃখিত, নির্দিষ্ট চিকিৎসা পরামর্শের জন্য দয়া করে আপনার ডাক্তারের সাথে কথা বলুন।",
    "te-IN": "క్షమించండి, నిర్దిష్ట వైద్య సలహా కోసం దయచేసి మీ డాక్టర్‌ని సంప్రదించండి.",
    "mr-IN": "क्षमस्व, विशिष्ट वैद्यकीय सल्ल्यासाठी कृपया आपल्या डॉक्टरांशी संपर्क साधा.",
    "gu-IN": "માફ કરશો, ચોક્કસ તબીબી સલાહ માટે કૃપા કરીને તમારા ડૉક્ટરની સલાહ લો.",
    "pa-IN": "معاف ਕਰਨਾ, ਖਾਸ ਡਾਕਟरी ਸਲਾਹ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੇ ਡਾਕਟਰ ਨਾਲ ਗੱਲ ਕਰੋ।",
    "ur-IN": "معاف کیجئے، مخصوص طبی مشورے کے لیے براہ کرم اپنے ڈاکٹر سے بات کریں۔"
}


class SafetyAgent:
    """Agent that guards every patient-facing response."""

    def __init__(self) -> None:
        """Initialise the safety-review dependencies.

        Args:
            None: Uses the shared OpenAI helper and logger.
        Returns:
            None.
        Agent:
            SafetyAgent
        """

        self.gemini = OpenAIClient(thinking_level=ThinkingLevel.LOW)
        self.logger = get_logger("sahayi.safety_agent")

    async def review(self, response_text: str, rag_context: list[str], language_code: str = "en-IN") -> SafetyReview:
        """Review a patient-facing reply and return a safe variant.

        Uses a fast heuristic for real-time safety to avoid LLM latency.

        Args:
            response_text: Proposed response text.
            rag_context: Context strings used to build the reply.
            language_code: Patient's language code for fallback translation.
        Returns:
            Typed safety review result.
        Agent:
            SafetyAgent
        """

        self.logger.info("Safety agent activated (heuristic only) | trigger=patient_response")
        
        # Fast real-time heuristic
        result = self._heuristic_review(response_text)
        verdict = str(result.get("verdict", "SAFE")).upper()
        confidence = float(result.get("confidence", 0.8))
        
        unsafe = verdict != "SAFE"
        fallback_text = SAFE_FALLBACKS.get(language_code, SAFE_FALLBACKS["en-IN"])
        
        safe_response = fallback_text if unsafe else response_text
        flagged = [str(item) for item in result.get("flagged_claims", [])]
        
        # We can kick off an async LLM check here for monitoring later if needed,
        # but the real-time path must be fast.
        return SafetyReview(
            verdict="UNSAFE" if unsafe else "SAFE", 
            confidence=confidence, 
            flagged_claims=flagged, 
            safe_response=safe_response
        )

    def _heuristic_review(self, response_text: str) -> dict:
        """Apply a conservative local safety heuristic.

        Args:
            response_text: Proposed response text.
        Returns:
            Fallback JSON-like review payload.
        Agent:
            SafetyAgent
        """

        lowered = response_text.lower()
        risky = any(token in lowered for token in ["you have", "diagnosis", "stop taking", "definitely"])
        return {"verdict": "UNSAFE" if risky else "SAFE", "confidence": 0.55 if risky else 0.82, "flagged_claims": ["unsupported claim"] if risky else []}
