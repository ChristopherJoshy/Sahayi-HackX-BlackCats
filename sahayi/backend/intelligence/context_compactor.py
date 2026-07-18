# ============================================
# AGENT: ContextCompactor
# ROLE: Keep long conversations within the model context window (no data loss)
# TRIGGERS: Per turn, when estimated token usage crosses the 90% threshold
# OUTPUTS: A compacted history: persistent anchored summary + recent verbatim turns
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

from core.ai import OpenAIClient, ThinkingLevel
from utils.logger import get_logger

# sarvam-30b / OpenAI-compat context window used for the threshold check.
_MODEL_CONTEXT_TOKENS = 128_000
# Compaction fires when estimated usage exceeds this fraction of the window.
_COMPACTION_THRESHOLD = 0.90
# Keep this many recent turns verbatim so the model never loses the live thread.
_RECENT_TURNS_VERBATIM = 6
# Rough chars-per-token estimate for fast, dependency-free usage measurement.
_CHARS_PER_TOKEN = 4


class ContextCompactor:
    """Anchored, incremental context compaction (research-backed, fast).

    Instead of re-summarising the entire history every turn (which grows
    linearly), we keep one persistent ``summary`` and only summarise the
    newly dropped span of turns when the window is near full, then merge it
    into the anchored summary. Recent turns stay verbatim so the live
    conversation thread is never lost.
    """

    def __init__(self, database=None) -> None:
        """Initialise the compactor with an LLM helper.

        Args:
            database: Optional gateway (kept for future persistence hooks).
        Returns:
            None.
        Agent:
            ContextCompactor
        """

        self.ai = OpenAIClient(thinking_level=ThinkingLevel.MINIMAL)
        self.logger = get_logger("sahayi.context_compactor")
        self._summary: str | None = None

    @property
    def summary(self) -> str | None:
        """Return the current anchored summary.

        Args:
            None: Uses the internally maintained summary string.
        Returns:
            Anchored summary text or None when nothing compacted yet.
        Agent:
            ContextCompactor
        """

        return self._summary

    def estimate_tokens(self, history: list[str]) -> int:
        """Estimate token usage of a (possibly rendered) history.

        Args:
            history: List of turn strings to measure.
        Returns:
            Estimated token count.
        Agent:
            ContextCompactor
        """

        text = "\n".join(history)
        return len(text) // _CHARS_PER_TOKEN

    async def compact(self, history: list[str]) -> list[str]:
        """Return a compacted history when over threshold, else the original.

        The compacted form keeps a persistent summary line plus the most
        recent verbatim turns. When over the 90% threshold, only the turns
        that fall outside the recent window are folded into the summary
        (incremental merge), preserving all signal without re-summarising
        the whole prefix.

        Args:
            history: Full session history (alternating patient/assistant turns).
        Returns:
            Compacted history list (summary line + recent verbatim turns).
        Agent:
            ContextCompactor
        """

        if not history:
            return history

        if self.estimate_tokens(history) <= _MODEL_CONTEXT_TOKENS * _COMPACTION_THRESHOLD:
            return history

        recent = history[-_RECENT_TURNS_VERBATIM:]
        to_compact = history[:-_RECENT_TURNS_VERBATIM]

        merged = await self._merge_summary(to_compact)
        self._summary = merged
        self.logger.info(
            "Context compacted | before_turns=%d | after_turns=%d | summary_tokens=%d",
            len(history),
            len(recent) + 1,
            self.estimate_tokens([merged]),
        )
        return [f"[Conversation summary so far]\n{merged}"] + recent

    async def _merge_summary(self, turns: list[str]) -> str:
        """Fold a span of turns into the persistent anchored summary.

        Args:
            turns: Turns (outside the recent window) to summarise.
        Returns:
            Merged summary text combining prior summary and new span.
        Agent:
            ContextCompactor
        """

        span = "\n".join(turns)
        existing = self._summary or "No prior summary."
        system = (
            "You compress care-conversation history for a companion AI. "
            "Merge the NEW turns into the EXISTING summary. Keep: patient name, "
            "health concerns, symptoms mentioned, emotional state, preferences, "
            "open questions, and any escalation/care plan. Drop filler and exact "
            "wording. Output only the merged summary, under 200 words."
        )
        prompt = f"EXISTING SUMMARY:\n{existing}\n\nNEW TURNS:\n{span}"
        merged = await self.ai.ask_text(system, prompt, fallback=existing, max_tokens=300)
        return merged or existing
