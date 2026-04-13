FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

ARG GPT_SOVITS_UPSTREAM_REPO=https://github.com/TZFC/GPT-SoVITS-V2.git
ARG GPT_SOVITS_UPSTREAM_REF=main

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    ffmpeg \
    git \
    git-lfs \
    libsndfile1 \
    libsox-dev \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    sox \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 10 \
    && git lfs install \
    && python -m pip install --upgrade pip setuptools wheel

RUN python -m pip install --index-url https://download.pytorch.org/whl/cu128 \
    torch==2.10.0 \
    torchaudio==2.10.0

COPY services/gptsovits-runtime/requirements.inference.txt /tmp/requirements.inference.txt
RUN python -m pip install -r /tmp/requirements.inference.txt \
    && python -m pip install matplotlib rich nltk soxr pandas gradio==4.24.0 huggingface_hub==0.23.5 \
    && python -m pip check \
    && (python -m nltk.downloader averaged_perceptron_tagger averaged_perceptron_tagger_eng cmudict punkt \
    || python -m nltk.downloader averaged_perceptron_tagger cmudict punkt)

WORKDIR /opt
RUN git clone --depth 1 --branch "${GPT_SOVITS_UPSTREAM_REF}" "${GPT_SOVITS_UPSTREAM_REPO}" /opt/GPT-SoVITS-V2

COPY services/gptsovits-runtime/bootstrap.py /opt/bootstrap/bootstrap.py
COPY services/gptsovits-runtime/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 9880
ENTRYPOINT ["/entrypoint.sh"]
