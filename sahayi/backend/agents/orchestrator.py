# ============================================
# AGENT: Orchestrator
# ROLE: Route each patient turn through extraction, intelligence, safety, and escalation
# TRIGGERS: Every patient transcript or WhatsApp message
# OUTPUTS: TurnResult dataclass plus realtime dashboard updates
# TEAM: Black Cats — Sahayi @ HackX
# ============================================

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import asdict

from contracts.agents import CompanionReply, PopulationFinding, TurnResult
from core.config import get_settings
from core.realtime import DashboardSocketManager
from db.database import DatabaseGateway
from intelligence.anomaly_detection import detect_anomaly
from intelligence.mistake_logger import MistakeLogger
from intelligence.risk_scoring import compute_risk
from intelligence.trend_detection import detect_trend
from utils.logger import get_logger

        # Guardrails to keep prompts bounded and avoid stuck loops.
_MAX_HISTORY_TURNS = 40
_LOOP_DETECT_THRESHOLD = 3


class Orchestrator:
    """Central routing agent for SAHAYI patient turns."""

    def __init__(self, database: DatabaseGateway, sockets: DashboardSocketManager, signal_extractor: object, safety_agent: object, companion_agent: object, research_agent: object, hypothesis_agent: object, population_agent: object, doctor_summary_agent: object, relative_reporter: object | None = None) -> None:
        """Initialise orchestrator dependencies.

        Args:
            database: Shared database gateway instance.
            sockets: Shared dashboard socket manager.
            signal_extractor: Signal extractor agent instance.
            safety_agent: Safety agent instance.
            companion_agent: Main companion agent instance.
            research_agent: Research intelligence agent instance.
            hypothesis_agent: Hypothesis agent instance.
            population_agent: Population intelligence agent instance.
            doctor_summary_agent: Doctor summary agent instance.
            relative_reporter: Optional agent that pushes care updates to relatives.
        Returns:
            None.
        Agent:
            Orchestrator
        """

        self.database = database
        self.sockets = sockets
        self.signal_extractor = signal_extractor
        self.safety_agent = safety_agent
        self.companion_agent = companion_agent
        self.research_agent = research_agent
        self.hypothesis_agent = hypothesis_agent
        self.population_agent = population_agent
        self.doctor_summary_agent = doctor_summary_agent
        self.relative_reporter = relative_reporter
        self.logger = get_logger("sahayi.orchestrator")
        # Full live transcript for the call. A single call never approaches the
        # model window, so we keep the WHOLE conversation verbatim — compaction
        # was dropping context and made the agent repeat itself / ignore the user.
        self.session_history: dict[str, list[str]] = defaultdict(list)
        self.session_risks: dict[str, float] = {}
        self._last_transcripts: dict[str, list[str]] = defaultdict(list)
        self._first_turn: dict[str, bool] = defaultdict(lambda: True)
        self._last_question: dict[str, str] = {}
        self.mistake_logger = MistakeLogger(database)

    async def handle_turn(self, patient: dict, session_id: str, transcript: str, detected_language: str | None = None, is_opening: bool = False) -> TurnResult:
        """Process one patient turn end-to-end.

        Runs signal extraction and companion reply concurrently so the
        patient hears a response faster.  Downstream risk-based agents
        (research, hypothesis, doctor summary) also run in parallel where
        their data dependencies allow.

        Args:
            patient: Patient profile dictionary.
            session_id: Active session UUID.
            transcript: Latest transcript or message text.
        Returns:
            Typed turn result.
        Agent:
            Orchestrator
        """

        self.logger.info("Orchestrator activated | patient_id=%s | session_id=%s | trigger=patient_turn", patient["id"], session_id)

        # Ignore empty/silence turns — answering dead air made the agent sound
        # like it was talking to itself. Only process real patient input.
        # The opening turn has no transcript yet (it is the agent's greeting),
        # so it must bypass the empty-transcript filter.
        if not is_opening and (not transcript or not transcript.strip()):
            self.logger.info("Empty transcript ignored | session_id=%s", session_id)
            return TurnResult(signal=None, risk=None, reply=CompanionReply(text="", used_context=[]), research=None, hypothesis=None, doctor_report=None)

        # Loop guard: if the patient repeats the same thing too many times,
        # gently steer the conversation elsewhere instead of echoing.
        self._last_transcripts[session_id].append(transcript.strip().lower())
        if len(self._last_transcripts[session_id]) > _LOOP_DETECT_THRESHOLD:
            self._last_transcripts[session_id].pop(0)
        if self._last_transcripts[session_id].count(transcript.strip().lower()) >= _LOOP_DETECT_THRESHOLD:
            self.logger.info("Loop detected | session_id=%s — steering conversation", session_id)
            transcript = "[The patient seems to be repeating themselves. Gently acknowledge and ask about something else, like how their day is going or if they've eaten.]"

        # Bound the live history window to keep prompts fast and cheap.
        # (Kept generous — a single call stays well within the model window so
        # the agent never loses the thread mid-conversation.)
        self.session_history[session_id].append(f"patient:{transcript}")

        # Full verbatim history for this call — no compaction that drops context.
        compacted_history = list(self.session_history[session_id])

        # Surface lessons learned from past mistakes as gentle guardrails.
        lessons = ""
        if getattr(self, "mistake_logger", None) is not None:
            lessons = await self.mistake_logger.lessons_for_prompt(patient_id=patient["id"])

        # To make voice snappy, we await ONLY the companion agent now,
        # and fire the rest in the background!
        is_first = bool(self._first_turn.get(session_id, True)) or is_opening
        last_question = "" if is_opening else self._last_question.get(session_id, "")
        reply_task = self.companion_agent.respond(
            patient, compacted_history, transcript, lessons=lessons,
            detected_language=detected_language, is_first_turn=is_first,
            last_question=last_question,
        )
        reply = await reply_task
        self._first_turn[session_id] = False
        # Remember the question we just asked so we never repeat it next turn.
        asked = self.companion_agent.last_question(reply.text)
        if asked:
            self._last_question[session_id] = asked
        
        # Safety review runs immediately — risk-based routing (research,
        # hypothesis, doctor summary) is fired off in the background so
        # the patient hears a reply without waiting for PubMed / extra LLM calls.
        safety = await self.safety_agent.review(reply.text, [])
        # If the safety agent had to alter the reply, that is a correction we
        # learn from so the companion improves over time.
        if safety.safe_response.strip() != reply.text.strip():
            asyncio.create_task(
                self.mistake_logger.record(
                    agent="main_companion",
                    mistake_type="safety",
                    context=f"session_id={session_id}; patient_id={patient['id']}",
                    error=reply.text,
                    correction=safety.safe_response,
                    patient_id=patient["id"],
                )
            )
        await self.sockets.broadcast(patient["doctor_uid"], "safety_check", {"session_id": session_id, "patient_id": patient["id"], "safe_response": safety.safe_response})

        safe_reply = CompanionReply(text=safety.safe_response, used_context=reply.used_context)
        self.session_history[session_id].append(f"assistant:{safe_reply.text}")

        # Kick off downstream intelligence in the background — results
        # flow to the dashboard via sockets and to the database log.
        # The opening line has no patient transcript, so skip signal/risk work.
        if transcript and transcript.strip():
            asyncio.create_task(
                self._background_processing(patient, session_id, transcript, safe_reply)
            )

        # Return dummy turn result (signal and risk will be computed in bg)
        # TurnResult is primarily consumed for reply text
        return TurnResult(signal=None, risk=None, reply=safe_reply, research=None, hypothesis=None, doctor_report=None)

    async def _background_processing(self, patient: dict, session_id: str, transcript: str, safe_reply: object) -> None:
        """Run extraction, risk, and downstream agents in the background."""
        try:
            signal = await self.signal_extractor.extract(patient["id"], session_id, transcript)
            history = await self.database.recent_signals(patient["id"], days=14)
            risk = self._calculate_risk(signal, history)
            self.session_risks[session_id] = risk.score
            await self._broadcast_basics(patient, session_id, signal, risk)

            # Proactively update the relative when risk is elevated or a red flag appears.
            if self.relative_reporter is not None and (risk.score >= get_settings().risk_yellow_threshold or getattr(signal, "red_flag", False)):
                observed = f"severity {getattr(signal, 'severity', 0):.1f}"
                if getattr(signal, "red_flag", False):
                    observed += ", red-flag symptom reported"
                asyncio.create_task(
                    self.relative_reporter.report_event(patient, risk.score, "check-in update", observed)
                )

            await self._background_risk_routing(patient, session_id, signal, risk, history, safe_reply)
        except Exception:
            self.logger.exception("Background processing failed | session_id=%s", session_id)

    async def _background_risk_routing(self, patient: dict, session_id: str, signal: object, risk: object, history: list[object], reply: object) -> None:
        """Run risk-based downstream agents in the background.

        Results update the dashboard via sockets and are persisted to the
        database audit log.  This never blocks the voice reply.

        Args:
            patient: Patient profile dictionary.
            session_id: Active session UUID.
            signal: Latest extracted signal.
            risk: Latest risk assessment.
            history: Recent patient signal history.
            reply: The companion reply that was already sent.
        Returns:
            None.
        Agent:
            Orchestrator
        """

        try:
            research, hypothesis, report = await self._route_by_risk(patient, signal, risk, history)
            await self.database.log_decision(patient["id"], session_id, "patient_turn", self._decision_text(risk, report, hypothesis))
        except Exception:
            self.logger.exception("Background risk routing failed | session_id=%s", session_id)

    def _calculate_risk(self, signal: object, history: list[object]) -> object:
        """Calculate risk using trend and anomaly helpers.

        Args:
            signal: Latest extracted signal.
            history: Recent patient signal history.
        Returns:
            Typed risk assessment.
        Agent:
            Orchestrator
        """

        this_week = [item for item in history if (signal.created_at - item.created_at).days < 7]
        previous = [item for item in history if (signal.created_at - item.created_at).days >= 7]
        current_count = len(this_week)
        previous_count = len(previous)
        trend, _ = detect_trend(current_count, previous_count)
        anomaly, z_score, _ = detect_anomaly([item.severity for item in history[:-1]], signal.severity, get_settings().anomaly_z_score_threshold)
        return compute_risk(signal, current_count, previous_count, get_settings().risk_yellow_threshold, get_settings().risk_red_threshold, trend, z_score, anomaly)

    async def _broadcast_basics(self, patient: dict, session_id: str, signal: object, risk: object) -> None:
        """Broadcast baseline signal and risk updates to the dashboard.

        Args:
            patient: Patient profile dictionary.
            session_id: Active session UUID.
            signal: Latest extracted signal.
            risk: Latest risk assessment.
        Returns:
            None.
        Agent:
            Orchestrator
        """

        await self.sockets.broadcast(patient["doctor_uid"], "new_signal", {"session_id": session_id, "patient_id": patient["id"], "patient_name": patient["name"], **asdict(signal)})
        await self.sockets.broadcast(patient["doctor_uid"], "risk_update", {"session_id": session_id, "patient_id": patient["id"], "patient_name": patient["name"], **asdict(risk)})

    async def _route_by_risk(self, patient: dict, signal: object, risk: object, history: list[object]) -> tuple[object | None, object | None, object | None]:
        """Route optional downstream agents based on risk thresholds.

        Runs independent agents concurrently where possible to minimise
        overall latency.

        Args:
            patient: Patient profile dictionary.
            signal: Latest extracted signal.
            risk: Latest risk assessment.
            history: Recent patient signal history.
        Returns:
            Tuple of optional research, hypothesis, and doctor report outputs.
        Agent:
            Orchestrator
        """

        # Research and population patterns are independent — fetch together.
        research_coro = self.research_agent.analyze(signal, self._serialize_history(history), patient) if risk.score > 0.3 else None
        patterns_coro = self.database.latest_population_patterns()

        if research_coro:
            research, patterns = await asyncio.gather(research_coro, patterns_coro)
        else:
            research = None
            patterns = await patterns_coro

        findings = [PopulationFinding(item.pattern_json, item.frequency, item.week_delta, item.research_gap) for item in patterns]

        # Hypothesis and doctor summary depend on research but not on
        # each other — run them simultaneously when both are needed.
        hypothesis = None
        report = None
        if research:
            need_hypothesis = risk.score > 0.5
            need_report = risk.score > 0.4
            if need_hypothesis and need_report:
                hypothesis, report = await asyncio.gather(
                    self.hypothesis_agent.generate(research, findings),
                    self.doctor_summary_agent.generate(patient, signal, risk, research, None),
                )
            elif need_hypothesis:
                hypothesis = await self.hypothesis_agent.generate(research, findings)
            elif need_report:
                report = await self.doctor_summary_agent.generate(patient, signal, risk, research, None)
                await self.sockets.broadcast(patient["doctor_uid"], "doctor_summary", {"session_id": session_id, "patient_id": patient["id"], **asdict(report)})

        if hypothesis:
            await self.sockets.broadcast(patient["doctor_uid"], "hypothesis_generated", {"patient_id": patient["id"], **asdict(hypothesis)})
        return research, hypothesis, report

    def _serialize_history(self, history: list[object]) -> list[dict]:
        """Serialize ORM signal history for downstream agents.

        Args:
            history: SignalRecord ORM instances.
        Returns:
            List of simple dictionaries.
        Agent:
            Orchestrator
        """

        return [
            {
                "fatigue": item.fatigue,
                "appetite": item.appetite,
                "chest_pain": item.chest_pain,
                "duration_days": item.duration_days,
                "severity": item.severity,
                "red_flag": item.red_flag,
                "created_at": item.created_at.isoformat(),
            }
            for item in history
        ]

    def _decision_text(self, risk: object, report: object | None, hypothesis: object | None) -> str:
        """Render the audit log decision text.

        Args:
            risk: Latest risk assessment.
            report: Optional doctor report.
            hypothesis: Optional hypothesis result.
        Returns:
            Rendered decision text.
        Agent:
            Orchestrator
        """

        return f"risk={risk.score}; summary={'yes' if report else 'no'}; hypothesis={'yes' if hypothesis else 'no'}"
