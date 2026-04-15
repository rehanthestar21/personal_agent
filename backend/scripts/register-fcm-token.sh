#!/usr/bin/env bash
# Manual FCM token registration when the app can't reach the backend.
# Usage:
#   1. On your phone: open Vertex app, tap "Copy FCM token", paste the token somewhere.
#   2. Run: ./scripts/register-fcm-token.sh "PASTE_YOUR_FCM_TOKEN_HERE"
#   3. Then run the test-push curl to send a test notification.

set -e
BACKEND_URL="${VERTEX_BACKEND_URL:-http://localhost:8000}"
TOKEN="$1"
if [ -z "$TOKEN" ]; then
  echo "Usage: $0 <FCM_TOKEN>"
  echo "  Get the token from the app: tap 'Copy FCM token', then paste it here in quotes."
  exit 1
fi

echo "Getting access token..."
AUTH_RESP=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/device" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"manual-fcm-setup"}')
ACCESS_TOKEN=$(echo "$AUTH_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
if [ -z "$ACCESS_TOKEN" ]; then
  echo "Failed to get access token. Is the backend running at $BACKEND_URL?"
  echo "$AUTH_RESP"
  exit 1
fi

echo "Registering FCM token with backend..."
REG_RESP=$(curl -s -X POST "$BACKEND_URL/api/v1/fcm/register" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN\"}")
echo "$REG_RESP"
if echo "$REG_RESP" | grep -q '"ok":true'; then
  echo ""
  echo "Done. Now run test-push:"
  echo "  curl -X POST \"$BACKEND_URL/api/v1/fcm/test-push\" -H \"Authorization: Bearer $ACCESS_TOKEN\""
else
  echo "Registration may have failed. Check response above."
  exit 1
fi
