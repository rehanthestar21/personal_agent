"""TTS with Indian English/Hindi support via Google Cloud. Falls back to OpenAI."""

import asyncio
import base64
import logging
import os
import re

from app.config import Settings

logger = logging.getLogger("vertex.tts")

# Devanagari script range (Hindi, etc.)
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _has_hindi_script(text: str) -> bool:
    """True if text contains Devanagari (Hindi) characters."""
    return bool(DEVANAGARI_RE.search(text))


async def synthesize_speech(text: str, settings: Settings) -> str:
    """
    Synthesize speech to base64 MP3. Uses Google TTS (Indian English/Hindi voices)
    when TTS_USE_GOOGLE=true and GOOGLE_APPLICATION_CREDENTIALS is set, else OpenAI.
    """
    if _use_google_tts(settings):
        try:
            return await _google_tts(text, settings)
        except Exception as e:
            logger.warning("Google TTS failed, falling back to OpenAI: %s", e)
    return await _openai_tts(text, settings)


def _use_google_tts(settings: Settings) -> bool:
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    return getattr(settings, "tts_use_google", False) and bool(creds)


def _google_tts_sync(text: str) -> str:
    """Sync Google TTS; run via asyncio.to_thread."""
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()

    # Indian English for English text, Hindi for Devanagari-heavy text (male voices)
    if _has_hindi_script(text):
        lang_code = "hi-IN"
        voice_name = "hi-IN-Neural2-B"  # Hindi male
    else:
        lang_code = "en-IN"
        voice_name = "en-IN-Neural2-B"  # Indian English male

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=lang_code,
        name=voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=0.95,  # Slightly slower for clarity
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    b64 = base64.b64encode(response.audio_content).decode("ascii")
    logger.debug("tts google voice=%s len=%d", voice_name, len(response.audio_content))
    return b64


async def _google_tts(text: str, settings: Settings) -> str:
    return await asyncio.to_thread(_google_tts_sync, text)


async def _openai_tts(text: str, settings: Settings) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.audio.speech.create(
        model="tts-1",
        voice="ash",
        input=text,
        response_format="mp3",
    )
    return base64.b64encode(response.content).decode("ascii")
