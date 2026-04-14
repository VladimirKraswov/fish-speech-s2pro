# Services

Этот каталог содержит физически разнесённые сервисы проекта.

## Сервисы

- `services/api-gateway`
  UI-facing API, orchestration, datasets, references, jobs, events.
- `services/tts-render`
  Качественный synthesis на `s2-pro`.
- `services/tts-live`
  Отдельный low-latency live runtime.
- `services/text-preprocess`
  Нормализация и препроцессинг текста.
- `services/finetune`
  Fine-tuning API и manual training runtime.

У каждого сервиса есть собственные:

- `app/`
- `entrypoint.sh`
- `Dockerfile`

Общий инфраструктурный код лежит в [shared](/fish-speech-s2pro/shared).

## Compose-файлы

Каждый сервис можно поднимать отдельно через свой compose-файл из [compose](fish-speech-s2pro/compose):

- [compose/render.yml](/fish-speech-s2pro/compose/render.yml)
- [compose/live.yml](/fish-speech-s2pro/compose/live.yml)
- [compose/preprocess.yml](/fish-speech-s2pro/compose/preprocess.yml)
- [compose/finetune-api.yml](/fish-speech-s2pro/compose/finetune-api.yml)
- [compose/gateway.yml](/fish-speech-s2pro/compose/gateway.yml)
- [compose/frontend.yml](/fish-speech-s2pro/compose/frontend.yml)
- [compose/render-stack.yml](/fish-speech-s2pro/compose/render-stack.yml)

## Порты

По умолчанию сервисы публикуются так:

- gateway: `7777`
- render: `7778`
- live: `7779`
- preprocess: `7780`
- finetune-api: `7781`
- frontend: `7070`

Основные переменные в `.env`:

- `GATEWAY_PORT`
- `RENDER_PORT`
- `LIVE_PORT`
- `PREPROCESS_PORT`
- `FINETUNE_PORT`
- `FRONTEND_PORT`

## Рекомендуемый режим

Для одной GPU сейчас рекомендован render-only стек:

- `tts-render`
- `text-preprocess`
- `finetune-api`
- `api-gateway`
- `frontend`

Команды:

- `make render-stack-deploy`
- `make render-stack-ps`
- `make render-stack-health`
- `make render-stack-logs`

В этом режиме:

- `live` отключён внутри gateway
- healthchecks остаются зелёными без `tts-live`
- VRAM уходит на качественный render, а не делится между render и live

## Публичный Render API

`api-gateway` теперь предназначен не только для web UI, но и для внешних интеграций.

Полная reference-документация лежит в [docs/API.md](/Volumes/Extend/work/fish-speech-s2pro/docs/API.md).

Что доступно наружу:

- `GET /docs`
- `GET /openapi.json`
- `GET /api/events/history`
- `GET /api/datasets`
- `GET /api/synthesis/capabilities`
- `POST /api/synthesis`
- `GET /api/references`
- `POST /api/references`
- `GET /api/references/{name}/audio`
- `GET /api/finetune`
- `GET /api/finetune/status`
- `POST /api/finetune/validate`
- `POST /api/finetune/start`
- `POST /api/finetune/stop`
- `GET /api/jobs`
- `GET /v1/datasets`
- `GET /v1/events/history`
- `GET /v1/render/capabilities`
- `GET /v1/render/models`
- `GET /v1/render/references`
- `POST /v1/render/speech`
- `POST /v1/render/benchmark`
- `POST /v1/audio/speech`
- `GET /v1/finetune`
- `GET /v1/finetune/status`
- `POST /v1/finetune/validate`
- `POST /v1/finetune/start`
- `POST /v1/finetune/stop`
- `GET /v1/jobs`

`/v1/audio/speech` сделан как OpenAI-style совместимый слой поверх render runtime:

- `input` -> текст для синтеза
- `voice` -> `reference_id` для `fish`, либо нативный `voice` для `vllm-omni`
- `response_format` -> пока только `wav`

