"""Delegation state for side agents: which contacts Vertex may auto-respond to."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("vertex.delegation")

DELEGATION_FILE = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "data" / "delegation.json"

DEFAULT_STATE = {
    "active": False,
    "delegated_contacts": [],  # e.g. ["Keya"]
    "last_processed": {},  # jid -> message_id (dedupe)
    "thread_id_override": {},  # jid -> thread_id (recovery from corrupted checkpoint)
    "escalated_jids": {},  # jid -> true (stop auto-reply until cleared)
    "pending_escalations": [],  # [{ "id", "contact_name", "contact_jid", "reason", "timestamp", "acked": false }]
    "last_activity_at": {},  # jid -> unix timestamp (for idle timeout)
}


class DelegationService:
    """Persisted delegation: which contacts get auto-replies and dedupe state."""

    def __init__(self) -> None:
        self._state = self._load()

    def _load(self) -> dict:
        if not DELEGATION_FILE.exists():
            return dict(DEFAULT_STATE)
        try:
            with open(DELEGATION_FILE) as f:
                data = json.load(f)
                data.setdefault("active", False)
                data.setdefault("delegated_contacts", [])
                data.setdefault("last_processed", {})
                data.setdefault("thread_id_override", {})
                data.setdefault("escalated_jids", {})
                data.setdefault("pending_escalations", [])
                data.setdefault("last_activity_at", {})
                # Delegation is off until the user explicitly says "respond to X's messages" this run.
                data["active"] = False
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("delegation load failed: %s", e)
            return dict(DEFAULT_STATE)

    def _save(self) -> None:
        DELEGATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DELEGATION_FILE, "w") as f:
            json.dump(self._state, f, indent=2)

    def on_incoming_from_delegated_contact(
        self, jid: str, contact_name: str, idle_seconds: float = 240
    ) -> bool:
        """Update last-activity time; if contact was idle longer than idle_seconds, deactivate and return True (skip). Otherwise return False (process)."""
        import time
        now = time.time()
        last = self._state.setdefault("last_activity_at", {}).get(jid)
        if last is not None and (now - last) > idle_seconds:
            logger.info(
                "idle timeout for jid=%s (%.0fs), stopping delegation for %s",
                jid, now - last, contact_name,
            )
            self.deactivate(contact_name)
            return True
        self._state.setdefault("last_activity_at", {})[jid] = now
        self._save()
        return False

    def activate(self, contact: str) -> None:
        """Start delegating replies to this contact (e.g. 'Keya'). Clears any prior escalation so we resume replying."""
        contact = contact.strip()
        if not contact:
            return
        self.clear_escalation(contact)
        delegated = list(self._state["delegated_contacts"])
        if contact not in delegated:
            delegated.append(contact)
        self._state["delegated_contacts"] = delegated
        self._state["active"] = True
        self._save()
        logger.info("delegation activated for: %s", contact)

    def deactivate(self, contact: str | None = None) -> None:
        """Stop delegating. If contact is None, turn off all delegation."""
        if contact is None:
            self._state["active"] = False
            self._state["delegated_contacts"] = []
        else:
            contact = contact.strip()
            delegated = [c for c in self._state["delegated_contacts"] if c.lower() != contact.lower()]
            self._state["delegated_contacts"] = delegated
            if not delegated:
                self._state["active"] = False
        self._save()
        logger.info("delegation deactivated: %s", contact or "all")

    def is_active(self) -> bool:
        return bool(self._state["active"] and self._state["delegated_contacts"])

    def is_delegated_sender(self, sender_name: str, sender_jid: str) -> bool:
        """True if this sender is in delegated_contacts (match by name)."""
        if not self.is_active():
            return False
        name = (sender_name or "").strip().lower()
        for d in self._state["delegated_contacts"]:
            if d.lower() in name or name in d.lower():
                return True
        return False

    def should_process(self, jid: str, message_id: str) -> bool:
        """True if we have not already processed this message (dedupe)."""
        last = self._state["last_processed"].get(jid)
        if last == message_id:
            return False
        return True

    def mark_processed(self, jid: str, message_id: str) -> None:
        """Record that we processed this message."""
        self._state["last_processed"][jid] = message_id
        self._save()

    def get_thread_id(self, jid: str) -> str:
        """Thread id for delegated conversation; use override if we recovered from corrupted state."""
        override = self._state.get("thread_id_override", {}).get(jid)
        return override or f"delegated_{jid}"

    def set_thread_id_override(self, jid: str, thread_id: str) -> None:
        """After recovering from corrupted history, use this thread_id for future messages."""
        self._state.setdefault("thread_id_override", {})[jid] = thread_id
        self._save()
        logger.info("delegation thread override for %s -> %s", jid, thread_id)

    def is_escalated(self, jid: str) -> bool:
        """True if this contact has asked for the user to take over; we stop auto-replying until cleared."""
        return bool(self._state.get("escalated_jids", {}).get(jid))

    def set_escalated(self, jid: str, contact_name: str, reason: str) -> str | None:
        """Record escalation and stop auto-reply for this contact. Returns escalation id for the app to ack, or None if already escalated (no second push)."""
        if self.is_escalated(jid):
            logger.debug("escalation already active for jid=%s, skip duplicate", jid)
            return None
        import uuid
        esc_id = str(uuid.uuid4())
        self._state.setdefault("escalated_jids", {})[jid] = True
        self._state.setdefault("pending_escalations", []).append({
            "id": esc_id,
            "contact_name": contact_name,
            "contact_jid": jid,
            "reason": reason,
            "timestamp": __import__("time").time(),
            "acked": False,
        })
        self._save()
        logger.info("escalation set for jid=%s contact=%s reason=%s", jid, contact_name, reason[:50])
        return esc_id

    def clear_escalation(self, contact: str) -> None:
        """Clear escalated state for this contact so Vertex can auto-reply again. Contact is name (e.g. Keya)."""
        contact = contact.strip().lower()
        escalated = dict(self._state.get("escalated_jids", {}))
        pending = list(self._state.get("pending_escalations", []))
        jids_to_clear = set()
        for p in pending:
            if p.get("contact_name", "").strip().lower() == contact or contact in (p.get("contact_jid") or "").lower():
                jids_to_clear.add(p.get("contact_jid"))
                p["acked"] = True
        for jid in jids_to_clear:
            escalated.pop(jid, None)
        # Also remove by jid if contact looks like a jid
        for jid in list(escalated):
            if contact in (jid or "").lower():
                escalated.pop(jid, None)
        self._state["escalated_jids"] = escalated
        self._state["pending_escalations"] = pending
        self._save()
        logger.info("escalation cleared for contact=%s", contact)

    def get_pending_escalations(self) -> list[dict]:
        """Return unacked escalations for the app to show and notify."""
        pending = self._state.get("pending_escalations", [])
        return [p for p in pending if not p.get("acked")]

    def ack_escalation(self, escalation_id: str) -> bool:
        """Mark an escalation as seen so the app stops showing it."""
        for p in self._state.get("pending_escalations", []):
            if p.get("id") == escalation_id:
                p["acked"] = True
                self._save()
                return True
        return False

    def get_status(self) -> dict:
        return {
            "active": self._state["active"],
            "delegated_contacts": list(self._state["delegated_contacts"]),
            "escalated": list(self._state.get("escalated_jids", {}).keys()),
        }
