"""One-off script to create the Thankamma patient via the DB gateway."""

import asyncio

from db.database import DatabaseGateway
from utils.validators import normalize_phone, normalize_whatsapp

DOCTOR_PHONE = "6282257804"

payload = {
    "name": "Thankamma",
    "language": "ml-IN",
    "phone_number": normalize_phone("8075809531"),
    "registration_number": None,
    "conditions": [],
    "medicines": [
        {"name": "Paracetamol", "dose": "500mg", "frequency": "As needed", "timing": "After meals"},
    ],
    "emergency_contact": {
        "name": "Relative",
        "phone": normalize_phone("6282257804"),
        "relationship": "Relative",
    },
    "doctor_contact": {
        "name": "Doctor",
        "phone": normalize_phone("6282257804"),
        "relationship": "Doctor",
    },
    "relatives": [
        {
            "name": "Relative",
            "relationship": "Relative",
            "phone": normalize_phone("6282257804"),
            "whatsapp_number": normalize_whatsapp("6282257804"),
        }
    ],
    "doctor_uid": normalize_phone("6282257804"),
    "doctor_email": "",
}


async def main():
    db = DatabaseGateway()
    patient = await db.create_patient(payload)
    print("Created patient:")
    print("  id:", patient.id)
    print("  name:", patient.name)
    print("  phone_number:", patient.phone_number)
    print("  doctor_uid:", patient.doctor_uid)
    print("  medicines:", patient.medicines)
    print("  relatives:", patient.relatives)


if __name__ == "__main__":
    asyncio.run(main())
