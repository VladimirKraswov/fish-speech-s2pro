# =============================================
# Fish Speech S2 Pro — Render (High Quality)
# =============================================
ARG CUDA_VER=12.9.0
FROM nvidia/cuda:${CUDA_VER}-devel-ubuntu24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev python3-venv git curl wget \
    ffmpeg libsndfile1 libsox-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv ${VIRTUAL_ENV} && pip install --upgrade pip setuptools wheel

WORKDIR /app

# ==================== PROD STAGE ====================
FROM base AS prod

ARG PYTORCH_CUDA_TAG=cu129
ARG FISH_SPEECH_REF=main
ARG ENABLE_VLLM_OMNI=true
ARG VLLM_VERSION=0.18.0
ARG VLLM_OMNI_VERSION=

# Клонируем и устанавливаем Fish Speech один раз
RUN git clone https://github.com/fishaudio/fish-speech.git /app/fish-speech \
    && cd /app/fish-speech && git checkout "${FISH_SPEECH_REF}"

WORKDIR /app/fish-speech
RUN pip install torch torchaudio --index-url https://download.pytorch.org/whl/${PYTORCH_CUDA_TAG} \
    && pip install -e . \
    && pip install "huggingface_hub[cli]" fastapi uvicorn httpx python-multipart \
    && if [ "${ENABLE_VLLM_OMNI}" = "true" ]; then \
         pip install "vllm==${VLLM_VERSION}" \
         && if [ -n "${VLLM_OMNI_VERSION}" ]; then pip install "vllm-omni==${VLLM_OMNI_VERSION}"; else pip install vllm-omni; fi; \
       fi \
    && python -c "from fish_speech.inference_engine import TTSInferenceEngine; from fish_speech.models.dac.inference import load_model; from fish_speech.models.text2semantic.inference import launch_thread_safe_queue; assert hasattr(TTSInferenceEngine, 'inference') and callable(load_model) and callable(launch_thread_safe_queue)"

WORKDIR /app
COPY services/tts-render/app /app/app
COPY services/tts-render/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]

# ==================== DEV STAGE ====================
FROM base AS dev

ARG PYTORCH_CUDA_TAG=cu129
ARG FISH_SPEECH_REF=main
ARG ENABLE_VLLM_OMNI=true
ARG VLLM_VERSION=0.18.0
ARG VLLM_OMNI_VERSION=

# Те же зависимости, но без копирования кода (он будет монтироваться)
RUN git clone https://github.com/fishaudio/fish-speech.git /app/fish-speech \
    && cd /app/fish-speech && git checkout "${FISH_SPEECH_REF}"

WORKDIR /app/fish-speech
RUN pip install torch torchaudio --index-url https://download.pytorch.org/whl/${PYTORCH_CUDA_TAG} \
    && pip install -e . \
    && pip install "huggingface_hub[cli]" fastapi uvicorn httpx python-multipart \
    && if [ "${ENABLE_VLLM_OMNI}" = "true" ]; then \
         pip install "vllm==${VLLM_VERSION}" \
         && if [ -n "${VLLM_OMNI_VERSION}" ]; then pip install "vllm-omni==${VLLM_OMNI_VERSION}"; else pip install vllm-omni; fi; \
       fi \
    && python -c "from fish_speech.inference_engine import TTSInferenceEngine; from fish_speech.models.dac.inference import load_model; from fish_speech.models.text2semantic.inference import launch_thread_safe_queue; assert hasattr(TTSInferenceEngine, 'inference') and callable(load_model) and callable(launch_thread_safe_queue)"

WORKDIR /app
# Код будет монтироваться через volume, поэтому только entrypoint
COPY services/tts-render/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]
