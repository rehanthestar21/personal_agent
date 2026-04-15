import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("vertex.api")

router = APIRouter(prefix="/api/v1", tags=["notifications"])

NOTIF_FILE = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / "data" / "notifications.jsonl"


class NotificationPayload(BaseModel):
    app: str
    package: str = ""
    title: str
    text: str
    timestamp: int = 0
    key: str = ""


@router.post("/notifications")
async def receive_notification(body: NotificationPayload) -> dict:
    NOTIF_FILE.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "app": body.app,
        "package": body.package,
        "title": body.title,
        "text": body.text,
        "timestamp": body.timestamp or int(time.time() * 1000),
        "key": body.key,
        "read": False,
        "received_at": time.time(),
    }

    with open(NOTIF_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info("[api] notification stored: %s - %s: %s", body.app, body.title, body.text[:60])
    return {"ok": True}
