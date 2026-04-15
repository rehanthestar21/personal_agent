"""
Shared Google OAuth helper for Calendar and Gmail MCP servers.

First-time setup:
1. Go to https://console.cloud.google.com
2. Create a project, enable Calendar API and Gmail API
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download the JSON as 'google_credentials.json' into the mcp_servers/ directory
5. Run: python google_auth.py
6. It opens a browser, you authorize, and it saves 'google_token.json'
"""
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

MCP_DIR = Path(__file__).parent
CREDS_FILE = MCP_DIR / "google_credentials.json"
TOKEN_FILE = MCP_DIR / "google_token.json"


def get_google_creds() -> Credentials:
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDS_FILE}. "
                    "Download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=8889)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


if __name__ == "__main__":
    print("Authenticating with Google...")
    creds = get_google_creds()
    print(f"Authenticated. Token saved to {TOKEN_FILE}")
