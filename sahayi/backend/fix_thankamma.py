"""Reassign Thankamma's doctor_uid to the MVP dashboard doctor uid."""

import asyncio

from db.database import DatabaseGateway
from db.models import Patient
from db.session import SessionLocal
from sqlalchemy import select
from utils.validators import normalize_phone

TARGET_UID = "mvp-doctor-001"
PHONE = normalize_phone("8075809531")


async def main():
    db = DatabaseGateway()
    async with SessionLocal() as session:
        patient = await session.scalar(select(Patient).where(Patient.phone_number == PHONE))
        if not patient:
            print("Patient not found for phone", PHONE)
            return
        patient.doctor_uid = TARGET_UID
        await session.commit()
        await session.refresh(patient)
        print("Reassigned:", patient.id, patient.name, "-> doctor_uid =", patient.doctor_uid)


if __name__ == "__main__":
    asyncio.run(main())
