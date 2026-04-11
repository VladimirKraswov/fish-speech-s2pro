#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/checkpoints data/training_data data/finetuned references

echo "[render-stack] validating compose configuration"
docker compose -f compose/render-stack.yml config >/dev/null

echo "[render-stack] building and starting render-only services"
docker compose -f compose/render-stack.yml up -d --build

wait_for() {
  local url="$1"
  local label="$2"
  local attempts="${3:-180}"

  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[render-stack] $label is ready"
      return 0
    fi
    sleep 5
  done

  echo "[render-stack] $label did not become ready in time: $url" >&2
  return 1
}

echo "[render-stack] current status"
docker compose -f compose/render-stack.yml ps

wait_for "http://127.0.0.1:${RENDER_PORT:-7778}/healthz" "tts-render"
wait_for "http://127.0.0.1:${PREPROCESS_PORT:-7780}/healthz" "text-preprocess"
wait_for "http://127.0.0.1:${FINETUNE_PORT:-7781}/healthz" "finetune-api"
wait_for "http://127.0.0.1:${GATEWAY_PORT:-7777}/healthz" "api-gateway"
wait_for "http://127.0.0.1:${FRONTEND_PORT:-7070}/nginx-healthz" "frontend"

echo "[render-stack] health endpoints"
curl -fsS "http://127.0.0.1:${GATEWAY_PORT:-7777}/healthz"
echo
curl -fsS "http://127.0.0.1:${RENDER_PORT:-7778}/healthz"
echo
curl -fsS "http://127.0.0.1:${PREPROCESS_PORT:-7780}/healthz"
echo
curl -fsS "http://127.0.0.1:${FINETUNE_PORT:-7781}/healthz"
echo
curl -fsS "http://127.0.0.1:${FRONTEND_PORT:-7070}/nginx-healthz"
echo

echo "[render-stack] frontend: http://127.0.0.1:${FRONTEND_PORT:-7070}"
echo "[render-stack] gateway:  http://127.0.0.1:${GATEWAY_PORT:-7777}"
