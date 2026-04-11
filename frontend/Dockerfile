FROM node:20-slim AS builder

ARG FISH_SPEECH_REF=main

WORKDIR /build
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/fishaudio/fish-speech.git . \
    && git checkout "${FISH_SPEECH_REF}" \
    && cd awesome_webui \
    && npm install \
    && npm run build

FROM nginx:alpine
COPY --from=builder /build/awesome_webui/dist /usr/share/nginx/html
COPY custom /opt/finetune-ui
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
