import asyncio
import base64
from typing import Optional
from core.config import get_settings
from utils.logger import get_logger
from voice.sarvam_tts import SarvamTTSClient

_DEFAULT_THINKING_SOUNDS = {
    "ml-IN": "ഹ്മ്മ്...",
    "hi-IN": "हम्म...",
    "en-IN": "Hmm...",
    "ta-IN": "ஹும்ம்...",
    "kn-IN": "ಹಮ್...",
    "te-IN": "హ్మ్మ్...",
}

class ThinkingSoundManager:
    def __init__(self, tts_client: SarvamTTSClient) -> None:
        self.tts = tts_client
        self.settings = get_settings()
        self.logger = get_logger("sahayi.thinking_sounds")
        self._sounds_cache: dict[str, bytes] = {}

    async def initialize(self) -> None:
        """Pre-synthesize thinking sounds for configured languages."""
        if not self.settings.thinking_sounds_enabled:
            return

        self.logger.info("Initializing thinking sounds cache...")
        for lang, phrase in _DEFAULT_THINKING_SOUNDS.items():
            try:
                # Use a slightly faster pace for the thinking sound so it's snappy
                audio_bytes = await self.tts.synthesize(phrase, target_language=lang)
                if audio_bytes:
                    # Convert to Twilio media payloads for immediate playback
                    self._sounds_cache[lang] = audio_bytes
                    self.logger.debug(f"Cached thinking sound for {lang}")
            except Exception as e:
                self.logger.warning(f"Failed to synthesize thinking sound for {lang}: {e}")

    def get_thinking_payloads(self, stream_sid: str, language: str) -> list[dict]:
        """Get pre-computed Twilio media payloads for a thinking sound.
        
        Args:
            stream_sid: Twilio Stream SID.
            language: Patient's language code.
        Returns:
            List of Twilio media events.
        """
        if not self.settings.thinking_sounds_enabled:
            return []

        # Fallback to English if language not cached
        audio = self._sounds_cache.get(language) or self._sounds_cache.get("en-IN")
        if not audio:
            return []

        # Split into 20ms chunks (160 bytes for 8kHz mu-law)
        frame_bytes = 160
        events = []
        for i in range(0, len(audio), frame_bytes):
            chunk = audio[i:i + frame_bytes]
            if len(chunk) < frame_bytes:
                chunk = chunk + b"\x7f" * (frame_bytes - len(chunk))
            events.append({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode("utf-8")},
            })
        return events
