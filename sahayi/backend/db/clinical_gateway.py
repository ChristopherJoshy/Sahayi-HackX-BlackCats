"""Clinical record query mixins for SAHAYI database access."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, select

from db.models import CallSession, DoctorSummary, MemoryNote, MistakeNote, Patient, PopulationPattern, RelativeUpdate, SignalRecord
from db.session import SessionLocal


class ClinicalGateway:
    """Clinical record database access methods."""

    async def create_call_session(self, patient_id: int, session_id: str) -> CallSession:
        """Create a new voice or message session.

        Args:
            patient_id: Patient identifier.
            session_id: Session UUID.
        Returns:
            Persisted CallSession ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            record = CallSession(patient_id=patient_id, session_id=session_id)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def finalize_call_session(self, session_id: str, risk_score: float, status: str) -> None:
        """Close a session and store its final risk.

        Args:
            session_id: Session UUID.
            risk_score: Final risk score for the session.
            status: Final session status string.
        Returns:
            None.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            record = await session.scalar(select(CallSession).where(CallSession.session_id == session_id))
            if record:
                record.ended_at = datetime.utcnow()
                record.risk_score = risk_score
                record.status = status
                await session.commit()

    async def save_signal(self, payload: dict) -> SignalRecord:
        """Persist one extracted signal record.

        Args:
            payload: ORM-ready signal payload.
        Returns:
            Persisted SignalRecord ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            record = SignalRecord(**payload)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def recent_signals(self, patient_id: int, days: int = 14) -> list[SignalRecord]:
        """Fetch recent signals for one patient.

        Args:
            patient_id: Patient identifier.
            days: Lookback window in days.
        Returns:
            List of SignalRecord ORM objects.
        Agent:
            Database
        """

        cutoff = datetime.utcnow() - timedelta(days=days)
        async with SessionLocal() as session:
            rows = await session.scalars(select(SignalRecord).where(SignalRecord.patient_id == patient_id, SignalRecord.created_at >= cutoff).order_by(SignalRecord.created_at))
            return list(rows)

    async def all_recent_signals(self, days: int = 7) -> list[SignalRecord]:
        """Fetch all recent signals for population analysis.

        Args:
            days: Lookback window in days.
        Returns:
            List of SignalRecord ORM objects.
        Agent:
            Database
        """

        cutoff = datetime.utcnow() - timedelta(days=days)
        async with SessionLocal() as session:
            rows = await session.scalars(select(SignalRecord).where(SignalRecord.created_at >= cutoff))
            return list(rows)

    async def create_summary(self, payload: dict) -> DoctorSummary:
        """Persist a doctor summary.

        Args:
            payload: ORM-ready summary payload.
        Returns:
            Persisted DoctorSummary ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            summary = DoctorSummary(**payload)
            session.add(summary)
            await session.commit()
            await session.refresh(summary)
            return summary

    async def acknowledge_summary(self, summary_id: int, doctor_uid: str) -> DoctorSummary | None:
        """Acknowledge a doctor summary owned by a doctor.

        Args:
            summary_id: Summary identifier.
            doctor_uid: Owning doctor UID.
        Returns:
            Updated DoctorSummary ORM object or None.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            summary = await session.scalar(select(DoctorSummary).join(Patient, Patient.id == DoctorSummary.patient_id).where(DoctorSummary.id == summary_id, Patient.doctor_uid == doctor_uid))
            if not summary:
                return None
            summary.acknowledged = True
            await session.commit()
            await session.refresh(summary)
            return summary

    async def latest_unacknowledged(self) -> list[tuple[DoctorSummary, Patient]]:
        """Fetch unacknowledged summaries with patient context.

        Args:
            None: Uses database ordering and join conditions.
        Returns:
            List of `(DoctorSummary, Patient)` tuples.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            rows = await session.execute(select(DoctorSummary, Patient).join(Patient, Patient.id == DoctorSummary.patient_id).where(DoctorSummary.acknowledged.is_(False)))
            return list(rows.all())

    async def save_population_pattern(self, payload: dict) -> PopulationPattern:
        """Persist one population pattern.

        Args:
            payload: ORM-ready population pattern payload.
        Returns:
            Persisted PopulationPattern ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            pattern = PopulationPattern(**payload)
            session.add(pattern)
            await session.commit()
            await session.refresh(pattern)
            return pattern

    async def latest_population_patterns(self) -> list[PopulationPattern]:
        """Fetch the latest saved population patterns.

        Args:
            None: Uses database ordering.
        Returns:
            List of PopulationPattern ORM objects.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            rows = await session.scalars(select(PopulationPattern).order_by(desc(PopulationPattern.created_at)).limit(10))
            return list(rows)

    async def latest_patient_summary(self, patient_id: int):
        """Fetch the most recent summary for one patient."""
        async with SessionLocal() as session:
            result = await session.scalars(select(DoctorSummary).where(DoctorSummary.patient_id == patient_id).order_by(desc(DoctorSummary.created_at)).limit(1))
            return result.first()


class MemoryGateway:
    """Persistent companion memory access methods."""

    async def get_memory_notes(self, patient_id: int) -> list[MemoryNote]:
        """Fetch all memory notes for one patient.

        Args:
            patient_id: Patient identifier.
        Returns:
            List of MemoryNote ORM objects ordered by recency.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            rows = await session.scalars(
                select(MemoryNote).where(MemoryNote.patient_id == patient_id).order_by(desc(MemoryNote.updated_at))
            )
            return list(rows)

    async def add_memory_note(self, patient_id: int, category: str, content: str) -> MemoryNote:
        """Persist a new memory note for one patient.

        Args:
            patient_id: Patient identifier.
            category: Note category (preference/context/relationship/reminder).
            content: Note text content.
        Returns:
            Persisted MemoryNote ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            note = MemoryNote(patient_id=patient_id, category=category, content=content)
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return note

    async def prune_memory_notes(self, patient_id: int, keep: int = 5) -> None:
        """Keep only the most recent `keep` memory notes for a patient.

        Older notes are deleted to bound storage and prompt context.

        Args:
            patient_id: Patient identifier.
            keep: Maximum number of notes to retain.
        Returns:
            None.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            rows = await session.scalars(
                select(MemoryNote).where(MemoryNote.patient_id == patient_id).order_by(desc(MemoryNote.updated_at))
            )
            notes = list(rows.all())
            for note in notes[keep:]:
                await session.delete(note)
            if len(notes) > keep:
                await session.commit()


