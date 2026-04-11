ARG CUDA_VER=12.9.0
FROM nvidia/cuda:${CUDA_VER}-devel-ubuntu24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev python3-venv \
    curl wget ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv ${VIRTUAL_ENV} \
    && pip install --upgrade pip setuptools wheel \
    && pip install fastapi uvicorn httpx python-multipart

WORKDIR /app
FROM base AS prod

WORKDIR /app
COPY services/tts-live/app /app/app
COPY services/tts-live/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]

FROM base AS dev

WORKDIR /app
COPY services/tts-live/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]
