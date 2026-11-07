#!/usr/bin/env bash
# Start the API + Postgres, seed the vocabulary, and expose it through a temporary
# Cloudflare HTTPS tunnel so remote teammates can use it without running Docker.
set -euo pipefail

BACKEND="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND"

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "cloudflared is required (brew install cloudflared)." >&2
    exit 1
fi
if [ ! -f .env ]; then
    echo "backend/.env is missing; copy .env.example and fill it in." >&2
    exit 1
fi

# Remote frontends run in a browser, so they must be listed in CORS_ORIGINS
# (e.g. CORS_ORIGINS=https://my-frontend.example ./scripts/shared-dev.sh).
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000,http://localhost:5173,http://localhost:8081,http://localhost:19006}"
API_PORT="${API_HOST_PORT:-$(grep -E '^API_HOST_PORT=' .env | cut -d= -f2)}"
API_PORT="${API_PORT:-8000}"

cleanup() { docker compose stop api >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

docker compose up -d --build --wait db api
docker compose run --rm api python -m app.seed "$@"

echo "Local API: http://localhost:$API_PORT (docs at /docs)"
echo "Allowed frontend origins: $CORS_ORIGINS"
echo "Share the trycloudflare.com URL printed below. The API has no auth: test data only."
echo "Press Ctrl+C to stop."
cloudflared tunnel --url "http://localhost:$API_PORT"
