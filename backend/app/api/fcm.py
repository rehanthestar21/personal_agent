"""FCM token registration: app sends its FCM token so backend can push on escalation."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.jwt import require_auth
from app.config import get_settings
from app.core.fcm import register_token, send_escalation_push_if_configured

logger = logging.getLogger("vertex.fcm")

router = APIRouter(prefix="/api/v1", tags=["fcm"])


class FcmRegisterBody(BaseModel):
    token: str


@router.post("/fcm/register")
async def fcm_register(
    body: FcmRegisterBody,
    device_id: str = Depends(require_auth),
) -> dict:
    """Register this device's FCM token so the backend can push when someone escalates (e.g. Keya wants you)."""
    if not body.token or not body.token.strip():
        return {"ok": False, "error": "token required"}
    register_token(device_id, body.token)
    return {"ok": True}


@router.post("/fcm/test-push")
async def fcm_test_push(device_id: str = Depends(require_auth)) -> dict:
    """Send a test escalation push to all registered devices. Use to verify alarm notification on Android."""
    settings = get_settings()
    creds_path = (settings.firebase_credentials_path or "").strip()
    send_escalation_push_if_configured(
        contact_name="Test",
        reason="This is a test alarm – if you see this, notifications work.",
        escalation_id="test-push",
        credentials_path=creds_path,
    )
    return {"ok": True, "message": "Test push sent to all registered devices."}
