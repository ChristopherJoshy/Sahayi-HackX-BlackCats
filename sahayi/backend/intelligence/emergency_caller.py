"""Emergency call cascade for SAHAYI.

When a red-flag symptom is detected the companion asks the patient for
permission to call the doctor. If the patient says yes or does not reply in
time, we place an outbound call to the doctor via Twilio. If the doctor does
not answer, we cascade to the patient's relatives.

Args:
    None.
Agent:
    Intelligence
"""

from __future__ import annotations

import asyncio
from typing import Any

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from core.config import get_settings
from utils.logger import get_logger
from utils.validators import normalize_phone

_CALL_TIMEOUT_SECONDS = 30


class EmergencyCaller:
    """Orchestrate emergency outbound calls with a doctor→relative cascade."""

    def __init__(self, client: Client | None, database: Any, sockets: Any, family_alert: Any | None = None) -> None:
        """Initialise the emergency caller.

        Args:
            client: Authenticated Twilio REST client (may be None in dev).
            database: Shared database gateway instance.
            sockets: Dashboard socket manager for live updates.
            family_alert: Optional FamilyAlertAgent used to push a WhatsApp
                alert to the patient's relatives in parallel with the calls.
        Returns:
            None.
        Agent:
            Intelligence
        """

        self.client = client
        self.database = database
        self.sockets = sockets
        self.family_alert = family_alert
        self.settings = get_settings()
        self.logger = get_logger("sahayi.emergency_caller")

    async def trigger_cascade(self, patient: dict, session_id: str) -> None:
        """Run the full emergency call cascade.

        Calls the doctor first, then falls back to each relative in order if
        the doctor does not answer. Every attempt is broadcast to the doctor
        dashboard for observability.

        Args:
            patient: Patient profile dictionary.
            session_id: Active session UUID.
        Returns:
            None.
        Agent:
            Intelligence
        """

        doctor = patient.get("doctor_contact") or {}
        # Always call the configured emergency doctor number (set per clinic),
        # falling back to the per-patient doctor_contact phone when present.
        doctor_phone = normalize_phone(self.settings.doctor_emergency_phone) or normalize_phone(str(doctor.get("phone", "")))
        doctor_uid = patient.get("doctor_uid", "")
        patient_id = patient.get("id")
        patient_name = patient.get("name", "Patient")

        await self.sockets.broadcast(doctor_uid, "emergency_started", {
            "session_id": session_id,
            "patient_id": patient_id,
            "patient_name": patient_name,
        })

        # Alert the patient's relatives over WhatsApp in parallel with the
        # calls so a human is notified immediately, not only if the doctor is
        # unreachable. This is the "send alert to the relative" path.
        if self.family_alert:
            try:
                await self.family_alert.send(
                    patient,
                    f"{patient_name} may need urgent help. Sahayi has started calling the doctor. Please check in now.",
                    doctor_trigger=True,
                    red_flag=True,
                )
            except Exception:
                self.logger.exception("Relative WhatsApp alert failed | patient_id=%s", patient_id)

        if not self.client:
            self.logger.warning("Emergency cascade skipped — no Twilio client | patient_id=%s", patient_id)
            return

        # Step 1: call the doctor via the dedicated emergency line so the AI
        # briefs the doctor on the patient when they answer.
        base_url = self.settings.twilio_webhook_base.rstrip("/")
        doctor_webhook = f"{base_url}/voice/emergency/{session_id}"
        doctor_called = await self._attempt_call(doctor_phone, patient_name, "doctor", doctor_webhook)
        if doctor_called:
            await self.sockets.broadcast(doctor_uid, "emergency_doctor_contacted", {
                "session_id": session_id,
                "patient_id": patient_id,
                "patient_name": patient_name,
            })
            return

        # Step 2: cascade to relatives (voice call) if the doctor didn't connect.
        relatives = patient.get("relatives") or []
        for relative in relatives:
            rel_phone = normalize_phone(str(relative.get("phone", "")))
            rel_name = relative.get("name", "Relative")
            if not rel_phone:
                continue
            contacted = await self._attempt_call(rel_phone, patient_name, f"relative:{rel_name}")
            if contacted:
                await self.sockets.broadcast(doctor_uid, "emergency_relative_contacted", {
                    "session_id": session_id,
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "relative_name": rel_name,
                })
                return

        await self.sockets.broadcast(doctor_uid, "emergency_unreachable", {
            "session_id": session_id,
            "patient_id": patient_id,
            "patient_name": patient_name,
        })

    async def _attempt_call(self, phone_number: str, patient_name: str, role: str, webhook_url: str | None = None) -> bool:
        """Place one outbound Twilio call and report whether it connected.

        Args:
            phone_number: Destination phone number (normalized).
            patient_name: Patient display name for the call context.
            role: Who is being called (doctor / relative:Name).
            webhook_url: Optional TwiML webhook; defaults to the standard
                incoming-call handler when omitted.
        Returns:
            True when the call was created and reached an answered state.
        Agent:
            Intelligence
        """

        if not phone_number:
            return False
        if not webhook_url:
            base_url = self.settings.twilio_webhook_base.rstrip("/")
            webhook_url = base_url if base_url.endswith("/voice/incoming") else f"{base_url}/voice/incoming"
        try:
            call = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.calls.create,
                    to=phone_number,
                    from_=self.settings.twilio_phone_number,
                    url=webhook_url,
                    timeout=_CALL_TIMEOUT_SECONDS,
                ),
                timeout=_CALL_TIMEOUT_SECONDS + 5,
            )
            # Twilio 'queued'/'ringing' means the call is outgoing; treat as initiated.
            self.logger.info("Emergency call initiated | role=%s | to=%s | status=%s", role, phone_number, call.status)
            return bool(call.sid)
        except (TwilioRestException, TimeoutError, ValueError):
            self.logger.exception("Emergency call failed | role=%s | to=%s", role, phone_number)
            return False
