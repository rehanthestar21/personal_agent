import os
import json
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN", "")

API_BASE = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"

server = Server("spotify")

_access_token: str = ""


async def _ensure_token() -> str:
    global _access_token
    if _access_token:
        return _access_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": REFRESH_TOKEN,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        _access_token = resp.json()["access_token"]
    return _access_token


async def _api(method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict | None:
    global _access_token
    token = await _ensure_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.request(method, f"{API_BASE}{path}", headers=headers, params=params, json=body)

        if resp.status_code == 401:
            _access_token = ""
            token = await _ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            resp = await client.request(method, f"{API_BASE}{path}", headers=headers, params=params, json=body)

        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        if not resp.content or not resp.content.strip():
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="play_music",
            description="Search for and play a track, artist, album, or playlist on Spotify.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to play (song name, artist, playlist, etc.)"},
                    "type": {"type": "string", "enum": ["track", "artist", "album", "playlist"], "description": "Type of content. Default: track"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="play_pause",
            description="Pause or resume Spotify playback.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["play", "pause", "toggle"], "description": "Action to take. Default: toggle"},
                },
            },
        ),
        Tool(
            name="skip_track",
            description="Skip to next or previous track.",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["next", "previous"], "description": "Default: next"},
                },
            },
        ),
        Tool(
            name="get_now_playing",
            description="Get the currently playing track on Spotify.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="queue_track",
            description="Add a track to the Spotify queue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Track to search for and add to queue"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="set_volume",
            description="Set Spotify playback volume.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "description": "Volume 0-100"},
                },
                "required": ["level"],
            },
        ),
        Tool(
            name="list_devices",
            description="List available Spotify devices (phone, laptop, speaker, etc.).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="transfer_playback",
            description="Transfer Spotify playback to a specific device by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_name": {"type": "string", "description": "Name of the device to transfer to (e.g. 'MacBook Pro', 'Living Room Speaker')"},
                },
                "required": ["device_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "play_music":
        query = arguments.get("query", "")
        search_type = arguments.get("type", "track")
        data = await _api("GET", "/search", params={"q": query, "type": search_type, "limit": 1})

        items_key = f"{search_type}s"
        items = data.get(items_key, {}).get("items", [])
        if not items:
            return [TextContent(type="text", text=f"No {search_type} found for '{query}'")]

        item = items[0]
        uri = item["uri"]
        item_name = item.get("name", query)

        try:
            if search_type == "track":
                await _api("PUT", "/me/player/play", body={"uris": [uri]})
                artist = item.get("artists", [{}])[0].get("name", "")
                return [TextContent(type="text", text=f"Now playing: {item_name} by {artist}")]
            else:
                await _api("PUT", "/me/player/play", body={"context_uri": uri})
                return [TextContent(type="text", text=f"Now playing {search_type}: {item_name}")]
        except Exception:
            return [TextContent(type="text", text=f"Found '{item_name}' but no active Spotify device. Open Spotify on any device first, or say 'list my spotify devices'.")]

    elif name == "play_pause":
        action = arguments.get("action", "toggle")
        if action == "toggle":
            data = await _api("GET", "/me/player")
            if data and data.get("is_playing"):
                action = "pause"
            else:
                action = "play"

        if action == "pause":
            await _api("PUT", "/me/player/pause")
            return [TextContent(type="text", text="Paused.")]
        else:
            await _api("PUT", "/me/player/play")
            return [TextContent(type="text", text="Resumed.")]

    elif name == "skip_track":
        direction = arguments.get("direction", "next")
        await _api("POST", f"/me/player/{direction}")
        return [TextContent(type="text", text=f"Skipped {direction}.")]

    elif name == "get_now_playing":
        data = await _api("GET", "/me/player/currently-playing")
        if not data or not data.get("item"):
            return [TextContent(type="text", text="Nothing is playing right now.")]
        track = data["item"]
        name_ = track.get("name", "Unknown")
        artist = track.get("artists", [{}])[0].get("name", "Unknown")
        return [TextContent(type="text", text=f"Currently playing: {name_} by {artist}")]

    elif name == "queue_track":
        query = arguments.get("query", "")
        data = await _api("GET", "/search", params={"q": query, "type": "track", "limit": 1})
        items = data.get("tracks", {}).get("items", [])
        if not items:
            return [TextContent(type="text", text=f"No track found for '{query}'")]
        track = items[0]
        await _api("POST", "/me/player/queue", params={"uri": track["uri"]})
        artist = track.get("artists", [{}])[0].get("name", "")
        return [TextContent(type="text", text=f"Queued: {track['name']} by {artist}")]

    elif name == "set_volume":
        level = max(0, min(100, arguments.get("level", 50)))
        await _api("PUT", "/me/player/volume", params={"volume_percent": level})
        return [TextContent(type="text", text=f"Volume set to {level}%.")]

    elif name == "list_devices":
        data = await _api("GET", "/me/player/devices")
        devices = data.get("devices", [])
        if not devices:
            return [TextContent(type="text", text="No Spotify devices found. Open Spotify on a device first.")]
        lines = []
        for d in devices:
            active = " (active)" if d.get("is_active") else ""
            lines.append(f"{d['name']} - {d['type']}{active}")
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "transfer_playback":
        device_name = arguments.get("device_name", "").lower()
        data = await _api("GET", "/me/player/devices")
        devices = data.get("devices", [])
        match = None
        for d in devices:
            if device_name in d["name"].lower():
                match = d
                break
        if not match:
            available = ", ".join(d["name"] for d in devices) if devices else "none found"
            return [TextContent(type="text", text=f"Device '{device_name}' not found. Available: {available}")]
        await _api("PUT", "/me/player", body={"device_ids": [match["id"]], "play": True})
        return [TextContent(type="text", text=f"Transferred playback to {match['name']}.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