class MistakeGateway:
    """Persistent mistake-memory access so the AI learns from its errors."""

    async def log_mistake(self, agent: str, mistake_type: str, context: str, error: str, correction: str, lesson: str, patient_id: int | None = None) -> MistakeNote:
        """Persist one logged AI mistake for future learning.

        Args:
            agent: Agent name that made the mistake.
            mistake_type: Category of mistake (e.g. safety, tone, factual).
            context: What the situation was when the mistake happened.
            error: What the model did wrong.
            correction: What it should have done instead.
            lesson: Generalised rule to apply next time.
            patient_id: Optional patient identifier for context.
        Returns:
            Persisted MistakeNote ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            note = MistakeNote(
                patient_id=patient_id,
                agent=agent,
                mistake_type=mistake_type,
                context=context,
                error=error,
                correction=correction,
                lesson=lesson,
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return note

    async def recent_mistakes(self, limit: int = 20, patient_id: int | None = None) -> list[MistakeNote]:
        """Fetch recent mistakes, optionally scoped to one patient.

        Args:
            limit: Maximum number of mistakes to return.
            patient_id: Optional patient identifier to scope results.
        Returns:
            List of MistakeNote ORM objects ordered by recency.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            stmt = select(MistakeNote)
            if patient_id is not None:
                stmt = stmt.where(MistakeNote.patient_id == patient_id)
            stmt = stmt.order_by(desc(MistakeNote.created_at)).limit(limit)
            rows = await session.scalars(stmt)
            return list(rows.all())

    async def mistake_lessons_prompt(self, patient_id: int | None = None, limit: int = 10) -> str:
        """Render recent mistake lessons as a compact guardrail string.

        Args:
            patient_id: Optional patient identifier to scope lessons.
            limit: Maximum number of lessons to include.
        Returns:
            Newline-delimited lesson text, or empty string when none.
        Agent:
            Database
        """

        notes = await self.recent_mistakes(limit=limit, patient_id=patient_id)
        if not notes:
            return ""
        lines = [f"- {note.lesson}" for note in notes if note.lesson]
        return "\n".join(lines)


class RelativeUpdateGateway:
    """Persistent store for relative-submitted clinical summaries."""

    async def add_relative_update(
        self,
        patient_id: int,
        relative_name: str,
        update_type: str,
        clinical_summary: str,
        source_detail: str = "",
    ) -> RelativeUpdate:
        """Persist one relative-submitted clinical summary.

        Args:
            patient_id: Patient identifier the update relates to.
            relative_name: Name of the relative who submitted it.
            update_type: One of "medication", "voice_note", "symptom", "text".
            clinical_summary: Derived clinical summary (never raw transcript).
            source_detail: Short structured detail (e.g. medicine name).
        Returns:
            Persisted RelativeUpdate ORM object.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            record = RelativeUpdate(
                patient_id=patient_id,
                relative_name=relative_name,
                update_type=update_type,
                clinical_summary=clinical_summary,
                source_detail=source_detail,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def recent_relative_updates(self, patient_id: int, limit: int = 20) -> list[RelativeUpdate]:
        """Fetch recent relative updates for one patient.

        Args:
            patient_id: Patient identifier.
            limit: Maximum number of updates to return.
        Returns:
            List of RelativeUpdate ORM objects ordered by recency.
        Agent:
            Database
        """

        async with SessionLocal() as session:
            rows = await session.scalars(
                select(RelativeUpdate)
                .where(RelativeUpdate.patient_id == patient_id)
                .order_by(desc(RelativeUpdate.created_at))
                .limit(limit)
            )
            return list(rows.all())
