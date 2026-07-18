"""Sarvam speech-to-text client for SAHAYI."""

from __future__ import annotations

import asyncio
import io
import httpx
from sarvamai import SarvamAI

from core.config import get_settings
from utils.logger import get_logger
from voice.audio_codec import pcm_to_wav

# Sarvam STT rejects "auto"; its auto-detect sentinel is "unknown". Any other
# unsupported code also 400s, so we coerce everything to a known value.
_SUPPORTED_STT_LANGS = {
    "unknown", "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN",
    "ta-IN", "te-IN", "en-IN", "gu-IN", "as-IN", "ur-IN", "ne-IN", "kok-IN",
    "ks-IN", "sd-IN", "sa-IN", "sat-IN", "mni-IN", "brx-IN", "mai-IN", "doi-IN",
}


def _coerce_language(language_code: str) -> str:
    """Map a language hint to a Sarvam-supported STT code.

    Args:
        language_code: Incoming hint (e.g. "auto" or "ml-IN").
    Returns:
        A Sarvam-accepted language code ("unknown" for auto/detection).
    Agent:
        Voice
    """

    if not language_code or language_code.lower() == "auto":
        return "unknown"
    return language_code if language_code in _SUPPORTED_STT_LANGS else "unknown"


class SarvamSTTClient:
    """Client for Sarvam speech-to-text transcription using official SDK."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """Initialise STT client settings.

        Args:
            http_client: Shared HTTP client session.
        Returns:
            None.
        Agent:
            Voice
        """

        self.settings = get_settings()
        self.logger = get_logger("sahayi.sarvam_stt")
        self.client = SarvamAI(api_subscription_key=self.settings.sarvam_api_key) if self.settings.sarvam_api_key else None
        self.http_client = http_client

    @staticmethod
    def _normalize(response: object, default_language: str) -> dict[str, object]:
        """Normalize a Sarvam STT SDK response into the pipeline dict.

        Args:
            response: Raw SDK response object/dict.
            default_language: Language to report when detection is unavailable.
        Returns:
            Dictionary with text, confidence, detected language, should_repeat.
        Agent:
            Voice
        """

        confidence = float(getattr(response, 'language_probability', 0.85) or 0.85)
        transcript = str(getattr(response, 'transcript', "")).strip()
        detected = str(getattr(response, 'language_code', "") or default_language) or default_language
        return {
            "text": transcript,
            "confidence": confidence,
            "language": detected,
            # Only ask for a repeat when there is genuinely no transcript.
            # Sarvam's language_probability is a language-ID score and is often
            # low for Indic audio even when transcription is perfect, so gating
            # "repeat" on it made the agent loop on "please repeat" and never
            # reach the red-flag / emergency path.
            "should_repeat": not transcript,
        }

    async def transcribe(self, pcm16_bytes: bytes, language_code: str = "auto", sample_rate: int = 8000) -> dict[str, object]:
        """Transcribe audio and return text with confidence using REST API.

        Sarvam's STT natively supports 8 kHz telephony audio (Twilio media
        streams are 8 kHz mu-law), so we send the audio at its original sample
        rate.

        Args:
            pcm16_bytes: PCM16 mono audio bytes at ``sample_rate``.
            language_code: Sarvam language hint; "auto" enables detection.
            sample_rate: Sample rate of ``pcm16_bytes`` (default 8000 for Twilio).
        Returns:
            Dictionary with text, confidence, detected language, should_repeat.
        Agent:
            Voice
        """

        if not pcm16_bytes or not self.settings.sarvam_api_key:
            return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": True}

        wav_data = pcm_to_wav(pcm16_bytes, sample_rate)
        stt_lang = _coerce_language(language_code)

        headers = {
            "api-subscription-key": self.settings.sarvam_api_key,
        }
        files = {
            "file": ("audio.wav", wav_data, "audio/wav")
        }
        data = {
            "model": self.settings.sarvam_stt_model or "saaras:v3",
            "language_code": stt_lang,
            "mode": "codemix"
        }

        try:
            for attempt in range(2):
                if self.http_client:
                    response = await self.http_client.post(
                        "https://api.sarvam.ai/speech-to-text",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=self.settings.stt_timeout,
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            "https://api.sarvam.ai/speech-to-text",
                            headers=headers,
                            files=files,
                            data=data,
                            timeout=self.settings.stt_timeout,
                        )
                
                if response.status_code in (429, 503) and attempt == 0:
                    await asyncio.sleep(1.0)
                    # Needs fresh files object for retry
                    files = {"file": ("audio.wav", wav_data, "audio/wav")}
                    continue
                    
                if response.status_code != 200:
                    self.logger.warning("Sarvam STT failed with status %d: %s", response.status_code, response.text)
                    return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": False}
                break

            res_data = response.json()
            class StructResponse:
                def __init__(self, d):
                    self.transcript = d.get("transcript")
                    self.language_code = d.get("language_code")
                    self.language_probability = d.get("language_probability")

            return self._normalize(StructResponse(res_data), self.settings.sarvam_language)

        except (asyncio.TimeoutError, httpx.TimeoutException):
            self.logger.warning(f"Sarvam STT timed out after {self.settings.stt_timeout} seconds")
            return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": False}
        except Exception:
            self.logger.exception("Sarvam STT REST API call failed")
            return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": False}

    async def transcribe_file(self, file_bytes: bytes, file_name: str, mime_type: str, language_code: str = "auto") -> dict[str, object]:
        """Transcribe an arbitrary audio file using the REST API.

        Args:
            file_bytes: Raw audio file bytes.
            file_name: Dummy or actual file name payload.
            mime_type: MIME type of the audio.
            language_code: Sarvam language hint; "auto" enables detection.
        Returns:
            Dictionary with text, confidence, detected language, should_repeat.
        Agent:
            Voice
        """
        if not file_bytes or not self.settings.sarvam_api_key:
            return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": True}

        stt_lang = _coerce_language(language_code)
        headers = {
            "api-subscription-key": self.settings.sarvam_api_key,
        }
        files = {
            "file": (file_name, file_bytes, mime_type)
        }
        data = {
            "model": self.settings.sarvam_stt_model or "saaras:v3",
            "language_code": stt_lang,
            "mode": "codemix"
        }

        try:
            for attempt in range(2):
                if self.http_client:
                    response = await self.http_client.post(
                        "https://api.sarvam.ai/speech-to-text",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=self.settings.stt_timeout,
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            "https://api.sarvam.ai/speech-to-text",
                            headers=headers,
                            files=files,
                            data=data,
                            timeout=self.settings.stt_timeout,
                        )
                
                if response.status_code in (429, 503) and attempt == 0:
                    await asyncio.sleep(1.0)
                    files = {"file": (file_name, file_bytes, mime_type)}
                    continue
                    
                if response.status_code != 200:
                    self.logger.warning("Sarvam STT file ingest failed with status %d: %s", response.status_code, response.text)
                    return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": False}
                break

            res_data = response.json()
            class StructResponse:
                def __init__(self, d):
                    self.transcript = d.get("transcript")
                    self.language_code = d.get("language_code")
                    self.language_probability = d.get("language_probability")

            return self._normalize(StructResponse(res_data), self.settings.sarvam_language)

        except (asyncio.TimeoutError, httpx.TimeoutException):
            self.logger.warning(f"Sarvam STT file ingest timed out after {self.settings.stt_timeout} seconds")
            return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": False}
        except Exception:
            self.logger.exception("Sarvam STT file ingest REST API call failed")
            return {"text": "", "confidence": 0.0, "language": language_code, "should_repeat": False}
