ARG BASE_IMAGE=frankleeeee/sglang-omni:dev
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8888

WORKDIR /app

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install fastapi "uvicorn[standard]" httpx pydantic

COPY services/tts-sglang-s2/app /app/app
COPY services/tts-sglang-s2/config /app/config
COPY services/tts-sglang-s2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]
