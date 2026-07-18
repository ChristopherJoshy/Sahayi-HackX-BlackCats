# ============================================
# AGENT: RelativeReporter
# ROLE: Proactively push a short clinical care update to the patient's relative
# TRIGGERS: Risk crossing yellow/red, session end, or missed check-in
# OUTPUTS: WhatsApp message to the primary relative (clinical summary only)
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

from typing import Any

from agents.family_alert import FamilyAlertAgent
from core.ai import OpenAIClient, ThinkingLevel
from utils.logger import get_logger


class RelativeReporter:
    """Agent that reports patient status to the family relative over WhatsApp.

    On risk/session events the orchestrator calls this agent, which composes a
    short, warm, CLINICAL summary (risk level + observed signals, never raw
    patient messages) and sends it to the patient's primary relative. It reuses
    the existing FamilyAlertAgent for the actual WhatsApp delivery.
    """

    def __init__(self, database: Any, family_alert: FamilyAlertAgent) -> None:
        """Initialise the relative reporter.

        Args:
            database: Shared database gateway instance.
            family_alert: FamilyAlertAgent used for WhatsApp delivery.
        Returns:
            None.
        Agent:
            RelativeReporter
        """

        self.database = database
        self.family_alert = family_alert
        self.ai = OpenAIClient(thinking_level=ThinkingLevel.LOW)
        self.logger = get_logger("sahayi.relative_reporter")

    async def report_event(self, patient: dict, risk_score: float, reason: str, observed_signals: str = "") -> None:
        """Push a care update to the patient's primary relative.

        Args:
            patient: Patient profile dictionary.
            risk_score: Current risk score (0-1).
            reason: Short trigger reason (e.g. "risk increased", "check-in done").
            observed_signals: Optional clinical signal summary string.
        Returns:
            None.
        Agent:
            RelativeReporter
        """

        relatives = patient.get("relatives") or []
        if not relatives:
            self.logger.info("Relative report skipped | no relatives | patient_id=%s", patient.get("id"))
            return
        relative_name = relatives[0].get("name") or "Family Member"

        # Compose a short, warm, clinical-only summary (never raw transcripts).
        summary = await self._compose(patient, risk_score, reason, observed_signals)
        message = f"Hello {relative_name}, a quick update on {patient.get('name')}: {summary}"
        await self.family_alert.send(patient, message, doctor_trigger=False)

    async def _compose(self, patient: dict, risk_score: float, reason: str, observed_signals: str) -> str:
        """Generate a one-to-two sentence clinical summary for the relative.

        Args:
            patient: Patient profile dictionary.
            risk_score: Current risk score (0-1).
            reason: Trigger reason.
            observed_signals: Clinical signal summary string.
        Returns:
            Short clinical summary sentence(s).
        Agent:
            RelativeReporter
        """

        level = "low" if risk_score < 0.4 else "moderate" if risk_score < 0.7 else "high"
        prompt = (
            f"Write a SHORT, warm, human WhatsApp message from Sahayi to a family member about {patient.get('name')}.\n"
            f"Keep it to 1-2 sentences, like a kind neighbour would text. No headings, no lists, no 'risk level' wording.\n"
            f"Mention only the simple fact that matters (e.g. feeling a bit low today / we're keeping an eye / please check in) based on: {observed_signals or 'routine check-in'}.\n"
            f"End by gently suggesting they call {patient.get('name')} or the doctor if they're worried. Sound like a person, not a report."
        )
        system = "You write brief, warm family messages for a Kerala companion. Plain human language, no clinical or corporate phrasing, under 35 words."
        text = await self.ai.ask_text(system, prompt, fallback=f"Just a note — {patient.get('name')} had a quiet check-in today. Sahayi is with them, and we'll reach out if anything changes.", max_tokens=160)
        return text