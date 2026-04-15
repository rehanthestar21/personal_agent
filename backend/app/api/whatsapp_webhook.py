"""Webhook for real-time WhatsApp messages: triggers delegated side agent when enabled."""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("vertex.webhook")

router = APIRouter(prefix="/api/v1", tags=["whatsapp"])


class IncomingMessagePayload(BaseModel):
    jid: str
    from_name: str = Field(default="", alias="from")  # pushName from bridge
    text: str = ""
    id: str = ""
    timestamp: int | None = None


def _get_agent():
    from app.main import get_agent
    return get_agent()


def _get_delegation():
    from app.main import get_delegation_service
    return get_delegation_service()


@router.post("/whatsapp/incoming")
async def whatsapp_incoming(body: IncomingMessagePayload) -> dict:
    """Called by the WhatsApp bridge when a new message arrives. Runs delegated agent if active."""
    logger.info(
        "[webhook] incoming from=%r jid=%s id=%s len=%d",
        body.from_name,
        body.jid,
        body.id or "(none)",
        len(body.text or ""),
    )
    agent = _get_agent()
    delegation = _get_delegation()
    if delegation is None:
        logger.info("[webhook] skip: delegation service not available (WhatsApp disabled?)")
        return {"ok": True, "handled": False, "reason": "no_delegation_service"}
    if not delegation.is_active():
        logger.info("[webhook] skip: delegation not active")
        return {"ok": True, "handled": False, "reason": "not_active"}
    if not delegation.is_delegated_sender(body.from_name, body.jid):
        logger.info(
            "[webhook] skip: sender %r not in delegated_contacts %s",
            body.from_name,
            delegation.get_status().get("delegated_contacts", []),
        )
        return {"ok": True, "handled": False, "reason": "not_delegated"}
    if delegation.is_escalated(body.jid):
        logger.info("[webhook] skip: contact escalated (user taking over) jid=%s", body.jid)
        return {"ok": True, "handled": False, "reason": "escalated"}
    if not delegation.should_process(body.jid, body.id):
        logger.info("[webhook] skip: duplicate message jid=%s id=%s", body.jid, body.id)
        return {"ok": True, "handled": False, "reason": "duplicate"}
    contact_name = body.from_name or body.jid.split("@")[0] or "unknown"
    if delegation.on_incoming_from_delegated_contact(body.jid, contact_name, idle_seconds=240):
        logger.info("[webhook] skip: idle timeout (>4 min), delegation off for %s", contact_name)
        return {"ok": True, "handled": False, "reason": "idle_timeout"}
    asyncio.create_task(
        agent.process_delegated_message(
            contact_name=contact_name,
            contact_jid=body.jid,
            message_text=body.text or "",
            message_id=body.id,
        )
    )
    logger.info("[webhook] delegated task started for %s (jid=%s)", contact_name, body.jid)
    return {"ok": True, "handled": True}
