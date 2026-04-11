ARG CUDA_VER=12.9.0
FROM nvidia/cuda:${CUDA_VER}-devel-ubuntu24.04

ARG PYTORCH_CUDA_TAG=cu129
ARG FISH_SPEECH_REF=main

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV TZ=UTC
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev python3-venv \
    git curl wget ffmpeg libsndfile1 libsox-dev \
    build-essential cmake \
    libportaudio2 portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv ${VIRTUAL_ENV} \
    && python -m pip install --upgrade pip setuptools wheel

WORKDIR /app
RUN git clone https://github.com/fishaudio/fish-speech.git /app/fish-speech \
    && cd /app/fish-speech \
    && git checkout "${FISH_SPEECH_REF}"

WORKDIR /app/fish-speech
RUN python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/${PYTORCH_CUDA_TAG}
RUN python -m pip install -e .
RUN python -m pip install fastapi uvicorn gradio cachetools huggingface-hub numpy python-multipart asgi-lifespan httpx

WORKDIR /app
COPY shared /app/shared
COPY services/finetune/app /app/app
COPY services/finetune/fine_tune_runner.sh /app/fine_tune_runner.sh
COPY services/finetune/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /app/fine_tune_runner.sh

EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]
