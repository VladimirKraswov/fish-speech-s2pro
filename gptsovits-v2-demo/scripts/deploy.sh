#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

print_runtime_debug() {
  echo "[gptsovits-demo] current status"
  docker compose -f docker-compose.yml ps -a || true
  echo "[gptsovits-demo] runtime logs"
  docker compose -f docker-compose.yml logs --tail=300 gptsovits-runtime || true
}

trap 'echo "[gptsovits-demo] deploy failed"; print_runtime_debug' ERR

mkdir -p data/hf-cache data/torch-cache references

echo "[gptsovits-demo] validating compose configuration"
docker compose -f docker-compose.yml config >/dev/null

echo "[gptsovits-demo] building and starting services"
docker compose -f docker-compose.yml up -d --build

wait_for() {
  local url="$1"
  local label="$2"
  local attempts="${3:-360}"

  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[gptsovits-demo] $label is ready"
      return 0
    fi
    if (( i == 1 || i % 12 == 0 )); then
      echo "[gptsovits-demo] waiting for $label ($i/$attempts)"
      docker compose -f docker-compose.yml ps || true
      echo "[gptsovits-demo] recent runtime logs"
      docker compose -f docker-compose.yml logs --tail=25 gptsovits-runtime || true
    fi
    sleep 5
  done

  echo "[gptsovits-demo] $label did not become ready in time: $url" >&2
  return 1
}

echo "[gptsovits-demo] current status"
docker compose -f docker-compose.yml ps

wait_for "http://127.0.0.1:${GPTSOVITS_GATEWAY_PORT:-7088}/healthz" "gateway"
wait_for "http://127.0.0.1:${GPTSOVITS_FRONTEND_PORT:-7070}/nginx-healthz" "frontend"

echo "[gptsovits-demo] health endpoints"
curl -fsS "http://127.0.0.1:${GPTSOVITS_GATEWAY_PORT:-7088}/healthz"
echo
curl -fsS "http://127.0.0.1:${GPTSOVITS_FRONTEND_PORT:-7070}/nginx-healthz"
echo

echo "[gptsovits-demo] frontend: http://127.0.0.1:${GPTSOVITS_FRONTEND_PORT:-7070}"
echo "[gptsovits-demo] gateway:  http://127.0.0.1:${GPTSOVITS_GATEWAY_PORT:-7088}"

trap - ERR
