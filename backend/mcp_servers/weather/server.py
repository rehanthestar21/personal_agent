import os
import json
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

API_KEY = os.environ.get("OPENWEATHERMAP_API_KEY", "")
BASE_URL = "https://api.openweathermap.org/data/2.5"
DEFAULT_LOCATION = "London,UK"

server = Server("weather")


async def _fetch(endpoint: str, params: dict) -> dict:
    params["appid"] = API_KEY
    params["units"] = "metric"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_current",
            description="Get current weather conditions for a location. Returns temperature, conditions, humidity, and wind.",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name, e.g. 'London,UK'. Defaults to user's city."},
                },
            },
        ),
        Tool(
            name="get_forecast",
            description="Get weather forecast for the next few hours.",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name. Defaults to user's city."},
                    "hours": {"type": "integer", "description": "How many hours ahead to forecast (max 48). Default 6."},
                },
            },
        ),
        Tool(
            name="will_it_rain",
            description="Quick check: will it rain in the next few hours?",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name. Defaults to user's city."},
                    "hours": {"type": "integer", "description": "How many hours to check. Default 6."},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    location = arguments.get("location", DEFAULT_LOCATION)

    if name == "get_current":
        data = await _fetch("weather", {"q": location})
        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        result = f"{temp}°C (feels like {feels}°C), {desc}, humidity {humidity}%, wind {wind} m/s"
        return [TextContent(type="text", text=result)]

    elif name == "get_forecast":
        hours = min(arguments.get("hours", 6), 48)
        data = await _fetch("forecast", {"q": location})
        steps = hours // 3 or 1
        forecasts = []
        for item in data["list"][:steps]:
            t = item["dt_txt"]
            temp = item["main"]["temp"]
            desc = item["weather"][0]["description"]
            forecasts.append(f"{t}: {temp}°C, {desc}")
        return [TextContent(type="text", text="\n".join(forecasts))]

    elif name == "will_it_rain":
        hours = min(arguments.get("hours", 6), 48)
        data = await _fetch("forecast", {"q": location})
        steps = hours // 3 or 1
        rain_times = []
        for item in data["list"][:steps]:
            desc = item["weather"][0]["main"].lower()
            if "rain" in desc or "drizzle" in desc:
                rain_times.append(item["dt_txt"])

        if rain_times:
            result = f"Yes, rain expected at: {', '.join(rain_times)}"
        else:
            result = f"No rain expected in the next {hours} hours."
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
