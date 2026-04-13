FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    libsndfile1 \
    python3 \
    python3-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10 \
    && python -m pip install --upgrade pip setuptools wheel

RUN python -m pip install --index-url https://download.pytorch.org/whl/cu128 \
    torch==2.10.0 \
    torchaudio==2.10.0

COPY services/silero-runtime/requirements.txt /tmp/requirements.txt
RUN python -m pip install -r /tmp/requirements.txt

WORKDIR /app
COPY services/silero-runtime/app /app/app
COPY services/silero-runtime/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
