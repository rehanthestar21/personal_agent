import sys
from datetime import datetime, timedelta
from pathlib import Path

from googleapiclient.discovery import build
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).parent.parent))
from google_auth import get_google_creds

server = Server("calendar")

_service = None


def _get_service():
    global _service
    if not _service:
        creds = get_google_creds()
        _service = build("calendar", "v3", credentials=creds)
    return _service


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_events",
            description="Get calendar events for a specific date or date range.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format. Default: today."},
                    "days": {"type": "integer", "description": "Number of days to look ahead. Default 1."},
                },
            },
        ),
        Tool(
            name="create_event",
            description="Create a new calendar event. Reminders default to 1 day + 1 hour + 15 min before.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "start_time": {"type": "string", "description": "Start time in HH:MM format (24h)"},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes. Default 60."},
                    "description": {"type": "string", "description": "Optional event description"},
                    "reminder_minutes": {"type": "array", "items": {"type": "integer"}, "description": "Custom reminder times in minutes before event. Default: [1440, 300, 180, 60, 30] (1 day, 5h, 3h, 1h, 30min)."},
                },
                "required": ["title", "date", "start_time"],
            },
        ),
        Tool(
            name="delete_event",
            description="Delete a calendar event by searching for it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query to find the event to delete"},
                    "date": {"type": "string", "description": "Date to search on, YYYY-MM-DD. Default: today."},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_next_event",
            description="Get the next upcoming calendar event.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_availability",
            description="Check if a specific time slot is free.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "start_time": {"type": "string", "description": "Start time HH:MM"},
                    "end_time": {"type": "string", "description": "End time HH:MM"},
                },
                "required": ["date", "start_time", "end_time"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    svc = _get_service()

    if name == "get_events":
        date_str = arguments.get("date", datetime.now().strftime("%Y-%m-%d"))
        days = arguments.get("days", 1)
        start = datetime.fromisoformat(date_str + "T00:00:00")
        end = start + timedelta(days=days)

        events = svc.events().list(
            calendarId="primary",
            timeMin=start.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute().get("items", [])

        if not events:
            return [TextContent(type="text", text=f"No events for {date_str}.")]

        lines = []
        for e in events:
            start_t = e["start"].get("dateTime", e["start"].get("date", ""))
            if "T" in start_t:
                start_t = start_t[11:16]
            lines.append(f"{start_t} - {e.get('summary', 'No title')}")

        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "create_event":
        title = arguments["title"]
        date = arguments["date"]
        start_time = arguments["start_time"]
        duration = arguments.get("duration_minutes", 60)
        desc = arguments.get("description", "")
        reminder_mins = arguments.get("reminder_minutes", [1440, 300, 180, 60, 30])

        start_dt = datetime.fromisoformat(f"{date}T{start_time}:00")
        end_dt = start_dt + timedelta(minutes=duration)

        event = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/London"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/London"},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": m} for m in reminder_mins],
            },
        }
        if desc:
            event["description"] = desc

        created = svc.events().insert(calendarId="primary", body=event).execute()
        reminder_text = ", ".join(
            f"{m // 1440}d" if m >= 1440 else f"{m // 60}h" if m >= 60 else f"{m}m"
            for m in sorted(reminder_mins, reverse=True)
        )
        return [TextContent(type="text", text=f"Created: {title} on {date} at {start_time} ({duration} min, reminders: {reminder_text} before)")]

    elif name == "delete_event":
        query = arguments["query"]
        date_str = arguments.get("date", datetime.now().strftime("%Y-%m-%d"))
        start = datetime.fromisoformat(date_str + "T00:00:00")
        end = start + timedelta(days=1)

        events = svc.events().list(
            calendarId="primary",
            timeMin=start.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            q=query,
            singleEvents=True,
            maxResults=5,
        ).execute().get("items", [])

        if not events:
            return [TextContent(type="text", text=f"No event matching '{query}' found.")]

        event = events[0]
        svc.events().delete(calendarId="primary", eventId=event["id"]).execute()
        return [TextContent(type="text", text=f"Deleted: {event.get('summary', query)}")]

    elif name == "get_next_event":
        now = datetime.utcnow().isoformat() + "Z"
        events = svc.events().list(
            calendarId="primary",
            timeMin=now,
            singleEvents=True,
            orderBy="startTime",
            maxResults=1,
        ).execute().get("items", [])

        if not events:
            return [TextContent(type="text", text="No upcoming events.")]

        e = events[0]
        start_t = e["start"].get("dateTime", e["start"].get("date", ""))
        return [TextContent(type="text", text=f"Next: {e.get('summary', 'No title')} at {start_t}")]

    elif name == "check_availability":
        date = arguments["date"]
        start_time = arguments["start_time"]
        end_time = arguments["end_time"]

        start_dt = datetime.fromisoformat(f"{date}T{start_time}:00")
        end_dt = datetime.fromisoformat(f"{date}T{end_time}:00")

        events = svc.events().list(
            calendarId="primary",
            timeMin=start_dt.isoformat() + "Z",
            timeMax=end_dt.isoformat() + "Z",
            singleEvents=True,
            maxResults=5,
        ).execute().get("items", [])

        if not events:
            return [TextContent(type="text", text=f"You're free from {start_time} to {end_time} on {date}.")]

        conflicts = [e.get("summary", "Untitled") for e in events]
        return [TextContent(type="text", text=f"Busy: {', '.join(conflicts)}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
