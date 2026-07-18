# ============================================
# AGENT: DoctorBrieferAgent
# ROLE: Briefly the on-call doctor when Sahayi escalates a patient emergency
# TRIGGERS: Doctor answers the outbound emergency call
# OUTPUTS: Spoken reply for the doctor (in English, clinical but plain)
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

from core.ai import OpenAIClient, ThinkingLevel
from utils.logger import get_logger


class DoctorBrieferAgent:
    """Agent that talks to the on-call doctor during an emergency escalation.

    When the doctor answers the outbound emergency call, this agent opens with
    a concise briefing (patient name, age context, conditions, the red-flag
    symptom, current risk) and then answers the doctor's follow-up questions
    using the patient's profile and recent call context.
    """

    def __init__(self) -> None:
        """Initialise the doctor briefer dependencies.

        Args:
            None: Uses the shared Sarvam (OpenAI-compatible) helper and logger.
        Returns:
            None.
        Agent:
            DoctorBrieferAgent
        """
        self.gemini = OpenAIClient(thinking_level=ThinkingLevel.LOW)
        self.logger = get_logger("sahayi.doctor_briefer")

    def build_briefing(self, patient: dict, reason: str, risk_score: float, recent_signals: str = "") -> str:
        """Compose the opening briefing line spoken to the doctor.

        Args:
            patient: Patient profile dictionary.
            reason: Why the emergency was triggered (red-flag symptom / request).
            risk_score: Current risk score (0-1).
            recent_signals: Optional recent clinical signal summary.
        Returns:
            A short, spoken English briefing string.
        Agent:
            DoctorBrieferAgent
        """
        name = patient.get("name", "the patient")
        conditions = ", ".join(patient.get("conditions") or []) or "no known chronic conditions on file"
        medicines = ", ".join(
            m.get("name", "") for m in (patient.get("medicines") or []) if isinstance(m, dict)
        ) or "none on file"
        risk_pct = int(round((risk_score or 0.0) * 100))
        brief = (
            f"Hello Doctor, this is Sahayi calling. Your patient {name} may need urgent attention. "
            f"{reason} "
            f"{name} has: {conditions}. Current medicines: {medicines}. "
            f"Current risk score is {risk_pct} percent."
        )
        if recent_signals:
            brief += f" Recent observations: {recent_signals}."
        brief += " What would you like to know?"
        return brief

    async def answer(self, patient: dict, doctor_question: str, history: list[str], reason: str, risk_score: float) -> str:
        """Answer a doctor's follow-up question using patient context.

        Args:
            patient: Patient profile dictionary.
            doctor_question: What the doctor just asked.
            history: Recent doctor/agent exchange for context.
            reason: Why the emergency was triggered.
            risk_score: Current risk score (0-1).
        Returns:
            Spoken English reply for the doctor.
        Agent:
            DoctorBrieferAgent
        """
        name = patient.get("name", "the patient")
        conditions = ", ".join(patient.get("conditions") or []) or "none on file"
        medicines = ", ".join(
            m.get("name", "") for m in (patient.get("medicines") or []) if isinstance(m, dict)
        ) or "none on file"
        age = patient.get("age") or "unknown"
        history_text = " | ".join(history[-6:])
        system = (
            "You are Sahayi, an AI care companion speaking to an on-call DOCTOR during a patient "
            "emergency escalation. Be concise, clinical but plain-spoken, and helpful. Use only the "
            "patient facts provided. Do not invent vitals, labs, or history you were not given. If you "
            "do not know something, say so and suggest the doctor check the patient or the dashboard. "
            "Speak in English, a few sentences max, like a competent nurse handing over a case."
        )
        prompt = (
            f"Patient: {name}, age {age}. Conditions: {conditions}. Medicines: {medicines}. "
            f"Why escalated: {reason}. Risk score: {int(round((risk_score or 0.0) * 100))} percent.\n"
            f"Conversation so far: {history_text}\n"
            f"Doctor asks: {doctor_question}\n"
            f"Answer the doctor briefly using only the above facts."
        )
        fallback = (
            f"I'm sorry Doctor, I only have limited information on {name}. "
            f"The main concern is: {reason}. Please check {name} or the dashboard for full details."
        )
        return await self.gemini.ask_text(system, prompt, fallback, max_tokens=240)
