import json
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.jwt import require_auth
from app.config import Settings, get_settings
from app.core.agent import VertexAgent
from app.core.tts import synthesize_speech

logger = logging.getLogger("vertex.api")

router = APIRouter(prefix="/api/v1", tags=["voice"])


class VoiceRequest(BaseModel):
    transcript: str
    session_id: str | None = None


def _get_agent() -> VertexAgent:
    from app.main import get_agent
    return get_agent()


@router.post("/voice")
async def voice(
    body: VoiceRequest,
    device_id: str = Depends(require_auth),
    agent: VertexAgent = Depends(_get_agent),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    session_id = body.session_id or str(uuid4())
    logger.info("voice_request device=%s session=%s len=%d", device_id, session_id, len(body.transcript))

    async def event_stream():
        start = time.monotonic()

        try:
            async for event in agent.process_stream(body.transcript, session_id=session_id):
                if event["type"] == "status":
                    yield json.dumps(event) + "\n"

                elif event["type"] == "result":
                    llm_ms = int((time.monotonic() - start) * 1000)
                    reply_text = event["reply"]

                    audio_b64 = await synthesize_speech(reply_text, settings)
                    total_ms = int((time.monotonic() - start) * 1000)

                    logger.info(
                        "voice_response session=%s tools=%s llm_ms=%d total_ms=%d",
                        session_id, event.get("tools_used", []), llm_ms, total_ms,
                    )

                    yield json.dumps({
                        "type": "result",
                        "reply": reply_text,
                        "tools_used": event.get("tools_used", []),
                        "session_id": session_id,
                        "latency_ms": total_ms,
                        "audio_base64": audio_b64,
                    }) + "\n"
        except Exception as e:
            logger.exception("voice_stream_error session=%s", session_id)
            
            # User-friendly error message for spoken responses
            error_str = str(e).lower()
            if "spotify" in error_str:
                friendly_error = "Spotify crashed with an error. Can you repeat your request again?"
            elif "whatsapp" in error_str:
                friendly_error = "WhatsApp crashed with an error. Can you repeat your request again?"
            elif "maps" in error_str or "directions" in error_str:
                friendly_error = "Google Maps crashed with an error. Can you repeat your request again?"
            else:
                friendly_error = "I hit a technical hiccup with one of my tools. Can you repeat your request again?"
            
            audio_b64 = await synthesize_speech(friendly_error, settings)
            yield json.dumps({
                "type": "result",
                "reply": friendly_error,
                "tools_used": [],
                "session_id": session_id,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "audio_base64": audio_b64,
            }) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
