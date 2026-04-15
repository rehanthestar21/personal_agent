import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("stocks")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_price",
            description="Get current stock/crypto price with daily change.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker (e.g. AAPL, TSLA, NVDA) or crypto (BTC-USD, ETH-USD)"},
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_prices",
            description="Get prices for multiple stocks/crypto at once.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tickers": {"type": "array", "items": {"type": "string"}, "description": "List of tickers"},
                },
                "required": ["tickers"],
            },
        ),
        Tool(
            name="get_market_summary",
            description="Get a quick summary of major market indices.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_ticker",
            description="Find a stock ticker by company name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Company name to search for"},
                },
                "required": ["query"],
            },
        ),
    ]


def _get_quote(ticker: str) -> str:
    try:
        t = yf.Ticker(ticker.upper())
        info = t.fast_info
        price = info.get("lastPrice", 0)
        prev = info.get("previousClose", 0)
        if price and prev:
            change = price - prev
            pct = (change / prev) * 100
            arrow = "+" if change >= 0 else ""
            return f"{ticker.upper()}: ${price:.2f} ({arrow}{change:.2f}, {arrow}{pct:.1f}%)"
        elif price:
            return f"{ticker.upper()}: ${price:.2f}"
        return f"{ticker.upper()}: Price not available"
    except Exception as e:
        return f"{ticker.upper()}: Error - {str(e)[:80]}"


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_price":
        ticker = arguments["ticker"]
        result = _get_quote(ticker)
        return [TextContent(type="text", text=result)]

    elif name == "get_prices":
        tickers = arguments["tickers"]
        lines = [_get_quote(t) for t in tickers]
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "get_market_summary":
        indices = ["^GSPC", "^DJI", "^IXIC", "^FTSE", "BTC-USD"]
        names = {"^GSPC": "S&P 500", "^DJI": "Dow Jones", "^IXIC": "Nasdaq", "^FTSE": "FTSE 100", "BTC-USD": "Bitcoin"}
        lines = []
        for idx in indices:
            try:
                t = yf.Ticker(idx)
                info = t.fast_info
                price = info.get("lastPrice", 0)
                prev = info.get("previousClose", 0)
                if price and prev:
                    pct = ((price - prev) / prev) * 100
                    arrow = "+" if pct >= 0 else ""
                    lines.append(f"{names.get(idx, idx)}: {price:,.2f} ({arrow}{pct:.1f}%)")
            except Exception:
                pass
        return [TextContent(type="text", text="\n".join(lines) if lines else "Could not fetch market data.")]

    elif name == "search_ticker":
        query = arguments["query"]
        try:
            results = yf.Search(query)
            quotes = results.quotes[:5] if hasattr(results, 'quotes') else []
            if not quotes:
                return [TextContent(type="text", text=f"No results for '{query}'")]
            lines = [f"{q.get('symbol', '?')} - {q.get('shortname', q.get('longname', ''))}" for q in quotes]
            return [TextContent(type="text", text="\n".join(lines))]
        except Exception:
            return [TextContent(type="text", text=f"Search failed for '{query}'. Try the ticker directly.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
