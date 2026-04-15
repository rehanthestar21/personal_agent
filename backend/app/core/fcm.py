"""FCM: store device tokens and send push when someone escalates to the user."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("vertex.fcm")

FCM_TOKENS_FILE = Path(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
) / "data" / "fcm_tokens.json"

_firebase_app = None


def _get_firebase_app(credentials_path: str):
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    path = (credentials_path or "").strip() or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not path or not os.path.isfile(path):
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
        _firebase_app = firebase_admin.initialize_app(credentials.Certificate(path))
        logger.info("Firebase Admin initialized")
        return _firebase_app
    except Exception as e:
        logger.warning("Firebase Admin init failed: %s", e)
        return None


def _load_tokens() -> dict:
    """device_id -> fcm_token."""
    if not FCM_TOKENS_FILE.exists():
        return {}
    try:
        with open(FCM_TOKENS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_tokens(tokens: dict) -> None:
    FCM_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FCM_TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def register_token(device_id: str, token: str) -> None:
    if not device_id or not token:
        return
    tokens = _load_tokens()
    tokens[device_id] = token.strip()
    _save_tokens(tokens)
    logger.info("FCM token registered for device=%s", device_id[:8] + "...")


def send_escalation_push_if_configured(
    contact_name: str,
    reason: str,
    escalation_id: str,
    credentials_path: str,
) -> None:
    """Send a data-only FCM message to all registered devices so the app can ring and show notification."""
    tokens = _load_tokens()
    if not tokens:
        logger.info("No FCM tokens registered, skip push (open the app so it can register)")
        return
    app = _get_firebase_app(credentials_path)
    if not app:
        logger.info(
            "Firebase not configured, skip push (set GOOGLE_APPLICATION_CREDENTIALS or firebase_credentials_path to service account JSON)"
        )
        return
    try:
        from firebase_admin import messaging
        message = messaging.MulticastMessage(
            data={
                "type": "escalation",
                "escalation_id": escalation_id,
                "contact_name": contact_name or "",
                "reason": (reason or "")[:200],
            },
            tokens=list(tokens.values()),
        )
        resp = messaging.send_each_for_multicast(message)
        logger.info(
            "FCM escalation push: success=%d failure=%d",
            resp.success_count,
            resp.failure_count,
        )
        for i, send_resp in enumerate(resp.responses):
            if not send_resp.success and send_resp.exception:
                logger.warning("FCM send failed for token %d: %s", i, send_resp.exception)
    except Exception as e:
        logger.warning("FCM send failed: %s", e)
