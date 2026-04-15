import os
from datetime import datetime
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
BASE_URL = "https://maps.googleapis.com/maps/api"

server = Server("maps")


async def _get(endpoint: str, params: dict) -> dict:
    params["key"] = API_KEY
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/{endpoint}/json", params=params)
        resp.raise_for_status()
        return resp.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_directions",
            description="Get directions between two locations. Use for TRAINS, buses, and transit — returns actual schedules. Prefer this over web search for train/rail queries between stations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Starting location (e.g. Coventry Railway Station, London Euston)"},
                    "destination": {"type": "string", "description": "Destination (e.g. London Euston, Coventry)"},
                    "mode": {"type": "string", "enum": ["driving", "transit", "bicycling", "walking"], "description": "Use 'transit' for trains/buses. Default: transit."},
                    "departure_time": {"type": "string", "description": "Optional. For transit: departure time (e.g. '3:00 PM', '15:00', 'now'). Default: now."},
                },
                "required": ["origin", "destination"],
            },
        ),
        Tool(
            name="get_travel_time",
            description="Get travel time between two places. Use transit mode for train/bus times.",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Starting location"},
                    "destination": {"type": "string", "description": "Destination"},
                    "mode": {"type": "string", "enum": ["driving", "transit", "bicycling", "walking"], "description": "Default: transit."},
                },
                "required": ["origin", "destination"],
            },
        ),
        Tool(
            name="search_places",
            description="Search for nearby places (restaurants, cafes, shops, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for (e.g. 'coffee shop', 'pharmacy')"},
                    "near": {"type": "string", "description": "Location to search near. Default: London."},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_directions":
        origin = arguments["origin"]
        dest = arguments["destination"]
        mode = arguments.get("mode", "transit")
        dep_time = arguments.get("departure_time")

        params = {"origin": origin, "destination": dest, "mode": mode}
        if dep_time and mode == "transit":
            if dep_time.strip().lower() == "now":
                params["departure_time"] = "now"
            else:
                dt = None
                for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        dt = datetime.strptime(dep_time.strip(), fmt)
                        if dt.year == 1900:  # strptime default when no year
                            dt = dt.replace(year=datetime.now().year, month=datetime.now().month, day=datetime.now().day)
                        break
                    except ValueError:
                        continue
                if dt is None:
                    try:
                        dt = datetime.fromisoformat(dep_time.replace(" ", "T"))
                    except ValueError:
                        dt = datetime.now()
                params["departure_time"] = str(int(dt.timestamp()))

        data = await _get("directions", params)

        routes = data.get("routes", [])
        if not routes:
            return [TextContent(type="text", text=f"No route found from {origin} to {dest} by {mode}.")]

        leg = routes[0]["legs"][0]
        duration = leg["duration"]["text"]
        distance = leg["distance"]["text"]

        steps = []
        for s in leg.get("steps", [])[:12]:
            instruction = s.get("html_instructions", "")
            instruction = instruction.replace("<b>", "").replace("</b>", "").replace("<div style=\"font-size:0.9em\">", " ").replace("</div>", "")
            step_duration = s.get("duration", {}).get("text", "")
            td = s.get("transit_details", {})
            if td:
                dep = td.get("departure_time", {}).get("text", "")
                arr = td.get("arrival_time", {}).get("text", "")
                line = td.get("line", {}).get("short_name") or td.get("line", {}).get("name", "")
                time_str = f" {dep}–{arr}" if dep and arr else ""
                line_str = f" ({line})" if line else ""
                steps.append(f"- {instruction}{line_str}{time_str} ({step_duration})")
            elif instruction:
                steps.append(f"- {instruction} ({step_duration})")

        result = f"{origin} → {dest} by {mode}: {duration}, {distance}\n" + "\n".join(steps)
        return [TextContent(type="text", text=result)]

    elif name == "get_travel_time":
        origin = arguments["origin"]
        dest = arguments["destination"]
        mode = arguments.get("mode", "transit")

        data = await _get("directions", {
            "origin": origin,
            "destination": dest,
            "mode": mode,
        })

        routes = data.get("routes", [])
        if not routes:
            return [TextContent(type="text", text=f"No route found.")]

        leg = routes[0]["legs"][0]
        return [TextContent(type="text", text=f"{leg['duration']['text']} by {mode} ({leg['distance']['text']})")]

    elif name == "search_places":
        query = arguments["query"]
        near = arguments.get("near", "London, UK")

        async with httpx.AsyncClient() as client:
            geo = await client.get(f"{BASE_URL}/geocode/json", params={"address": near, "key": API_KEY})
            geo_data = geo.json()
            results = geo_data.get("results", [])
            if results:
                loc = results[0]["geometry"]["location"]
                lat, lng = loc["lat"], loc["lng"]
            else:
                lat, lng = 51.5074, -0.1278

            resp = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "X-Goog-Api-Key": API_KEY,
                    "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.currentOpeningHours,places.id",
                },
                json={
                    "textQuery": query,
                    "locationBias": {
                        "circle": {
                            "center": {"latitude": lat, "longitude": lng},
                            "radius": 2000.0,
                        }
                    },
                    "maxResultCount": 5,
                },
            )
            data = resp.json()

        places = data.get("places", [])
        if not places:
            return [TextContent(type="text", text=f"No places found for '{query}' near {near}.")]

        lines = []
        for p in places:
            name_ = p.get("displayName", {}).get("text", "")
            addr = p.get("formattedAddress", "")
            rating = p.get("rating", "")
            is_open = p.get("currentOpeningHours", {}).get("openNow")
            open_text = " (open now)" if is_open else " (closed)" if is_open is False else ""
            rating_text = f" ★{rating}" if rating else ""
            lines.append(f"{name_}{rating_text}{open_text} - {addr}")

        return [TextContent(type="text", text="\n".join(lines))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
