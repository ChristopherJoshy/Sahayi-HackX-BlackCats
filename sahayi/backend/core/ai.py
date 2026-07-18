"""Unified LLM helper for SAHAYI agents via the official Sarvam AI SDK.

All text reasoning for every agent is routed through Sarvam's Indic LLMs
(`sarvam-30b` / `sarvam-105b`) using the native `sarvamai` Python client.
The public surface (`OpenAIClient`, `ask_text`, `ask_json`) is unchanged so
agent code stays provider-agnostic.

Args:
    None.
Agent:
    Platform
"""

from __future__ import annotations

import asyncio
import json
import re
from enum import Enum
from typing import Any

from sarvamai import SarvamAI

from core.config import get_settings


class ThinkingLevel(str, Enum):
    """Agent reasoning tiers mapped to Sarvam sampling temperature.

    Sarvam reasoning mode is disabled at the client level (see ``_generate``),
    so these levels control determinism/cost via temperature rather than the
    model's reasoning effort. Lower levels are faster, cheaper, deterministic.
    """

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Default thinking levels per agent as per audit requirements.
# Lower tier => lower temperature (faster, cheaper, more deterministic).
AGENT_THINKING_LEVELS = {
    "main_companion": ThinkingLevel.MINIMAL,
    "signal_extractor": ThinkingLevel.MINIMAL,
    "safety_agent": ThinkingLevel.LOW,
    "research_intelligence": ThinkingLevel.MEDIUM,
    "hypothesis_agent": ThinkingLevel.HIGH,
    "population_intelligence": ThinkingLevel.LOW,
}

# Temperature per thinking level (kept low to stay fast and deterministic).
_THINKING_TEMPERATURES = {
    ThinkingLevel.MINIMAL: 0.1,
    ThinkingLevel.LOW: 0.2,
    ThinkingLevel.MEDIUM: 0.4,
    ThinkingLevel.HIGH: 0.7,
}

# Sarvam reasoning models spend part of the token budget on `reasoning_content`
# before emitting the real reply in `content`. A too-small cap truncates the reply
# to empty (finish_reason="length", content=None). We use a sensible floor so the
# reply is never starved, and a per-model ceiling equal to the largest `max_tokens`
# the API accepts (Starter tier) so calls never 422 on an over-large request while
# still giving the model room to reason. Reasoning tokens count toward this cap.
_MIN_MAX_TOKENS = 512

# Largest `max_tokens` the Sarvam API accepts per model (Starter tier limits from
# the official docs). The model stops early via finish_reason, so requesting the
# ceiling only ensures reasoning never exhausts the budget before the reply.
_MODEL_MAX_TOKENS = {
    "sarvam-30b": 4096,
    "sarvam-30b-16k": 4096,
    "sarvam-105b": 4096,
    "sarvam-105b-32k": 4096,
}

# Matches a fenced code block (```json ... ``` or ``` ... ```) so JSON mode can
# recover content the model wrapped in markdown despite no native JSON param.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Return text with surrounding markdown code fences removed.

    Args:
        text: Raw model output that may be wrapped in a code block.
    Returns:
        Unfenced text, or the original text when no fence is present.
    Agent:
        Platform
    """

    match = _FENCE_RE.search(text.strip())
    return match.group(1) if match else text


class OpenAIClient:
    """Async chat client backed by the official Sarvam AI SDK.

    Provides an `ask_text` / `ask_json` surface used by every agent. Internally
    it calls Sarvam's native (synchronous) `SarvamAI.chat.completions`, wrapped
    in a thread so the async event loop is never blocked. Agent code therefore
    stays provider-specific to Sarvam but otherwise unchanged.

    Args:
        thinking_level: Agent-specific reasoning configuration.
    Returns:
        OpenAIClient instance configured for the active Sarvam model.
    Agent:
        Platform
    """

    def __init__(self, thinking_level: ThinkingLevel = ThinkingLevel.MINIMAL) -> None:
        """Initialise the chat client for Sarvam's Indic LLM.

        Args:
            thinking_level: Reasoning config level (minimal/low/medium/high).
        Returns:
            None.
        Agent:
            Platform
        """

        settings = get_settings()
        self.thinking_level = thinking_level
        self.model = settings.sarvam_llm_model or "sarvam-30b"
        self.client = SarvamAI(api_subscription_key=settings.sarvam_api_key) if settings.sarvam_api_key else None

    async def ask_json(
        self,
        system: str,
        prompt: str,
        fallback: dict[str, Any],
        thinking_level: ThinkingLevel | None = None
    ) -> dict[str, Any]:
        """Request JSON output from the model with graceful fallback.

        Sarvam's chat API has no native JSON mode, so the prompt instructs the
        model to reply with JSON only and the response is fenced-block tolerant.

        Args:
            system: System instruction string.
            prompt: User prompt string.
            fallback: Fallback payload when the model is unavailable.
            thinking_level: Override thinking level for this specific call.
        Returns:
            Parsed JSON response or fallback data.
        Agent:
            Platform
        """

        level = thinking_level or self.thinking_level
        json_system = f"{system}\n\nReply with ONLY a single valid JSON object and no other text."
        text = await self._generate(json_system, prompt, level)
        if not text:
            return fallback
        try:
            data = json.loads(_strip_fences(text))
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                return data[0]
            if not isinstance(data, dict):
                return fallback
            return data
        except json.JSONDecodeError:
            return fallback

    async def ask_text(
        self,
        system: str,
        prompt: str,
        fallback: str,
        thinking_level: ThinkingLevel | None = None,
        max_tokens: int | None = None
    ) -> str:
        """Request free-form text output from the model with graceful fallback.

        Args:
            system: System instruction string.
            prompt: User prompt string.
            fallback: Fallback text when the model is unavailable.
            thinking_level: Override thinking level for this specific call.
            max_tokens: Optional cap on the generated token count. Lower values
                keep simple check-in replies short and fast.
        Returns:
            Model text output or fallback text.
        Agent:
            Platform
        """

        level = thinking_level or self.thinking_level
        text = await self._generate(system, prompt, level, max_tokens)
        return text.strip() if text else fallback

    async def _generate(
        self,
        system: str,
        prompt: str,
        thinking_level: ThinkingLevel,
        max_tokens: int | None = None
    ) -> str:
        """Call the Sarvam chat completions API (sync SDK, off the event loop).

        Args:
            system: System instruction string.
            prompt: User prompt string.
            thinking_level: Reasoning configuration level.
            max_tokens: Optional cap on generated tokens.
        Returns:
            Generated text payload or an empty string.
        Agent:
            Platform
        """

        if not self.client:
            return ""

        temperature = _THINKING_TEMPERATURES.get(thinking_level, 0.2)
        ceiling = _MODEL_MAX_TOKENS.get(self.model, 4096)
        requested = max_tokens if max_tokens is not None else ceiling
        # Clamp between the safety floor and the model's allowed ceiling so the
        # reply is never starved and the request is never rejected for being too large.
        effective_max = max(min(requested, ceiling), _MIN_MAX_TOKENS)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            # Reasoning is disabled: Sarvam's reasoning mode spends the entire
            # `max_tokens` budget on `reasoning_content` and returns empty `content`
            # (finish_reason="length"). Disabling it yields the reply directly and
            # is faster/cheaper for our conversational + extraction workloads.
            "reasoning_effort": None,
            "max_tokens": effective_max,
        }

        try:
            response = await asyncio.to_thread(self.client.chat.completions, **kwargs)
            return response.choices[0].message.content or ""
        except Exception:
            return ""
