import logging

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.auth.jwt import require_auth
from app.config import Settings, get_settings

logger = logging.getLogger("vertex")

router = APIRouter(prefix="/api/v1", tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    voice: str = "ash"


@router.post("/tts", response_class=Response)
async def text_to_speech(
    body: TTSRequest,
    device_id: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> Response:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.audio.speech.create(
        model="tts-1",
        voice=body.voice,
        input=body.text,
        response_format="mp3",
    )

    audio_bytes = response.content
    logger.info("tts_generated device=%s chars=%d bytes=%d", device_id, len(body.text), len(audio_bytes))

    return Response(content=audio_bytes, media_type="audio/mpeg")
