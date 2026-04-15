import os
import json
import re
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

BRIDGE_URL = os.environ.get("WA_BRIDGE_URL", "http://localhost:9777")

# Name -> number mapping (e.g. "keya" -> "+447503279587") so the bridge can resolve JID
_contacts_map: dict[str, str] = {}
_raw = os.environ.get("WA_CONTACTS", "{}")
try:
    _contacts_map = {k.strip().lower(): v.strip() for k, v in json.loads(_raw).items() if k and v}
except Exception:
    pass


def _resolve_contact(contact: str) -> str:
    """Resolve a name (e.g. Keya, girlfriend) to a number using WA_CONTACTS; otherwise return as-is."""
    if not contact or "@" in contact:
        return contact.strip()
    key = contact.strip().lower()
    # Allow "Keya" or "your girlfriend Keya" -> take last word as name hint
    if key not in _contacts_map:
        words = key.split()
        for w in reversed(words):
            if len(w) >= 2 and w in _contacts_map:
                return _contacts_map[w]
        # Normalize to digits for bridge: if already all digits, return with + if missing
        digits = re.sub(r"[^0-9]", "", contact)
        if len(digits) >= 7:
            return digits
        return contact.strip()
    return _contacts_map[key]


server = Server("whatsapp")


async def _bridge(method: str, path: str, body: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            resp = await client.get(f"{BRIDGE_URL}{path}")
        else:
            resp = await client.post(f"{BRIDGE_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_message",
            description="Send a WhatsApp message to a contact or group. Use the contact's name or phone number.",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "description": "Contact name, group name, or phone number (with country code, e.g. 447123456789)"},
                    "message": {"type": "string", "description": "Message text to send"},
                },
                "required": ["contact", "message"],
            },
        ),
        Tool(
            name="read_messages",
            description="Read recent messages from a WhatsApp contact or group. Use when the user asks what someone said, the last message, or to check a recent chat. Returns messages received while the bridge is running (real-time).",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "description": "Contact name, group name, or phone number"},
                    "count": {"type": "integer", "description": "Number of messages to fetch (default 5)"},
                },
                "required": ["contact"],
            },
        ),
        Tool(
            name="list_contacts",
            description="List available WhatsApp contacts and groups.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_status",
            description="Check if WhatsApp is connected.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "send_message":
        contact = arguments.get("contact", "")
        message = arguments.get("message", "")
        resolved = _resolve_contact(contact)
        try:
            result = await _bridge("POST", "/send", {"contact": resolved, "message": message})
            if result.get("ok"):
                return [TextContent(type="text", text=f"Message sent to {contact}.")]
            return [TextContent(type="text", text=f"Failed: {result.get('error', 'unknown error')}")]
        except httpx.HTTPStatusError as e:
            body = e.response.json() if e.response.headers.get("content-type", "").startswith("application/json") else {}
            return [TextContent(type="text", text=f"Failed: {body.get('error', str(e))}")]
        except httpx.ConnectError:
            return [TextContent(type="text", text="WhatsApp bridge is not running. Start it with: node bridge.js")]

    elif name == "read_messages":
        contact = arguments.get("contact", "")
        count = arguments.get("count", 5)
        try:
            result = await _bridge("POST", "/read", {"contact": contact, "count": count})
            messages = result.get("messages", [])
            if not messages:
                note = result.get("note", "No messages found.")
                return [TextContent(type="text", text=note)]
            lines = []
            for m in messages:
                lines.append(f"{m['from']}: {m['text']}")
            return [TextContent(type="text", text="\n".join(lines))]
        except httpx.HTTPStatusError as e:
            body = (
                e.response.json()
                if e.response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            msg = body.get("error", str(e))
            return [TextContent(type="text", text=f"Failed: {msg}. Use list_contacts to see available contacts.")]
        except httpx.ConnectError:
            return [TextContent(type="text", text="WhatsApp bridge is not running.")]

    elif name == "list_contacts":
        try:
            result = await _bridge("GET", "/contacts")
            contacts = result.get("contacts", [])
            if not contacts:
                return [TextContent(type="text", text="No contacts found. Send a message first to discover contacts.")]
            lines = [f"{c['name']} ({c['type']})" for c in contacts[:20]]
            return [TextContent(type="text", text="\n".join(lines))]
        except httpx.ConnectError:
            return [TextContent(type="text", text="WhatsApp bridge is not running.")]

    elif name == "check_status":
        try:
            result = await _bridge("GET", "/status")
            connected = result.get("connected", False)
            return [TextContent(type="text", text=f"WhatsApp is {'connected' if connected else 'not connected'}.")]
        except httpx.ConnectError:
            return [TextContent(type="text", text="WhatsApp bridge is not running.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
