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

Общий инфраструктурный код лежит в [shared](/Volumes/Extend/work/fish-speech-s2pro/shared). Legacy `backend/` runtime больше не участвует в сборке.

## Compose-файлы

Каждый сервис можно поднимать отдельно через свой compose-файл из [compose](/Volumes/Extend/work/fish-speech-s2pro/compose):

- [compose/render.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/render.yml)
- [compose/live.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/live.yml)
- [compose/preprocess.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/preprocess.yml)
- [compose/finetune-api.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/finetune-api.yml)
- [compose/gateway.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/gateway.yml)
- [compose/frontend.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/frontend.yml)
- [compose/render-stack.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/render-stack.yml)

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
- `RENDER_STACK_CHUNK_LENGTH=240`
- `DTYPE=bfloat16`
- `NORMALIZE_TEXT=true`
- `USE_MEMORY_CACHE=on`

Смысл такой:

- холодный старт дольше
- после прогрева synthesis обычно заметно быстрее
- это лучше подходит для quality-first режима на одной мощной GPU

Глобальный `ENABLE_COMPILE=false` остаётся безопасным дефолтом для остальных режимов, чтобы не раздувать старт и VRAM там, где это не нужно.

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
