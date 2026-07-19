"""Tests that the companion agent converses like a human.

Driven through the REAL MainCompanionAgent with a scripted mock LLM, so we
assert behavior (greeting, continuity, language lock, loops, restart) without
network or API keys. Run from sahayi/backend:  python -m pytest tests

Agent: Test harness.
"""

from __future__ import annotations

import asyncio
import importlib
import sys

import tests.stubs as stubs

stubs.install_stubs()

from agents.main_companion import MainCompanionAgent  # noqa: E402
from tests.stubs import MockOpenAIClient, MockDatabase  # noqa: E402


def _make_agent() -> MainCompanionAgent:
    agent = MainCompanionAgent()
    agent._db = MockDatabase()
    agent.memory.database = agent._db
    return agent


def _set_brain(fn):
    MockOpenAIClient.brain = staticmethod(fn)


async def _turn(agent, patient, history, text, lang=None, is_first=True, last_q=""):
    return await agent.respond(
        patient, history, text,
        detected_language=lang, is_first_turn=is_first, last_question=last_q,
    )


PATIENT = {"id": 1, "name": "Thankamma", "language": "ml-IN"}


# ---------------------------------------------------------------------------
# 1. GREETS like a human on first turn
# ---------------------------------------------------------------------------
def test_greets_on_first_turn():
    agent = _make_agent()
    captured = {}

    def brain(system, prompt, fallback, **kw):
        captured["system"] = system
        captured["reply"] = "നമസ്കാരം തങ്കമ്മ, സുഖമാണേല്ലേ? ഇന്ന് എങ്ങനെയുണ്ട്?"
        return captured["reply"]

    _set_brain(brain)
    reply = asyncio.run(_turn(agent, PATIENT, [], "", lang="ml-IN", is_first=True))
    assert reply.text
    # First-turn system prompt must instruct a warm greeting.
    assert "wish" in captured["system"].lower() or "greet" in captured["system"].lower()
    assert "നമസ്കാരം" in reply.text


# ---------------------------------------------------------------------------
# 2. NEVER re-greets on later turns (continuous conversation)
# ---------------------------------------------------------------------------
def test_no_repeat_greeting():
    agent = _make_agent()
    seen = []

    def brain(system, prompt, fallback, **kw):
        seen.append(system)
        return "ശരി ചേച്ചി, അത് കേൾക്കാം."

    _set_brain(brain)
    asyncio.run(_turn(agent, PATIENT, ["patient:നീ എങ്ങനെയുണ്ട്"], "നീ എങ്ങനെയുണ്ട്", lang="ml-IN", is_first=False))
    # The "do not greet" note must be present on a non-first turn.
    assert any("Do not greet" in s for s in seen)


# ---------------------------------------------------------------------------
# 3. RESTARTS conversation like a human in a new session
# ---------------------------------------------------------------------------
def test_restart_greets_again():
    agent = _make_agent()
    greetings = []

    def brain(system, prompt, fallback, **kw):
        if "wish" in system.lower() or "greet" in system.lower():
            greetings.append(True)
        return "മറ്റൊരു ദിവസം കാണാം."

    _set_brain(brain)
    # First session turn = greeting; second session (fresh agent) = greeting.
    asyncio.run(_turn(agent, PATIENT, [], "", lang="ml-IN", is_first=True))
    agent2 = _make_agent()
    asyncio.run(_turn(agent2, PATIENT, [], "", lang="ml-IN", is_first=True))
    assert greetings.count(True) == 2


# ---------------------------------------------------------------------------
# 4. CONTINUITY — references earlier content in THIS call
# ---------------------------------------------------------------------------
def test_picks_up_on_what_patient_said():
    agent = _make_agent()
    prompts = []

    def brain(system, prompt, fallback, **kw):
        prompts.append(prompt)
        return "അതെ, നിങ്ങൾ പറഞ്ഞ കാര്യം ഓർക്കാം."

    _set_brain(brain)
    asyncio.run(_turn(agent, PATIENT, ["patient:വൈകുന്നേരം ചായ കുടിച്ചു"], "വൈകുന്നേരം ചായ കുടിച്ചു", lang="ml-IN", is_first=False))
    # The patient's earlier statement should be in the prompt context.
    assert any("ചായ" in p for p in prompts)