`GET /api/synthesis/capabilities` и `GET /v1/render/capabilities` отдают не только дефолты runtime, но и `supported_request_fields`, чтобы клиент мог программно понять, какие render-параметры доступны:

- `fish`: `reference_id`, `references`, `chunk_length`, `temperature`, `top_p`, `repetition_penalty`, `seed`, `normalize`, `use_memory_cache`
- `vllm-omni`: `voice`, `reference_id`, `references`, `speed`, `temperature`, `top_p`, `seed`, `language`, `instructions`, `max_new_tokens`, `initial_codec_chunk_frames`, `x_vector_only_mode`

Это даёт возможность работать с качественным `Fish render` программно, не повторяя логику фронтенда, и покрывает не только synthesis, но и `datasets`, `references`, `jobs`, `events`, `finetune`.

## Render backends

`tts-render` теперь умеет два backend-а:

- `RENDER_ENGINE=fish`
  Текущий in-process Fish Speech runtime с `torch.compile`.
- `RENDER_ENGINE=vllm-omni`
  Managed `vllm-omni serve ...` внутри контейнера, но с тем же internal API для gateway.

Для `vllm-omni` полезны официальные справки:

- [Fish Speech S2 Pro - vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/fish_speech/)
- [Speech API - vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)

Минимальные env для high-concurrency запуска:

```env
RENDER_ENGINE=vllm-omni
ENABLE_VLLM_OMNI=true
RENDER_MAX_CONCURRENCY=2
VLLM_OMNI_GPU_MEMORY_UTILIZATION=0.9
VLLM_OMNI_EXTRA_ARGS=--max-num-seqs 2
```

## Отдельный запуск сервисов

Compose-команды:

- `make render-up`
- `make render-health`
- `make render-logs`
- `make live-up`
- `make live-health`
- `make live-logs`
- `make preprocess-up`
- `make preprocess-health`
- `make finetune-up`
- `make finetune-health`
- `make gateway-up`
- `make gateway-health`
- `make frontend-up`
- `make frontend-health`

Локальные entrypoints без compose:

- `make render`
- `make live`
- `make preprocess`
- `make finetune-api`
- `make gateway`

## Render profile

Render-only bundle использует отдельный профиль:

- `RENDER_STACK_ENABLE_COMPILE=true`
- `COMPILE_CUDAGRAPHS=false`
- `RENDER_STACK_CHUNK_LENGTH=240`
- `OOM_RETRY_CHUNK_CHARS=140`
- `CHUNK_JOIN_SILENCE_MS=90`
- `REFERENCE_MAX_SECONDS=30`
- `REFERENCE_SAMPLE_RATE=24000`
- `REFERENCE_CHANNELS=1`
- `RENDER_MAX_CONCURRENCY=1`
- `RENDER_MAX_QUEUE=8`
- `DTYPE=bfloat16`
- `NORMALIZE_TEXT=true`
- `USE_MEMORY_CACHE=on`

Смысл такой:

- `torch.compile` остаётся включённым
- VRAM-профиль осторожнее за счёт отключённых `cudagraphs`
- длинные запросы защищены через автоматический chunked retry после OOM
- длинные reference-аудио автоматически нормализуются и обрезаются до безопасной длины
- synthesis идёт через bounded queue в gateway, а не через бесконтрольную конкуренцию

Если нужен ещё более агрессивный speed-профиль и карта выдерживает больший VRAM-пик, запускайте так:

```bash
COMPILE_CUDAGRAPHS=true make render-stack-deploy
```

## Порядок старта

Если вы поднимаете сервисы не через `render-stack`, лучший порядок такой:

1. `tts-render`
2. `text-preprocess`
3. `finetune-api`
4. `api-gateway`
5. `frontend`

Если нужен `live`, поднимайте его отдельно и только потом проверяйте полный `make health`.

## Проверки

Базовая проверка проекта:

- `make check`

E2E:

- `make e2e`
- `make e2e-full`
