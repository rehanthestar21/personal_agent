import logging
import os

from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import json
from app.config import get_settings
from app.core.agent import VertexAgent
from app.core.delegation import DelegationService
from app.core.mcp_host import MCPHost, MCPServerConfig
from app.core.prompts import CONTACTS as PROMPT_CONTACTS
from app.api import voice, auth, health, tts, notifications, whatsapp_webhook, escalation, fcm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_agent: VertexAgent | None = None
_mcp_host: MCPHost | None = None
_delegation_service: DelegationService | None = None


def get_agent() -> VertexAgent:
    assert _agent is not None
    return _agent


def get_delegation_service() -> DelegationService | None:
    return _delegation_service


def _build_mcp_configs() -> list[MCPServerConfig]:
    """Build MCP server configs based on which env vars are set."""
    settings = get_settings()
    configs: list[MCPServerConfig] = []
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if getattr(settings, "openweathermap_api_key", None):
        configs.append(MCPServerConfig(
            name="weather",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "weather", "server.py")],
            env={**os.environ, "OPENWEATHERMAP_API_KEY": settings.openweathermap_api_key},
        ))

    if getattr(settings, "tavily_api_key", None):
        configs.append(MCPServerConfig(
            name="search",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "search", "server.py")],
            env={**os.environ, "TAVILY_API_KEY": settings.tavily_api_key},
        ))

    if getattr(settings, "spotify_client_id", None):
        configs.append(MCPServerConfig(
            name="spotify",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "spotify", "server.py")],
            env={
                **os.environ,
                "SPOTIFY_CLIENT_ID": settings.spotify_client_id,
                "SPOTIFY_CLIENT_SECRET": settings.spotify_client_secret,
                "SPOTIFY_REDIRECT_URI": settings.spotify_redirect_uri,
                "SPOTIFY_REFRESH_TOKEN": getattr(settings, "spotify_refresh_token", "") or "",
            },
        ))

    if getattr(settings, "whatsapp_enabled", False):
        configs.append(MCPServerConfig(
            name="whatsapp",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "whatsapp", "server.py")],
            env={
                **os.environ,
                "WA_BRIDGE_URL": settings.whatsapp_bridge_url,
                "WA_CONTACTS": json.dumps(PROMPT_CONTACTS),
            },
        ))

    notif_file = os.path.join(backend_dir, "data", "notifications.jsonl")
    configs.append(MCPServerConfig(
        name="notifications",
        command="python",
        args=[os.path.join(backend_dir, "mcp_servers", "notifications", "server.py")],
        env={**os.environ, "NOTIF_FILE": notif_file},
    ))

    if getattr(settings, "google_enabled", False):
        configs.append(MCPServerConfig(
            name="calendar",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "calendar", "server.py")],
            env={**os.environ},
        ))
        configs.append(MCPServerConfig(
            name="gmail",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "gmail", "server.py")],
            env={**os.environ},
        ))

    configs.append(MCPServerConfig(
        name="stocks",
        command="python",
        args=[os.path.join(backend_dir, "mcp_servers", "stocks", "server.py")],
        env={**os.environ},
    ))

    if getattr(settings, "google_maps_api_key", None):
        configs.append(MCPServerConfig(
            name="maps",
            command="python",
            args=[os.path.join(backend_dir, "mcp_servers", "maps", "server.py")],
            env={**os.environ, "GOOGLE_MAPS_API_KEY": settings.google_maps_api_key},
        ))

    if getattr(settings, "github_token", None):
        configs.append(MCPServerConfig(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_token},
        ))

    return configs


def _resolve_credential_paths():
    """Resolve relative credential paths to absolute (Google/Firebase require absolute paths)."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Load .env from backend dir so GOOGLE_APPLICATION_CREDENTIALS etc. are set even when
    # the process is not started via run.sh (e.g. systemd, docker, or different CWD).
    env_file = os.path.join(backend_dir, ".env")
    if os.path.isfile(env_file):
        load_dotenv(env_file)
    for env_key in ("GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_CREDENTIALS_PATH"):
        path = os.environ.get(env_key, "").strip()
        if not path:
            continue
        if not os.path.isabs(path):
            resolved = os.path.abspath(os.path.join(backend_dir, path))
            os.environ[env_key] = resolved


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _mcp_host, _delegation_service
    _resolve_credential_paths()
    settings = get_settings()
    logging.getLogger("vertex").setLevel(settings.log_level)

    _mcp_host = MCPHost()
    _delegation_service = DelegationService() if getattr(settings, "whatsapp_enabled", False) else None

    for config in _build_mcp_configs():
        _mcp_host.register_server(config)

    await _mcp_host.start_all()

    _agent = VertexAgent(settings, _mcp_host, delegation_service=_delegation_service)

    tools = _mcp_host.get_tools()
    tts_provider = "google (en-IN/hi-IN)" if (getattr(settings, "tts_use_google", False) and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")) else "openai"
    logging.getLogger("vertex").info(
        "Vertex backend started, model=%s, mcp_tools=%d, tts=%s",
        settings.openai_model, len(tools), tts_provider,
    )

    yield

    await _mcp_host.shutdown()


app = FastAPI(title="Vertex", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(voice.router)
app.include_router(tts.router)
app.include_router(auth.router)
app.include_router(health.router)
app.include_router(notifications.router)
app.include_router(whatsapp_webhook.router)
app.include_router(escalation.router)
app.include_router(fcm.router)
