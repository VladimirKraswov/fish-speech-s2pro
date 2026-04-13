#!/usr/bin/env bash
set -euo pipefail

cd /opt/GPT-SoVITS-V2
echo "[gptsovits-runtime] bootstrap starting"
python /opt/bootstrap/bootstrap.py
echo "[gptsovits-runtime] bootstrap finished"

export PYTHONPATH="/opt/GPT-SoVITS-V2:/opt/GPT-SoVITS-V2/GPT_SoVITS:${PYTHONPATH:-}"
export version="${GPTSOVITS_VERSION:-v2}"
export bert_path="/opt/GPT-SoVITS-V2/GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
export cnhubert_base_path="/opt/GPT-SoVITS-V2/GPT_SoVITS/pretrained_models/chinese-hubert-base"

echo "[gptsovits-runtime] launching api_v2.py on port ${GPTSOVITS_API_PORT:-9880}"
exec python api_v2.py -a 0.0.0.0 -p "${GPTSOVITS_API_PORT:-9880}" -c /app/data/tts_infer.yaml
