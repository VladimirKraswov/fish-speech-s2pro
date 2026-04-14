# Fish-Speech S2 Pro Render Stack

Проект сейчас ориентирован в первую очередь на качественный `render`-сценарий на базе `s2-pro`.

Рекомендованный путь запуска:
- `tts-render` для качественной озвучки
- `text-preprocess` для нормализации текста
- `finetune-api` для датасетов и fine-tuning control plane
- `api-gateway` для UI/API orchestration
- `frontend` для веб-интерфейса

`live`-контур вынесен отдельно и не нужен для запуска качественной озвучки.

В репозитории есть два режима запуска:

- рекомендуемый `render-only` стек для качественной озвучки на одной GPU
- полный стек с отдельным `live`, если он понадобится позже

## Что поднимается

Render-only стек стартует из [compose/render-stack.yml](/fish-speech-s2pro/compose/render-stack.yml) и включает:

- `tts-render` на порту `7778`
- `text-preprocess` на порту `7780`
- `finetune-api` на порту `7781`
- `api-gateway` на порту `7777`
- `frontend` на порту `7070`

## Требования

- NVIDIA GPU
- Docker
- NVIDIA Container Toolkit
- Docker Compose v2

Для `s2-pro` лучше ориентироваться на GPU уровня `RTX 5090 / 32 GB VRAM` или близко к этому.

## Быстрый старт

1. Перейдите в проект:
   ```bash
   cd /storage/data/fish-speech-s2pro
   ```
2. Создайте `.env`, если его ещё нет:
   ```bash
   cp .env.example .env
   ```
3. Создайте рабочие папки:
   ```bash
   mkdir -p data/checkpoints data/training_data data/finetuned references
   ```
4. Поднимите render-only стек:
   ```bash
   make render-stack-deploy
   ```
5. Проверьте здоровье сервисов:
   ```bash
   make render-stack-health
   ```

После этого:

- frontend: `http://127.0.0.1:7070`
- gateway: `http://127.0.0.1:7777`
- swagger docs: `http://127.0.0.1:7070/docs`
- openapi schema: `http://127.0.0.1:7070/openapi.json`

Если заходите с другой машины в локальной сети, замените `127.0.0.1` на IP сервера.

## Что важно про первый старт

По умолчанию `tts-render` в render-only стеке запускается с `torch.compile`, но в более VRAM-осторожной конфигурации.

Это означает:
- compile остаётся включён
- `cudagraphs` по умолчанию выключены, чтобы уменьшить пик памяти
- при `CUDA out of memory` длинный текст автоматически переразбивается на более безопасные части и склеивается обратно

Именно поэтому [scripts/deploy-render-stack.sh](/fish-speech-s2pro/scripts/deploy-render-stack.sh) ждёт реальной готовности `render`, `gateway` и `frontend`, а не просто старта контейнеров.

Если у карты есть запас VRAM и нужен ещё более агрессивный профиль, можно включить `cudagraphs` явно:

```bash
COMPILE_CUDAGRAPHS=true make render-stack-deploy
```

## Команды запуска

Основные команды:

```bash
make render-stack-build
make render-stack-up
make render-stack-down
make render-stack-logs
make render-stack-ps
make render-stack-health
make render-stack-deploy
```

Самая удобная серверная команда:

```bash
make render-stack-deploy
```

Она:
- валидирует compose
- собирает образы
- поднимает render-only стек
- ждёт готовности сервисов
- печатает health endpoints и адреса UI/API

Если нужен именно быстрый локальный запуск без ожидания readiness:

```bash
make render-stack-up
```

Если нужен полный стек со всеми сервисами, включая `live`:

```bash
make up
```

Важно:
- `make health` проверяет полный стек и ожидает, что `live` тоже поднят
- для render-only сценария используйте `make render-stack-health`

## Health и логи

Проверка всего render-only стека:

```bash
make render-stack-health
```

Проверка по сервисам:

```bash
make render-health
make gateway-health
make preprocess-health
make finetune-health
make frontend-health
```

Логи:

```bash
make render-logs
make gateway-logs
make frontend-logs
make render-stack-logs
```

Статус контейнеров:

```bash
make render-stack-ps
```

## Проверка synthesis

Проверка модели через gateway:

```bash
curl -s http://127.0.0.1:7777/api/models
```

Прямой тест озвучки:

```bash
curl -o /tmp/render.wav -X POST http://127.0.0.1:7777/api/synthesis \
  -H 'Content-Type: application/json' \
  -d '{"target":"render","text":"Привет, это проверка качественной озвучки через s2-pro."}'
```

