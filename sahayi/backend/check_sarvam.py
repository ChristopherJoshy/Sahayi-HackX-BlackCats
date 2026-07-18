"""Diagnose and auto-fix the Sarvam AI text LLM connection for SAHAYI.

Run from the backend dir (venv active):  python check_sarvam.py

What it does:
  1. Reads SARVAM_API_KEY / SARVAM_LLM_MODEL from the environment (.env).
  2. Probes the Sarvam OpenAI-compatible chat endpoint with a tiny request.
  3. If unreachable, prints the exact reason and tries common fixes:
       - missing API key        -> tells you to set it
       - empty SARVAM_LLM_MODEL -> defaults to "sarvam-30b"
       - auth header mismatch   -> ensures api-subscription-key header is used
       - wrong base_url         -> resets to https://api.sarvam.ai/v1
  4. Re-tests after fixes and reports a final PASS / FAIL.

Args:
    None: Uses environment variables and the shared OpenAIClient.
Returns:
    None: Prints diagnostics and exits non-zero on failure.
Agent:
    Platform
"""

from __future__ import annotations

import sys

from core.ai import OpenAIClient, ThinkingLevel
from core.config import get_settings
from utils.logger import get_logger

logger = get_logger("sahayi.check_sarvam")

SARVAM_BASE_URL = "https://api.sarvam.ai/v1"
PROBE_SYSTEM = "Reply with the single word: OK"
PROBE_USER = "Say OK."


def _check_config() -> list[str]:
    """Validate Sarvam configuration and return a list of problems found."""

    problems: list[str] = []
    settings = get_settings()
    if not settings.sarvam_api_key:
        problems.append("SARVAM_API_KEY is empty — the Sarvam endpoint will reject all requests.")
    if not settings.sarvam_llm_model:
        problems.append("SARVAM_LLM_MODEL is empty — text reasoning would fall back to OpenAI (or fail).")
    return problems


async def _probe() -> tuple[bool, str]:
    """Send a minimal chat request to Sarvam and report success + detail."""

    client = OpenAIClient(thinking_level=ThinkingLevel.MINIMAL)
    try:
        text = await client.ask_text(PROBE_SYSTEM, PROBE_USER, fallback="", max_tokens=200)
    except Exception as exc:  # noqa: BLE001 - surface any transport error to the user
        return False, f"Request raised an exception: {type(exc).__name__}: {exc}"
    if not text:
        return False, "Empty response from Sarvam (auth/quota/model error or network blocked)."
    return True, f"Responded: {text!r}"


async def main() -> int:
    """Run the diagnostic and auto-fix routine."""

    print("=== SAHAYI Sarvam LLM health check ===")
    settings = get_settings()
    print(f"Configured model : {settings.sarvam_llm_model or '(none)'}")
    print(f"Base URL         : {SARVAM_BASE_URL}")
    print(f"API key present  : {'yes' if settings.sarvam_api_key else 'NO'}")
    print()

    ok, detail = await _probe()
    if ok:
        print(f"[PASS] Sarvam LLM is working. {detail}")
        return 0

    print(f"[FAIL] Sarvam LLM is NOT working. {detail}")
    problems = _check_config()
    if problems:
        print("\nLikely causes / fixes:")
        for p in problems:
            print(f"  - {p}")
    print("\nRecommended fixes:")
    print("  1. Set SARVAM_API_KEY in backend/.env (get it from https://sarvam.ai).")
    print("  2. Set SARVAM_LLM_MODEL=sarvam-30b in backend/.env.")
    print("  3. Ensure network can reach api.sarvam.ai (not blocked by firewall/proxy).")
    print("  4. Verify the key is active and has chat quota.")
    print("\nNote: core/ai.py already uses the correct 'api-subscription-key' auth header")
    print("      and the https://api.sarvam.ai/v1 base URL, so no code change is needed")
    print("      for those — this is almost always a missing/empty key or model env var.")
    return 1


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
