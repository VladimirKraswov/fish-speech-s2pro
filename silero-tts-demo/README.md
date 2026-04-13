# Silero TTS Demo

Этот каталог содержит полностью автономное демонстрационное окружение для `Silero TTS` с упором на качественный русский синтез.

- `silero-runtime` автоматически скачивает официальную русскую модель `v5_ru` при первом старте
- `silero-frontend` поднимает отдельную страницу на `7072`
- проект живёт в собственной папке и не зависит от `gptsovits-v2-demo` или корневого `fish-speech` стека

В демо доступны:

- выбор диктора: `aidar`, `baya`, `kseniya`, `xenia`, `eugene`
- выбор sample rate: `8000`, `24000`, `48000`
- опции `put_accent` и `put_yo`
- SSML-режим для пауз
- синтез длинного обычного текста с автоматическим разбиением по предложениям

Источники модели и параметров:

- официальный репозиторий: [snakers4/silero-models](https://github.com/snakers4/silero-models)
- SSML wiki: [Silero Models Wiki / SSML](https://github.com/snakers4/silero-models/wiki/SSML)

## Требования

- Debian / Ubuntu с Docker
- Docker Compose v2
- NVIDIA Driver
- NVIDIA Container Toolkit
- GPU не обязательна, но для сервера с `RTX 5090` runtime по умолчанию использует `cuda`

## One-Command Deploy

```bash
git clone <этот-репозиторий>
cd fish-speech-s2pro/silero-tts-demo
cp .env.example .env
make deploy
```

После запуска:

- frontend: `http://127.0.0.1:7072`
- runtime API: `http://127.0.0.1:7090`

Если заходите с другой машины, замените `127.0.0.1` на IP сервера.

## Что происходит на первом старте

`silero-runtime`:

1. Проверяет наличие `v5_ru.pt` в `data/models`
2. Если файла нет, скачивает его с официального CDN `models.silero.ai`
3. Загружает модель на `cuda`, если GPU доступна, иначе автоматически откатывается на `cpu`

Все кэши и скачанные данные остаются внутри этой папки:

- `data/models`

## Команды

```bash
make build
make up
make down
make logs
make ps
make config
make health
make deploy
```

Самые полезные логи:

```bash
docker compose -f docker-compose.yml logs -f silero-runtime
docker compose -f docker-compose.yml logs -f silero-frontend
```

## Возможности страницы

- быстро переключать голоса и частоту дискретизации
- проверять автоударения и `ё`
- вставлять длинный русский текст
- использовать SSML c `<speak>` и `<break time="..."/>`
- сразу слушать результат в браузере и скачивать WAV

## Переменные окружения

- `SILERO_FRONTEND_PORT=7072`
- `SILERO_API_PORT=7090`
- `SILERO_DEVICE=cuda`
- `SILERO_THREADS=4`
- `SILERO_MODEL_URL=https://models.silero.ai/models/tts/ru/v5_ru.pt`
- `SILERO_MODEL_ID=v5_ru`
- `SILERO_LANGUAGE=ru`
- `SILERO_DEFAULT_SPEAKER=xenia`
- `SILERO_DEFAULT_SAMPLE_RATE=48000`
- `SILERO_MAX_TEXT_CHARS=6000`
- `SILERO_CHUNK_CHARS=350`
- `SILERO_SENTENCE_PAUSE_MS=160`
