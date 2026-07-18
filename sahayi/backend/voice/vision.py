"""Vision helpers for WhatsApp prescription extraction using Gemini vision."""

from __future__ import annotations

import base64
import httpx
import json

from contracts.clinical import PrescriptionData
from core.config import get_settings
from utils.logger import get_logger


async def extract_prescription_from_url(image_url: str) -> PrescriptionData:
    """Extract structured prescription data from an image URL using Gemini vision.

    Args:
        image_url: Public URL of the prescription image from Twilio.
    Returns:
        PrescriptionData with extracted medicines, doses, timings, purposes.
    Agent:
        WhatsApp Vision
    """

    logger = get_logger("sahayi.vision")
    settings = get_settings()

    prompt = """Extract the prescription details from this image.
    Return ONLY a JSON object with these exact keys:
    - medicines: array of medicine names
    - doses: array of doses (e.g., "500mg", "10ml")
    - timings: array of timings (e.g., "morning", "night", "after food", "before food")
    - purposes: array of purposes/indications for each medicine
    - raw_text: the full raw text visible in the prescription

    If no medicines found, return empty arrays."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            image_response = await client.get(image_url)
            image_response.raise_for_status()
            image_bytes = image_response.content

        from google.genai import Client, types

        vision_client = Client(api_key=settings.gemini_vision_api_key)
        mime_type = image_response.headers.get("content-type", "image/jpeg")

        response = await vision_client.aio.models.generate_content(
            model=settings.gemini_vision_model,
            contents=[
                prompt,
                types.Part(
                    inline_data=types.Blob(data=image_bytes, mime_type=mime_type)
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                system_instruction="You are a medical prescription parser. Extract structured data only.",
            ),
        )

        text = response.candidates[0].content.parts[0].text
        data = json.loads(text)

        return PrescriptionData(
            medicines=data.get("medicines", []),
            doses=data.get("doses", []),
            timings=data.get("timings", []),
            purposes=data.get("purposes", []),
            raw_text=data.get("raw_text", ""),
            confidence=0.85
        )

    except Exception as e:
        logger.error("Vision extraction failed: %s", str(e))
        return PrescriptionData(
            medicines=[],
            doses=[],
            timings=[],
            purposes=[],
            raw_text="",
            confidence=0.0
        )
