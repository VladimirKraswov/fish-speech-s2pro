#!/usr/bin/env bash
set -euo pipefail

BASE_MODEL_PATH="${BASE_MODEL_PATH:-/app/data/checkpoints/s2-pro}"
TRAIN_DATA_DIR="${TRAIN_DATA_DIR:-/app/data/training_data}"
OUTPUT_MODEL_DIR="${OUTPUT_MODEL_DIR:-/app/data/finetuned/my_voice}"
PROJECT_NAME="${PROJECT_NAME:-my_voice}"
VQ_BATCH_SIZE="${VQ_BATCH_SIZE:-8}"
VQ_NUM_WORKERS="${VQ_NUM_WORKERS:-1}"
BUILD_DATASET_WORKERS="${BUILD_DATASET_WORKERS:-4}"
LORA_CONFIG="${LORA_CONFIG:-r_8_alpha_16}"
MODEL_REPO="${MODEL_REPO:-fishaudio/s2-pro}"

WORK_ROOT="/workspace"
WORK_DATA_DIR="${WORK_ROOT}/data"
RESULTS_ROOT="/app/data/finetuned/results"

mkdir -p "$WORK_ROOT" "$RESULTS_ROOT" "$(dirname "$OUTPUT_MODEL_DIR")" "$(dirname "$BASE_MODEL_PATH")"

if [[ ! -d "$TRAIN_DATA_DIR" ]]; then
    echo "Training data directory not found: $TRAIN_DATA_DIR"
    exit 1
fi

if ! find "$TRAIN_DATA_DIR" -type f \( -iname '*.wav' -o -iname '*.mp3' -o -iname '*.flac' \) | grep -q .; then
    echo "No audio files (.wav/.mp3/.flac) found in $TRAIN_DATA_DIR"
    exit 1
fi

if ! find "$TRAIN_DATA_DIR" -type f -iname '*.lab' | grep -q .; then
    echo "No .lab transcription files found in $TRAIN_DATA_DIR"
    exit 1
fi

if [[ ! -f "$BASE_MODEL_PATH/codec.pth" ]]; then
    echo "Base model not found in $BASE_MODEL_PATH. Downloading ${MODEL_REPO} ..."
    if [[ -n "${HF_ENDPOINT:-}" ]]; then
        export HF_ENDPOINT
    else
        unset HF_ENDPOINT
    fi
    hf download "$MODEL_REPO" --local-dir "$BASE_MODEL_PATH"
fi

rm -rf "$WORK_DATA_DIR"
mkdir -p "$WORK_DATA_DIR"
cp -a "$TRAIN_DATA_DIR/." "$WORK_DATA_DIR/"

cd /app/fish-speech

rm -rf data results
mkdir -p checkpoints
rm -rf checkpoints/s2-pro

ln -s "$WORK_DATA_DIR" data
ln -s "$RESULTS_ROOT" results
ln -s "$BASE_MODEL_PATH" checkpoints/s2-pro

echo "Step 1/4: extracting semantic tokens"
python tools/vqgan/extract_vq.py data \
    --num-workers "$VQ_NUM_WORKERS" \
    --batch-size "$VQ_BATCH_SIZE" \
    --config-name "modded_dac_vq" \
    --checkpoint-path "checkpoints/s2-pro/codec.pth"

echo "Step 2/4: building protobuf dataset"
python tools/llama/build_dataset.py \
    --input "data" \
    --output "data/protos" \
    --text-extension .lab \
    --num-workers "$BUILD_DATASET_WORKERS"

echo "Step 3/4: training LoRA"
python fish_speech/train.py \
    --config-name text2semantic_finetune \
    project="$PROJECT_NAME" \
    +lora@model.model.lora_config="$LORA_CONFIG"

LATEST_CKPT="$(find "results/${PROJECT_NAME}/checkpoints" -maxdepth 1 -type f -name '*.ckpt' | sort | tail -n 1 || true)"
if [[ -z "$LATEST_CKPT" ]]; then
    echo "No checkpoint produced in results/${PROJECT_NAME}/checkpoints"
    exit 1
fi

echo "Step 4/4: merging LoRA into regular weights"
rm -rf "$OUTPUT_MODEL_DIR"
python tools/llama/merge_lora.py \
    --lora-config "$LORA_CONFIG" \
    --base-weight "checkpoints/s2-pro" \
    --lora-weight "$LATEST_CKPT" \
    --output "$OUTPUT_MODEL_DIR"

echo "Done. Merged model saved to: $OUTPUT_MODEL_DIR"
echo "Training artifacts saved under: $RESULTS_ROOT/$PROJECT_NAME"