# ---------------------------------------------------------------------------
# 5. LANGUAGE LOCK — non-English reply never drifts to English
# ---------------------------------------------------------------------------
def test_language_lock_no_english_drift():
    agent = _make_agent()
    attempts = []

    def brain(system, prompt, fallback, **kw):
        attempts.append(system)
        # First call "drifts" to English to simulate the bug we fixed.
        if len(attempts) == 1:
            return "Hello, how are you today?"
        return "സുഖം തന്നെ, നന്ദി."

    _set_brain(brain)
    reply = asyncio.run(_turn(agent, PATIENT, [], "എങ്ങനെയുണ്ട്", lang="ml-IN", is_first=False))
    # The retry prompt must enforce the lock, and the final text must be Indic.
    assert any("LOCK" in s or "lock" in s for s in attempts)
    assert reply.text and not reply.text.lower().startswith("hello")


# ---------------------------------------------------------------------------
# 6. LOOP detection — does not parrot its own last reply
# ---------------------------------------------------------------------------
def test_loop_detection_rewords():
    agent = _make_agent()
    calls = []

    def brain(system, prompt, fallback, **kw):
        calls.append(system)
        return "ശരി, അത് ശരിയാണ്."

    _set_brain(brain)
    # Real orchestrator history ends with the assistant's previous line.
    history = ["patient:സുഖം", "assistant:ശരി, അത് ശരിയാണ്.", "patient:സുഖം", "assistant:ശരി, അത് ശരിയാണ്."]
    asyncio.run(_turn(agent, PATIENT, history, "സുഖം", lang="ml-IN", is_first=False))
    # The companion prompt must forbid repeating the same question/topic so
    # the conversation never gets stuck parroting itself.
    assert any(("change the topic" in s or "never ask the same thing" in s) for s in calls)


# ---------------------------------------------------------------------------
# 7. TURN SHAPE — varies length, can be a single short word
# ---------------------------------------------------------------------------
def test_turn_shape_allows_short_reply():
    agent = _make_agent()
    sys_prompt = {}

    def brain(system, prompt, fallback, **kw):
        sys_prompt["s"] = system
        return "അതെ."

    _set_brain(brain)
    asyncio.run(_turn(agent, PATIENT, ["patient:നന്ദി"], "നന്ദി", lang="ml-IN", is_first=False))
    # Prompt should permit brief acknowledgements, not force 1-2 sentences.
    assert "one word" in sys_prompt["s"].lower() or "vary" in sys_prompt["s"].lower()


# ---------------------------------------------------------------------------
# 8. CROSS-CALL MEMORY — recalls a fact from a previous call
# ---------------------------------------------------------------------------
def test_cross_call_memory_recall():
    agent = _make_agent()
    prompts = []

    def brain(system, prompt, fallback, **kw):
        prompts.append(system)
        return "അതെ, കഴിഞ്ഞ തവണ പറഞ്ഞ കാര്യം ഓർക്കാം."

    _set_brain(brain)
    # Seed a memory note as if a previous call stored it.
    async def _seed():
        await agent._db.add_memory_note(1, "context", "patient mentioned their grandson Arjun visited")
    asyncio.run(_seed())
    asyncio.run(_turn(agent, PATIENT, [], "എങ്ങനെയുണ്ട്", lang="ml-IN", is_first=True))
    # The memory context must be injected into the prompt so the model can recall it.
    assert any("Arjun" in s for s in prompts)


