"""Sarvam text-to-speech client for SAHAYI."""

from __future__ import annotations

import asyncio
import base64
import httpx
from sarvamai import SarvamAI

from core.config import get_settings
from utils.logger import get_logger


class SarvamTTSClient:
    """Client for Sarvam text-to-speech synthesis using official SDK."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """Initialise TTS client settings.

        Args:
            http_client: Shared HTTP client session.
        Returns:
            None.
        Agent:
            Voice
        """

        self.settings = get_settings()
        self.logger = get_logger("sahayi.sarvam_tts")
        self.client = SarvamAI(api_subscription_key=self.settings.sarvam_api_key) if self.settings.sarvam_api_key else None
        self.http_client = http_client

    async def synthesize(self, text: str, language_code: str | None = None) -> bytes:
        """Synthesize speech into Twilio-safe mu-law audio using REST API.

        Args:
            text: Text to synthesize (in the target language).
            language_code: BCP-47 language for synthesis; defaults to the
                configured Sarvam language when omitted.
        Returns:
            Mu-law audio bytes at 8kHz, or empty bytes when Sarvam fails.
        Agent:
            Voice
        """

        if not text.strip() or not self.settings.sarvam_api_key:
            return b""

        target_language = language_code or self.settings.sarvam_language

        headers = {
            "api-subscription-key": self.settings.sarvam_api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "target_language_code": target_language,
            "speaker": self.settings.sarvam_tts_speaker,
            "model": self.settings.sarvam_tts_model or "bulbul:v3",
            "output_audio_codec": "mulaw",
            "speech_sample_rate": 8000,
            "pace": self.settings.sarvam_tts_speed,
            "enable_preprocessing": True,
        }

        try:
            if self.http_client:
                response = await self.http_client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers=headers,
                    json=payload,
                    timeout=self.settings.tts_timeout,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.sarvam.ai/text-to-speech",
                        headers=headers,
                        json=payload,
                        timeout=self.settings.tts_timeout,
                    )
            
            if response.status_code != 200:
                self.logger.warning("Sarvam TTS failed with status %d: %s", response.status_code, response.text)
                return b""

            res_data = response.json()
            audio_base64 = res_data.get("audio") or (res_data.get("audios") and res_data["audios"][0])
            if audio_base64:
                return base64.b64decode(audio_base64)
            return b""

        except (asyncio.TimeoutError, httpx.TimeoutException):
            self.logger.warning(f"Sarvam TTS timed out after {self.settings.tts_timeout} seconds")
            return b""
        except Exception:
            self.logger.exception("Sarvam TTS REST API call failed")
            return b""
