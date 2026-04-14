#!/usr/bin/env bash
set -euo pipefail
MODEL_PATH="${MODEL_PATH:-/app/data/checkpoints/s2-pro}"
MODEL_REPO="${MODEL_REPO:-fishaudio/s2-pro}"
RENDER_ENGINE="${RENDER_ENGINE:-fish}"
if [[ ! -f "$MODEL_PATH/codec.pth" ]]; then
  mkdir -p "$MODEL_PATH"
  [[ -n "${HF_ENDPOINT:-}" ]] && export HF_ENDPOINT || unset HF_ENDPOINT
  hf download "$MODEL_REPO" --local-dir "$MODEL_PATH"
fi
if [[ "$RENDER_ENGINE" == "vllm-omni" || "$RENDER_ENGINE" == "vllm_omni" || "$RENDER_ENGINE" == "vllm" ]]; then
  command -v vllm-omni >/dev/null 2>&1 || {
    echo "vllm-omni binary is not available inside the tts-render image. Rebuild with ENABLE_VLLM_OMNI=true." >&2
    exit 1
  }
fi
cd /app
exec uvicorn app.main:app --host 0.0.0.0 --port 8888 --app-dir /app