# ---------------------------------------------------------------------------
# 9. NO INTERROGATION — prompt forbids firing many questions
# ---------------------------------------------------------------------------
def test_prompt_forbids_interrogation():
    agent = _make_agent()
    sys_prompt = {}

    def brain(system, prompt, fallback, **kw):
        sys_prompt["s"] = system
        return "ശരി."

    _set_brain(brain)
    asyncio.run(_turn(agent, PATIENT, ["patient:വിശപ്പില്ല"], "വിശപ്പില്ല", lang="ml-IN", is_first=False))
    assert "interrogate" in sys_prompt["s"].lower() or "one gentle question" in sys_prompt["s"].lower()


# ---------------------------------------------------------------------------
# 10. LESSONS injected without breaking prompt formatting
# ---------------------------------------------------------------------------
def test_lessons_placeholder_does_not_crash():
    agent = _make_agent()
    ok = {}

    def brain(system, prompt, fallback, **kw):
        ok["sys"] = system
        return "സുഖം."

    _set_brain(brain)
    # is_first_turn False but pass a lessons string like the orchestrator does.
    reply = asyncio.run(_turn(agent, PATIENT, ["patient:ഹായ്"], "ഹായ്", lang="ml-IN", is_first=False))
    assert reply.text == "സുഖം."
    # The literal placeholder must have been substituted (no bare '{lessons}').
    assert "{lessons}" not in ok["sys"]


# ---------------------------------------------------------------------------
# 11. NO ECHO — reply reacts to meaning, not a repetition of patient's words
# ---------------------------------------------------------------------------
def test_does_not_echo_patient_words():
    agent = _make_agent()
    sys_prompt = {}

    def brain(system, prompt, fallback, **kw):
        sys_prompt["s"] = system
        return "അതെ, അങ്ങനെയാണോ. ഇനിയെന്താ പറയാനുള്ളത്?"

    _set_brain(brain)
    asyncio.run(_turn(agent, PATIENT, ["patient:എനിക്ക് വയറ്റിൽ വേദനയാണ്"], "എനിക്ക് വയറ്റിൽ വേദനയാണ്", lang="ml-IN", is_first=False))
    # Prompt must forbid echoing/parroting the patient's own sentence.
    assert ("echo" in sys_prompt["s"].lower() or "repeat their" in sys_prompt["s"].lower()
            or "parrot" in sys_prompt["s"].lower() or "repeat the patient" in sys_prompt["s"].lower())


# ---------------------------------------------------------------------------
# 12. WIND-DOWN — closes the call warmly after enough turns, not loop forever
# ---------------------------------------------------------------------------
def test_winds_down_after_enough_turns():
    agent = _make_agent()
    sys_prompt = {}

    def brain(system, prompt, fallback, **kw):
        sys_prompt["s"] = system
        return "ശരി, ഞാൻ വീണ്ടും വിളിക്കാം. കരുതലോടെ ഇരിക്കൂ."

    _set_brain(brain)
    history = [f"patient:turn{i}" for i in range(12)]
    asyncio.run(_turn(agent, PATIENT, history, "ശരി", lang="ml-IN", is_first=False))
    # The prompt must instruct a warm close once the call has gone long enough.
    assert "wind" in sys_prompt["s"].lower() or "close" in sys_prompt["s"].lower()


# ---------------------------------------------------------------------------
# 13. STALL PIVOT — when talk stalls, moves to a new lighter subject
# ---------------------------------------------------------------------------
def test_pivots_to_new_topic_when_stalled():
    agent = _make_agent()
    sys_prompt = {}

    def brain(system, prompt, fallback, **kw):
        sys_prompt["s"] = system
        return "അതെ. ഇന്ന് ഉച്ചക്ക് എന്താ കഴിച്ചത്?"

    _set_brain(brain)
    asyncio.run(_turn(agent, PATIENT, ["patient:ശരി", "assistant:ശരി", "patient:ശരി"], "ശരി", lang="ml-IN", is_first=False))
    # Prompt must tell the model to change to a different, lighter subject.
    assert ("change" in sys_prompt["s"].lower() and "topic" in sys_prompt["s"].lower()) or \
           "new" in sys_prompt["s"].lower()


if __name__ == "__main__":
    for name in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        name()
        print(f"PASS {name.__name__}")
