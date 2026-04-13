#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

print_runtime_debug() {
  echo "[silero-demo] current status"
  docker compose -f docker-compose.yml ps -a || true
  echo "[silero-demo] runtime logs"
  docker compose -f docker-compose.yml logs --tail=200 silero-runtime || true
  echo "[silero-demo] frontend logs"
  docker compose -f docker-compose.yml logs --tail=100 silero-frontend || true
}

trap 'echo "[silero-demo] deploy failed"; print_runtime_debug' ERR

mkdir -p data/models

echo "[silero-demo] validating compose configuration"
docker compose -f docker-compose.yml config >/dev/null

echo "[silero-demo] building and starting services"
docker compose -f docker-compose.yml up -d --build

wait_for() {
  local url="$1"
  local label="$2"
  local attempts="${3:-240}"

  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[silero-demo] $label is ready"
      return 0
    fi
    if (( i == 1 || i % 12 == 0 )); then
      echo "[silero-demo] waiting for $label ($i/$attempts)"
      docker compose -f docker-compose.yml ps || true
      echo "[silero-demo] recent runtime logs"
      docker compose -f docker-compose.yml logs --tail=30 silero-runtime || true
    fi
    sleep 5
  done

  echo "[silero-demo] $label did not become ready in time: $url" >&2
  return 1
}

wait_for "http://127.0.0.1:${SILERO_API_PORT:-7090}/healthz" "runtime"
wait_for "http://127.0.0.1:${SILERO_FRONTEND_PORT:-7072}/nginx-healthz" "frontend"

echo "[silero-demo] health endpoints"
curl -fsS "http://127.0.0.1:${SILERO_API_PORT:-7090}/healthz"
echo
curl -fsS "http://127.0.0.1:${SILERO_FRONTEND_PORT:-7072}/nginx-healthz"
echo

echo "[silero-demo] frontend: http://127.0.0.1:${SILERO_FRONTEND_PORT:-7072}"
echo "[silero-demo] runtime:  http://127.0.0.1:${SILERO_API_PORT:-7090}"

trap - ERR
