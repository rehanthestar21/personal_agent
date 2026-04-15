"""
Run this once to get your Spotify refresh token.

1. Go to https://developer.spotify.com/dashboard
2. Create an app, set redirect URI to http://localhost:8888/callback
3. Copy your Client ID and Client Secret
4. Run: python get_refresh_token.py YOUR_CLIENT_ID YOUR_CLIENT_SECRET
5. It opens a browser. Log in and authorize.
6. Copy the refresh_token it prints into your .env
"""
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
import httpx

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = parse_qs(urlparse(self.path).query)
        auth_code = query.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Done! You can close this tab.</h1>")

    def log_message(self, format, *args):
        pass


def main():
    if len(sys.argv) != 3:
        print("Usage: python get_refresh_token.py CLIENT_ID CLIENT_SECRET")
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]

    auth_url = "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })

    print(f"Opening browser for Spotify authorization...")
    webbrowser.open(auth_url)

    httpd = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    httpd.handle_request()

    if not auth_code:
        print("No auth code received.")
        sys.exit(1)

    resp = httpx.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    resp.raise_for_status()
    tokens = resp.json()

    print(f"\n=== Add this to your .env ===")
    print(f"SPOTIFY_REFRESH_TOKEN={tokens['refresh_token']}")
    print(f"============================\n")


if __name__ == "__main__":
    main()
