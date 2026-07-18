"""Persistent companion memory for SAHAYI.

Builds and maintains lightweight memory notes per patient so the companion
can reference prior conversations, preferences, and relationship context
without re-sending the full history on every turn.

Args:
    None.
Agent:
    Intelligence
"""

from __future__ import annotations

from db.database import DatabaseGateway
from core.ai import OpenAIClient, ThinkingLevel
from utils.logger import get_logger

_MAX_NOTES = 15
_MEMORY_EXTRACTION_PROMPT = (
    "You are a memory assistant for a warm companion named Sahayi that checks in "
    "on rural Kerala patients. Given the latest conversation turn, extract ONLY "
    "durable, relationship-building facts worth remembering for future calls. "
    "Skip transient symptoms (those go to the medical record). Capture things like "
    "family members mentioned, preferences (call time, language, tone), hobbies, "
    "mood patterns, or reminders the patient asked us to keep.\n"
    "Respond ONLY with a JSON array of objects, each with 'category' "
    "(one of: preference, context, relationship, reminder) and 'content' "
    "(one short sentence). If nothing memory-worthy, return an empty array []."
)


class MemoryManager:
    """Manage persistent companion memory notes for patients."""

    def __init__(self, database: DatabaseGateway) -> None:
        """Initialise the memory manager dependencies.

        Args:
            database: Shared database gateway instance.
        Returns:
            None.
        Agent:
            Intelligence
        """

        self.database = database
        self.model = OpenAIClient(thinking_level=ThinkingLevel.MINIMAL)
        self.logger = get_logger("sahayi.memory_manager")

    async def get_context_string(self, patient_id: int) -> str:
        """Render stored memory notes as a single context string for prompts.

        Args:
            patient_id: Patient identifier.
        Returns:
            Newline-separated memory notes or empty string when none exist.
        Agent:
            Intelligence
        """

        notes = await self.database.get_memory_notes(patient_id)
        if not notes:
            return ""
        return "\n".join(f"- ({n.category}) {n.content}" for n in notes)

    async def extract_and_store(self, patient_id: int, transcript: str, reply: str) -> None:
        """Extract memory-worthy notes from a turn and persist them.

        Runs as a fire-and-forget background task. Never blocks the voice reply.

        Args:
            patient_id: Patient identifier.
            transcript: Patient's latest message.
            reply: Companion's latest reply.
        Returns:
            None.
        Agent:
            Intelligence
        """

        try:
            conversation = f"Patient: {transcript}\nSahayi: {reply}"
            result = await self.model.ask_json(
                _MEMORY_EXTRACTION_PROMPT,
                conversation,
                [],
            )
            notes = result if isinstance(result, list) else []
            for note in notes[:3]:
                category = str(note.get("category", "context"))[:32]
                content = str(note.get("content", "")).strip()
                if content:
                    await self.database.add_memory_note(patient_id, category, content)
            if notes:
                await self.database.prune_memory_notes(patient_id, _MAX_NOTES)
        except Exception:
            self.logger.exception("Memory extraction failed | patient_id=%s", patient_id)
