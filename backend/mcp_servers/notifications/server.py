import json
import os
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

NOTIF_FILE = Path(os.environ.get("NOTIF_FILE", ""))

server = Server("notifications")


def _load_notifications(max_age_hours: float = 24) -> list[dict]:
    if not NOTIF_FILE.exists():
        return []

    cutoff = time.time() - (max_age_hours * 3600)
    notifications = []
    with open(NOTIF_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("received_at", 0) >= cutoff:
                    notifications.append(entry)
            except json.JSONDecodeError:
                continue
    return notifications


def _mark_as_read(keys: list[str] | None = None):
    """Mark notifications as read. If keys is None, mark all as read."""
    if not NOTIF_FILE.exists():
        return

    lines = []
    with open(NOTIF_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if keys is None or entry.get("key") in keys:
                    entry["read"] = True
                lines.append(json.dumps(entry))
            except json.JSONDecodeError:
                lines.append(line)

    with open(NOTIF_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_unread_notifications",
            description="Get all unread notifications from the user's phone. Returns app name, title, text, and time for each notification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_filter": {"type": "string", "description": "Optional: filter by app name (e.g. 'WhatsApp', 'Gmail'). Leave empty for all apps."},
                },
            },
        ),
        Tool(
            name="get_recent_notifications",
            description="Get all recent notifications from the last few hours, including read ones.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "number", "description": "How many hours back to look. Default 6."},
                    "app_filter": {"type": "string", "description": "Optional: filter by app name."},
                },
            },
        ),
        Tool(
            name="mark_notifications_read",
            description="Mark all current notifications as read.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_unread_notifications":
        app_filter = arguments.get("app_filter", "").lower()
        notifications = _load_notifications(max_age_hours=24)
        unread = [n for n in notifications if not n.get("read")]

        if app_filter:
            unread = [n for n in unread if app_filter in n.get("app", "").lower()]

        if not unread:
            return [TextContent(type="text", text="No unread notifications.")]

        lines = []
        for n in unread[-20:]:
            ts = time.strftime("%H:%M", time.localtime(n.get("received_at", 0)))
            lines.append(f"[{ts}] {n['app']} - {n['title']}: {n['text']}")

        return [TextContent(type="text", text=f"{len(unread)} unread notifications:\n" + "\n".join(lines))]

    elif name == "get_recent_notifications":
        hours = arguments.get("hours", 6)
        app_filter = arguments.get("app_filter", "").lower()
        notifications = _load_notifications(max_age_hours=hours)

        if app_filter:
            notifications = [n for n in notifications if app_filter in n.get("app", "").lower()]

        if not notifications:
            return [TextContent(type="text", text=f"No notifications in the last {hours} hours.")]

        lines = []
        for n in notifications[-20:]:
            ts = time.strftime("%H:%M", time.localtime(n.get("received_at", 0)))
            read_mark = "" if n.get("read") else " (unread)"
            lines.append(f"[{ts}] {n['app']} - {n['title']}: {n['text']}{read_mark}")

        return [TextContent(type="text", text=f"{len(notifications)} notifications:\n" + "\n".join(lines))]

    elif name == "mark_notifications_read":
        _mark_as_read()
        return [TextContent(type="text", text="All notifications marked as read.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
