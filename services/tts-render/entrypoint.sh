#!/usr/bin/env bash
set -euo pipefail
MODEL_PATH="${MODEL_PATH:-/app/data/checkpoints/s2-pro}"
MODEL_REPO="${MODEL_REPO:-fishaudio/s2-pro}"
if [[ ! -f "$MODEL_PATH/codec.pth" ]]; then
  mkdir -p "$MODEL_PATH"
  [[ -n "${HF_ENDPOINT:-}" ]] && export HF_ENDPOINT || unset HF_ENDPOINT
  hf download "$MODEL_REPO" --local-dir "$MODEL_PATH"
fi
cd /app
exec uvicorn app.main:app --host 0.0.0.0 --port 8888 --app-dir /app