Если используете reference, длинные reference-аудио теперь автоматически:

- конвертируются в `sample.wav`
- приводятся к mono / `24000 Hz`
- обрезаются до `REFERENCE_MAX_SECONDS`

Это сделано специально, чтобы длинный reference не выбивал render в `CUDA out of memory`.

Если нужен только benchmark без UI:

```bash
curl -s -X POST http://127.0.0.1:7777/api/synthesis/benchmark \
  -H 'Content-Type: application/json' \
  -d '{"target":"render","text":"Загружайте датасеты, обучайте голосовые профили и запускайте качественный синтез речи."}'
```

## Публичный API

Gateway теперь можно использовать как полноценный внешний API, а не только как backend для web UI.

Полная reference-документация лежит в [docs/API.md](/Volumes/Extend/work/fish-speech-s2pro/docs/API.md).

Основные точки входа:

- `GET /docs` и `GET /openapi.json`
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
- `POST /api/jobs/{job_id}/cancel`
- `GET /v1/datasets`
- `GET /v1/events/history`
- `GET /v1/render/capabilities`
- `GET /api/render/models`
- `GET /v1/render/models`
- `POST /api/render/models/activate`
- `POST /v1/render/models/activate`
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

Примеры:

```bash
curl -s http://127.0.0.1:7777/api/synthesis/capabilities | jq
```

```bash
curl -o /tmp/render.wav -X POST http://127.0.0.1:7777/v1/render/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "text":"Привет, это внешний API для render Fish Audio.",
    "reference_id":"my_reference",
    "temperature":0.62,
    "top_p":0.88,
    "repetition_penalty":1.15
  }'
```

```bash
curl -o /tmp/render.wav -X POST http://127.0.0.1:7777/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "input":"Привет, это OpenAI-style совместимый маршрут поверх render runtime.",
    "voice":"my_reference",
    "response_format":"wav"
  }'
```

Важно:

- при `RENDER_ENGINE=fish` поле `voice` в `/v1/audio/speech` маппится на `reference_id`
- при `RENDER_ENGINE=vllm-omni` поле `voice` уходит в нативный `vllm-omni` speech API, а `reference_id` остаётся отдельным saved reference
- `response_format` сейчас поддерживается только `wav`
- если хотите использовать другой render checkpoint, активировать его можно либо по имени через `POST /api/models/activate` / `POST /v1/render/models/activate`, либо прямым путём через `POST /api/render/models/activate`
- `GET /api/synthesis/capabilities` и `GET /v1/render/capabilities` теперь возвращают `supported_request_fields`, где перечислены поддерживаемые render knobs
- набор render knobs теперь зависит от backend-а:
  - `fish`: `reference_id`, `references`, `chunk_length`, `temperature`, `top_p`, `repetition_penalty`, `seed`, `normalize`, `use_memory_cache`
  - `vllm-omni`: `voice`, `reference_id`, `references`, `speed`, `temperature`, `top_p`, `seed`, `language`, `instructions`, `max_new_tokens`, `initial_codec_chunk_frames`, `x_vector_only_mode`
- fine-tune сценарий тоже доступен через API: датасеты, валидация конфигурации, старт/стоп обучения, просмотр статуса и jobs

## Render profile

Render-only стек использует quality-first профиль:

- `DTYPE=bfloat16`
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
- `NORMALIZE_TEXT=true`
- `USE_MEMORY_CACHE=on`

Практический смысл:
- качество остаётся высоким
- compile остаётся включён
- профиль осторожнее по VRAM, чем compile+cudagraphs
- длинные запросы переживают OOM заметно лучше благодаря автоматическому chunked retry
- gateway держит управляемую очередь synthesis вместо бесконтрольного параллелизма

### vLLM-Omni backend

Для high-concurrency режима render теперь можно переключить backend на `vllm-omni`, сохранив тот же внешний gateway API.

Опора для интеграции:

- [Fish Speech S2 Pro - vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/fish_speech/)
- [Speech API - vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)

Минимальный набор переменных:

```env
RENDER_ENGINE=vllm-omni
ENABLE_VLLM_OMNI=true
RENDER_MAX_CONCURRENCY=2
VLLM_OMNI_MODEL=fishaudio/s2-pro
VLLM_OMNI_GPU_MEMORY_UTILIZATION=0.9
VLLM_OMNI_EXTRA_ARGS=--max-num-seqs 2
```

