#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p data/checkpoints data/training_data data/finetuned references

echo "[render-stack] validating compose configuration"
docker compose -f compose/render-stack.yml config >/dev/null

echo "[render-stack] building and starting render-only services"
docker compose -f compose/render-stack.yml up -d --build

render_wait_attempts() {
  local default_wait_seconds=900
  local render_engine="${RENDER_ENGINE:-fish}"
  local wait_seconds="${RENDER_READY_TIMEOUT_SECONDS:-}"

  if [[ -z "$wait_seconds" ]]; then
    if [[ "$render_engine" == "vllm-omni" || "$render_engine" == "vllm_omni" || "$render_engine" == "vllm" ]]; then
      wait_seconds="${VLLM_OMNI_START_TIMEOUT:-2400}"
    else
      wait_seconds="$default_wait_seconds"
    fi
  fi

  if [[ ! "$wait_seconds" =~ ^[0-9]+$ ]]; then
    wait_seconds="$default_wait_seconds"
  fi

  echo $(((wait_seconds + 4) / 5))
}

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

wait_for "http://127.0.0.1:${RENDER_PORT:-7778}/healthz" "tts-render" "$(render_wait_attempts)"
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
