import os
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

API_KEY = os.environ.get("TAVILY_API_KEY", "")
BASE_URL = "https://api.tavily.com"

server = Server("search")


async def _search(query: str, count: int = 5, topic: str = "general") -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/search",
            json={
                "api_key": API_KEY,
                "query": query,
                "max_results": count,
                "topic": topic,
                "include_answer": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    answer = data.get("answer", "")
    results = data.get("results", [])

    parts = []
    if answer:
        parts.append(f"Summary: {answer}")

    for r in results[:count]:
        title = r.get("title", "")
        content = r.get("content", "")
        url = r.get("url", "")
        parts.append(f"{title}: {content} ({url})")

    return "\n\n".join(parts) if parts else "No results found."


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_web",
            description="Search the web for current information. Use for facts, news, opening hours, prices, or anything that needs up-to-date data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "count": {"type": "integer", "description": "Number of results (default 5, max 10)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_news",
            description="Search for recent news articles.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News search query"},
                    "count": {"type": "integer", "description": "Number of results (default 5, max 10)"},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    query = arguments.get("query", "")
    count = min(arguments.get("count", 5), 10)

    if name == "search_web":
        result = await _search(query, count, "general")
        return [TextContent(type="text", text=result)]

    elif name == "search_news":
        result = await _search(query, count, "news")
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
