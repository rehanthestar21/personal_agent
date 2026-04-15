import logging
import os
from dataclasses import dataclass, field

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("vertex.mcp")


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


class MCPHost:
    """Manages MCP server connections and provides LangChain-compatible tools."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._contexts: list = []
        self._tools: list = []

    def register_server(self, config: MCPServerConfig) -> None:
        self._servers[config.name] = config

    async def start_all(self) -> None:
        for name, config in self._servers.items():
            try:
                await self._start_server(name, config)
                logger.info("[mcp:%s] server started", name)
            except Exception as e:
                logger.error("[mcp:%s] FAILED to start: %s", name, e, exc_info=True)

        await self._load_all_tools()

    async def _start_server(self, name: str, config: MCPServerConfig) -> None:
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env if config.env else None,
        )

        ctx = stdio_client(server_params)
        read, write = await ctx.__aenter__()
        self._contexts.append(ctx)

        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()

        self._sessions[name] = session

    async def _load_all_tools(self) -> None:
        self._tools.clear()

        for server_name, session in self._sessions.items():
            try:
                tools = await load_mcp_tools(session)
                for tool in tools:
                    tool.name = f"{server_name}__{tool.name}"

                self._tools.extend(tools)
                tool_names = [t.name.split("__")[1] for t in tools]
                logger.info("[mcp:%s] loaded %d tools: %s", server_name, len(tools), ", ".join(tool_names))
            except Exception as e:
                logger.error("[mcp:%s] FAILED to load tools: %s", server_name, e, exc_info=True)

    def get_tools(self) -> list:
        return self._tools

    async def shutdown(self) -> None:
        for name, session in self._sessions.items():
            try:
                await session.__aexit__(None, None, None)
                logger.info("[mcp:%s] session closed", name)
            except Exception:
                pass

        for ctx in self._contexts:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception:
                pass

        self._sessions.clear()
        self._contexts.clear()
        logger.info("[mcp] host shut down")
