# Vertex

Personal AI agent powered by GPT-5 mini with MCP tool servers.

## Architecture

- **Android app** (Kotlin/Compose) — voice-first interface with tap-to-talk
- **Backend** (Python/FastAPI) — GPT-5 mini agent with MCP tool calling, self-hosted

## Quick Start

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your OpenAI API key, JWT secret, and optional integrations (see .env.example)

# Personal WhatsApp aliases (optional): copy the example and edit phone numbers
cp data/contacts.example.json data/contacts.json

# Optional: seed long-term memory from a short profile (copy and edit)
cp data/personal_context.md.example data/personal_context.md

# Google Calendar / Gmail (optional): copy OAuth client JSON from Google Cloud Console
cp mcp_servers/google_credentials.json.example mcp_servers/google_credentials.json
# Then: python mcp_servers/google_auth.py

# Run it
./run.sh
```

See `backend/.env.example` for optional API keys (weather, search, Spotify, Maps, GitHub, Firebase, etc.).

### Android

1. In Firebase Console, add an Android app and download `google-services.json`.
2. Place it at `android/app/google-services.json` (see `android/app/google-services.json.example` for shape).
3. Open `android/` in Android Studio. Set your backend URL via `BACKEND_URL` in `gradle.properties` or the default in `app/build.gradle.kts`. Build and run.

## Personal data and secrets

Files under `backend/data/` such as `contacts.json`, `personal_context.md`, `delegation.json`, `fcm_tokens.json`, and `vertex_memory.db` are **local only** and listed in `.gitignore`. Do not commit them.

Credential JSON files for Google and Firebase are also gitignored; use the `*.example` / `*.example.json` files in-repo as templates.

If this repo was ever pushed with secrets in history, read [docs/OPEN_SOURCE_SANITIZATION.md](docs/OPEN_SOURCE_SANITIZATION.md).

## License

MIT — see [LICENSE](LICENSE).

## Project status

Phase 1: Voice loop MVP (in progress).
