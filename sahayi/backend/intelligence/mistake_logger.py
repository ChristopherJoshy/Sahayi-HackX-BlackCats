# ============================================
# AGENT: MistakeLogger
# ROLE: Detect and record AI mistakes so the system learns from its own errors
# TRIGGERS: Doctor/guardrail correction, safety override, or explicit feedback
# OUTPUTS: Persisted MistakeNote; exposes lessons to improve future turns
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

from typing import Any

from core.ai import OpenAIClient, ThinkingLevel
from db.database import DatabaseGateway
from utils.logger import get_logger


class MistakeLogger:
    """Agent that turns a correction into a stored, reusable lesson.

    When a doctor overrides a reply, a safety guardrail fires, or explicit
    feedback arrives, this agent summarises the error into a durable
    ``MistakeNote`` and can later surface past lessons as guardrails.
    """

    def __init__(self, database: DatabaseGateway) -> None:
        """Initialise the mistake logger with DB access.

        Args:
            database: Shared database gateway instance.
        Returns:
            None.
        Agent:
            MistakeLogger
        """

        self.database = database
        self.ai = OpenAIClient(thinking_level=ThinkingLevel.LOW)
        self.logger = get_logger("sahayi.mistake_logger")

    async def record(
        self,
        agent: str,
        mistake_type: str,
        context: str,
        error: str,
        correction: str,
        lesson: str | None = None,
        patient_id: int | None = None,
    ) -> Any:
        """Persist a mistake and derive a generalised lesson when missing.

        Args:
            agent: Agent name that made the mistake.
            mistake_type: Category of mistake (safety/tone/factual/format).
            context: Situation in which the mistake happened.
            error: What the model did wrong.
            correction: What it should have done instead.
            lesson: Optional pre-written lesson; if omitted it is generated.
            patient_id: Optional patient identifier for context.
        Returns:
            Persisted MistakeNote ORM object.
        Agent:
            MistakeLogger
        """

        if not lesson:
            lesson = await self._derive_lesson(agent, mistake_type, error, correction)
        self.logger.info("Mistake recorded | agent=%s | type=%s | patient_id=%s", agent, mistake_type, patient_id)
        return await self.database.log_mistake(
            agent=agent,
            mistake_type=mistake_type,
            context=context,
            error=error,
            correction=correction,
            lesson=lesson,
            patient_id=patient_id,
        )

    async def lessons_for_prompt(self, patient_id: int | None = None) -> str:
        """Return a compact guardrail string built from past mistakes.

        Args:
            patient_id: Optional patient identifier to scope lessons.
        Returns:
            Newline-delimited lessons, or empty string when none exist.
        Agent:
            MistakeLogger
        """

        return await self.database.mistake_lessons_prompt(patient_id=patient_id)

    async def _derive_lesson(self, agent: str, mistake_type: str, error: str, correction: str) -> str:
        """Ask the model to generalise a correction into a short rule.

        Args:
            agent: Agent that made the mistake.
            mistake_type: Category of the mistake.
            error: What went wrong.
            correction: The correct behaviour.
        Returns:
            One-sentence generalised lesson.
        Agent:
            MistakeLogger
        """

        system = "You record lessons so an AI care companion avoids repeating mistakes. Given an error and its correction, write ONE short rule (under 20 words) the companion must follow next time. No preamble."
        prompt = f"Agent: {agent}\nMistake type: {mistake_type}\nError: {error}\nCorrection: {correction}"
        lesson = await self.ai.ask_text(system, prompt, fallback=correction, max_tokens=60)
        return lesson or correction