Что важно:

- `tts-render` в этом режиме поднимает managed `vllm-omni serve ...` внутри контейнера и продолжает отвечать по старому internal API
- `reference_id` автоматически разворачивается в `ref_audio` + `ref_text`
- смена render-модели через `/api/models/activate` остаётся доступной, но для `vllm-omni` это означает restart managed backend-а
- fish-specific knobs (`chunk_length`, `normalize`, `use_memory_cache`, `repetition_penalty`) не применяются к `vllm-omni`; смотрите актуальный список через `/api/synthesis/capabilities`

Если нужен ещё более быстрый synthesis и карта выдерживает больший VRAM-пик, можно в `.env` поменять:

```env
COMPILE_CUDAGRAPHS=true
```

Если хотите осторожно уменьшить латентность на коротких фразах, можно попробовать:

```env
RENDER_STACK_CHUNK_LENGTH=220
```

## Переменные окружения

Основные переменные для render-only режима:

```env
FRONTEND_PORT=7070
GATEWAY_PORT=7777
RENDER_PORT=7778
PREPROCESS_PORT=7780
FINETUNE_PORT=7781

MODEL_PATH=/app/data/checkpoints/s2-pro
RENDER_ENGINE=fish
DTYPE=bfloat16
ENABLE_COMPILE=false
RENDER_STACK_ENABLE_COMPILE=true
COMPILE_CUDAGRAPHS=false
CHUNK_LENGTH=240
RENDER_STACK_CHUNK_LENGTH=240
OOM_RETRY_CHUNK_CHARS=140
CHUNK_JOIN_SILENCE_MS=90
REFERENCE_MAX_SECONDS=30
REFERENCE_SAMPLE_RATE=24000
REFERENCE_CHANNELS=1
RENDER_MAX_CONCURRENCY=1
RENDER_MAX_QUEUE=8
NORMALIZE_TEXT=true
USE_MEMORY_CACHE=on
TEMPERATURE=0.62
TOP_P=0.88
REPETITION_PENALTY=1.15
ENABLE_VLLM_OMNI=true
VLLM_VERSION=0.18.0
VLLM_OMNI_VERSION=
VLLM_OMNI_HOST=127.0.0.1
VLLM_OMNI_PORT=8091
VLLM_OMNI_MODEL=fishaudio/s2-pro
VLLM_OMNI_GPU_MEMORY_UTILIZATION=0.9
VLLM_OMNI_START_TIMEOUT=900
VLLM_OMNI_STAGE_CONFIGS_PATH=
VLLM_OMNI_EXTRA_ARGS=
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Замысел тут такой:
- глобальный `ENABLE_COMPILE` оставлен безопасным
- render-only bundle держит `torch.compile` включённым
- более тяжёлая часть compile-конфигурации вынесена в opt-in через `COMPILE_CUDAGRAPHS=true`
- длинные тексты страхуются через автоматический chunked retry
- входящий render-трафик проходит через bounded queue в gateway; при переполнении возвращается `429`

## Обновление на сервере

Если код уже обновлён:

```bash
cd /storage/data/fish-speech-s2pro
make render-stack-down
make render-stack-deploy
```

Если нужен только rebuild без полного down:

```bash
make render-stack-build
make render-stack-up
make render-stack-health
```

## Независимый запуск сервисов

Каждый сервис можно поднимать отдельно через свой compose-файл:

```bash
make render-up
make preprocess-up
make finetune-up
make gateway-up
make frontend-up
```

Файлы compose для этого лежат в каталоге [compose](/fish-speech-s2pro/compose):

- [compose/render.yml](/fish-speech-s2pro/compose/render.yml)
- [compose/preprocess.yml](/fish-speech-s2pro/compose/preprocess.yml)
- [compose/finetune-api.yml](/fish-speech-s2pro/compose/finetune-api.yml)
- [compose/gateway.yml](/fish-speech-s2pro/compose/gateway.yml)
- [compose/frontend.yml](/fish-speech-s2pro/compose/frontend.yml)
- [compose/live.yml](/fish-speech-s2pro/compose/live.yml)

И отдельно проверять:

```bash
make render-health
make preprocess-health
make finetune-health
make gateway-health
make frontend-health
```

## Fine-tuning

Render-only стек не отключает fine-tuning control plane. После запуска доступны:

- UI: `http://127.0.0.1:7070/finetune/`
- API status: `http://127.0.0.1:7781/internal/finetune/status`
