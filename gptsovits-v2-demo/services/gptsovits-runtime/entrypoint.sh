#!/usr/bin/env bash
set -euo pipefail

cd /opt/GPT-SoVITS-V2
python /opt/bootstrap/bootstrap.py

export PYTHONPATH="/opt/GPT-SoVITS-V2:/opt/GPT-SoVITS-V2/GPT_SoVITS:${PYTHONPATH:-}"
export version="${GPTSOVITS_VERSION:-v2}"
export bert_path="/opt/GPT-SoVITS-V2/GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
export cnhubert_base_path="/opt/GPT-SoVITS-V2/GPT_SoVITS/pretrained_models/chinese-hubert-base"

exec python api_v2.py -a 0.0.0.0 -p "${GPTSOVITS_API_PORT:-9880}" -c /app/data/tts_infer.yaml
