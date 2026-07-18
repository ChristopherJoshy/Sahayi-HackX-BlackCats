"""Application bootstrap helpers for SAHAYI backend."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from agents.doctor_summary import DoctorSummaryAgent
from agents.doctor_briefer import DoctorBrieferAgent
from agents.family_alert import FamilyAlertAgent
from agents.hypothesis_agent import HypothesisAgent
from agents.main_companion import MainCompanionAgent
from agents.orchestrator import Orchestrator
from agents.population_intelligence import PopulationIntelligenceAgent
from agents.relative_reporter import RelativeReporter
from agents.research_intelligence import ResearchIntelligenceAgent
from agents.safety_agent import SafetyAgent
from agents.signal_extractor import SignalExtractorAgent
from agents.whatsapp_agent import WhatsAppAgent
from core.realtime import DashboardSocketManager
from db.database import DatabaseGateway, init_db
from intelligence.emergency_caller import EmergencyCaller
from rag.chroma_store import ChromaStore
from rag.pubmed_client import PubMedClient
from twilio.rest import Client
from utils.logger import get_logger
from voice.twilio_handler import TwilioVoiceHandler

logger = get_logger("sahayi.bootstrap")


async def warmup_models() -> None:
    """Preload heavy ML models at startup to avoid mid-call stalls.

    The sentence-transformer embedding model (``all-MiniLM-L6-v2``) is pulled
    from the HuggingFace hub on first use, which otherwise happens during the
    first Research/RAG turn and blocks the voice flow with a download +
    progress bar. The Silero VAD ONNX model is also loaded once here so the
    first call doesn't pay the one-time ONNX session init cost.

    Args:
        None: Triggers warmup of the embedding model and VAD.
    Returns:
        None.
    Agent:
        Platform
    """

    # Embedding model — the main culprit behind the startup-time HF warning.
    try:
        # Silence the noisy "unauthenticated requests" HF notice now that the
        # model is preloaded at boot (it is a harmless telemetry hint).
        import os
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        import logging
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        from rag.embeddings import warmup_embeddings
        warmup_embeddings()
        logger.info("Warmed up embedding model")
    except Exception:
        logger.exception("Embedding model warmup failed")

    # Silero VAD — load one shared instance so per-session calls reuse it.
    try:
        from voice.vad import SileroVAD
        SileroVAD()
        logger.info("Warmed up VAD model")
    except Exception:
        logger.exception("VAD warmup failed")


async def bootstrap_app(app: Any) -> None:
    """Initialise database, retrieval, agents, and voice services.

    Args:
        app: FastAPI application instance.
    Returns:
        None.
    Agent:
        Platform
    """

    await init_db()
    app.state.database = DatabaseGateway()
    app.state.sockets = DashboardSocketManager()
    app.state.chroma = ChromaStore()
    await preload_knowledge_base(app.state.chroma)
    # Warm heavy models at startup so the first voice/research call isn't
    # stalled by a mid-request model download (HF hub pull + load bar).
    await warmup_models()
    pubmed = PubMedClient()
    signal = SignalExtractorAgent(app.state.database)
    safety = SafetyAgent()
    companion = MainCompanionAgent()
    companion.set_database(app.state.database)
    research = ResearchIntelligenceAgent(app.state.chroma, pubmed)
    population = PopulationIntelligenceAgent(app.state.database, pubmed)
    hypothesis = HypothesisAgent()
    doctor_summary = DoctorSummaryAgent(app.state.database, app.state.sockets)
    app.state.family_alert = FamilyAlertAgent()
    app.state.relative_reporter = RelativeReporter(app.state.database, app.state.family_alert)
    app.state.orchestrator = Orchestrator(app.state.database, app.state.sockets, signal, safety, companion, research, hypothesis, population, doctor_summary, app.state.relative_reporter)
    twilio_client = Client(app.state.settings.twilio_account_sid, app.state.settings.twilio_auth_token) if app.state.settings.twilio_account_sid and app.state.settings.twilio_auth_token else None
    emergency_caller = EmergencyCaller(twilio_client, app.state.database, app.state.sockets, app.state.family_alert)
    app.state.doctor_briefer = DoctorBrieferAgent()
    app.state.twilio_handler = TwilioVoiceHandler(app.state.database, app.state.orchestrator, app.state.sockets, emergency_caller, app.state.doctor_briefer, app.state.http_client)
    app.state.twilio_client = twilio_client
    app.state.whatsapp_agent = WhatsAppAgent(app.state.database, app.state.http_client)

    # Initialise population data if empty on startup
    import asyncio
    asyncio.create_task(run_population_job(app))


async def preload_knowledge_base(chroma: ChromaStore) -> None:
    """Populate Chroma when the collection is empty.

    Args:
        chroma: Shared Chroma store wrapper.
    Returns:
        None.
    Agent:
        Platform
    """

    if chroma.count():
        return
    logger.info("Knowledge base is empty at startup; keeping local store ready without remote preload.")


async def run_population_job(app: Any) -> None:
    """Execute the scheduled population intelligence job.

    Args:
        app: FastAPI application instance.
    Returns:
        None.
    Agent:
        Platform
    """

    findings = await app.state.orchestrator.population_agent.run()
    for finding in findings:
        await app.state.sockets.broadcast_all("population_update", {"pattern_json": finding.pattern_json, "frequency": finding.frequency, "week_delta": finding.week_delta, "research_gap": finding.research_gap})


async def run_patient_checkin_job(app: Any) -> None:
    """Place an outbound companion voice call to every active patient.

    Runs on a fixed cadence (20 minutes) so Sahayi proactively checks in.
    Patients without a usable phone number are skipped. Each call reuses the
    same inbound webhook path as follow-ups so the orchestrator handles the
    conversation.

    Args:
        app: FastAPI application instance.
    Returns:
        None.
    Agent:
        Platform
    """

    patients = await app.state.database.list_all_patients()
    called = 0
    for patient in patients:
        phone = getattr(patient, "phone_number", None)
        if not phone:
            continue
        await app.state.twilio_handler.initiate_follow_up_call(phone, patient.id)
        called += 1
    logger.info("Patient check-in job | patients=%d | calls_initiated=%d", len(patients), called)


async def run_overdue_summary_job(app: Any) -> None:
    """Handle overdue summaries and escalation rules.

    Args:
        app: FastAPI application instance.
    Returns:
        None.
    Agent:
        Platform
    """

    cutoff = datetime.utcnow() - timedelta(hours=app.state.settings.doctor_escalation_hours)
    for summary, patient in await app.state.database.latest_unacknowledged():
        if summary.created_at > cutoff:
            continue
        latest_signal = await app.state.database.latest_signal(patient.id)
        await app.state.twilio_handler.initiate_follow_up_call(patient.phone_number)
        await app.state.sockets.broadcast(patient.doctor_uid, "follow_up_due", {"summary_id": summary.id, "patient_id": patient.id, "patient_name": patient.name})
        if latest_signal and latest_signal.red_flag:
            payload = patient.__dict__.copy()
            payload.pop("_sa_instance_state", None)
            await app.state.family_alert.send(payload, "Doctor summary remained unacknowledged for 3 hours.", red_flag=True)


async def health_snapshot(app: Any) -> dict[str, Any]:
    """Build the health-check payload for the system.

    Args:
        app: FastAPI application instance.
    Returns:
        Health payload dictionary.
    Agent:
        Platform
    """

    services = {
        "database": {"status": "green"},
        "chroma": {"status": "green" if app.state.chroma.count() >= 0 else "red"},
        "gemini_vision": {"status": "green" if app.state.settings.gemini_vision_api_key else "red"},
        "twilio": {"status": "green" if app.state.settings.twilio_account_sid else "red"},
        "sarvam": {"status": "green" if app.state.settings.sarvam_api_key else "red"},
        "pubmed": {"status": "green" if app.state.settings.pubmed_email else "yellow"},
    }
    overall = "green" if all(item["status"] == "green" for item in services.values() if item["status"] != "yellow") else "degraded"
    return {"status": overall, "services": services}
