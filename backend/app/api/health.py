import os

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    use_google = getattr(settings, "tts_use_google", False)
    creds_file_exists = os.path.isfile(creds_path) if creds_path else False
    tts_active = "google (en-IN/hi-IN)" if (use_google and creds_file_exists) else "openai"
    return {
        "status": "ok",
        "service": "vertex",
        "tts": tts_active,
        "tts_google_creds_path_set": bool(creds_path),
        "tts_google_creds_file_exists": creds_file_exists,
    }
