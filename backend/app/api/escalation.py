"""Escalation API: pending escalations for the app to show and ack."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.jwt import require_auth

logger = logging.getLogger("vertex.escalation")

router = APIRouter(prefix="/api/v1", tags=["escalation"])


def _get_delegation():
    from app.main import get_delegation_service
    return get_delegation_service()


@router.get("/escalation/pending")
async def get_pending_escalations(device_id: str = Depends(require_auth)) -> dict:
    """Return unacked escalations so the app can show a notification (e.g. Keya wants you – open WhatsApp)."""
    delegation = _get_delegation()
    if delegation is None:
        return {"pending": []}
    pending = delegation.get_pending_escalations()
    # Return minimal fields for the app; no PII beyond contact name and reason
    out = [
        {
            "id": p.get("id"),
            "contact_name": p.get("contact_name"),
            "reason": (p.get("reason") or "")[:200],
            "timestamp": p.get("timestamp"),
        }
        for p in pending
    ]
    return {"pending": out}


class AckEscalationBody(BaseModel):
    id: str


@router.post("/escalation/ack")
async def ack_escalation(
    body: AckEscalationBody,
    device_id: str = Depends(require_auth),
) -> dict:
    """Mark an escalation as seen so the app stops showing it."""
    delegation = _get_delegation()
    if delegation is None:
        return {"ok": False, "error": "delegation not available"}
    if delegation.ack_escalation(body.id):
        return {"ok": True}
    return {"ok": False, "error": "escalation not found"}
