# Fish Speech Gateway API

Подробная документация по внешнему API для `render`-стека.

Этот API предназначен не только для Web UI, но и для внешних интеграций: backend-сервисов, автоматизаций, CLI-скриптов и production pipeline.

## Base URLs

Обычно стек публикуется так:

- frontend proxy: `http://127.0.0.1:7070`
- gateway direct: `http://127.0.0.1:7777`

Большинство клиентов могут работать через frontend proxy:

- Swagger UI: `GET /docs`
- OpenAPI schema: `GET /openapi.json`

Примеры:

```bash
curl -s http://127.0.0.1:7070/openapi.json | jq '.info'
curl -s http://127.0.0.1:7777/healthz | jq
```

## Общие правила

- Аутентификация сейчас не требуется.
- JSON endpoints используют `Content-Type: application/json`.
- Upload endpoints используют `multipart/form-data`.
- Synthesis endpoints возвращают `audio/wav`.
- Event stream endpoints возвращают `text/event-stream`.
- Все ошибки возвращаются как JSON вида `{"detail":"..."}`.
- Текущий render backend смотрите по полю `engine` в `GET /api/synthesis/capabilities`.

Типичные статусы:

- `200` для успешного JSON/WAV ответа
- `429` если bounded queue synthesis переполнена
- `400` для некорректного входа или runtime validation
- `409` для конфликтов состояния
- `422` для schema validation на уровне FastAPI/Pydantic
- `503` если runtime ещё не готов

## API Surface

Есть два слоя:

- `/api/*`
  Исторический UI-facing API. Полностью пригоден для интеграций.
- `/v1/*`
  Публичный и более явный интеграционный слой.

Если вы пишете новый клиент, лучше использовать `/v1/*`.

## Health And Discovery

### `GET /healthz`

Агрегированное состояние gateway, render, preprocess, finetune и live.

Пример:

```bash
curl -s http://127.0.0.1:7777/healthz | jq
```

Ответ:

```json
{
  "status": "ok",
  "ready": true,
  "services": {
    "render": {"status": "ok", "ready": true, "engine": "fish", "detail": ""},
    "live": {"status": "disabled", "ready": false, "engine": "disabled", "detail": "Live runtime is disabled."},
    "preprocess": {"status": "ok"},
    "finetune": {"status": "ok"}
  }
}
```

### `GET /v1/health`

Alias на `GET /healthz`.

### `GET /api/models`
### `GET /v1/render/models`

Показывает:

- активную `render` модель
- активную `live` модель
- список доступных моделей
- низкоуровневый статус runtime

Пример:

```bash
curl -s http://127.0.0.1:7777/v1/render/models | jq
```

## Render Capabilities

### `GET /api/synthesis/capabilities`
### `GET /v1/render/capabilities`

Возвращают:

- готовность render runtime
- активную модель
- `device`, `dtype`, `compile_enabled`
- текущее состояние gateway queue
- список поддерживаемых output formats
- список поддерживаемых per-request полей
- дефолтные параметры synthesis
- лимиты runtime

Пример:

```bash
curl -s http://127.0.0.1:7777/v1/render/capabilities | jq
```

Ключевые поля ответа:

- `supported_output_formats`
  Сейчас только `["wav"]`
- `supported_request_fields`
  Поля, которые реально можно передать в synthesis request
- `defaults`
  Дефолты runtime
- `limits`
  Ограничения runtime
- `gateway_parallelism`
  Текущее состояние bounded queue в gateway

Список `supported_request_fields` зависит от backend-а:

- `fish`
  `text`, `reference_id`, `references`, `chunk_length`, `top_p`, `repetition_penalty`, `temperature`, `seed`, `normalize`, `use_memory_cache`
- `vllm-omni`
  `text`, `voice`, `reference_id`, `references`, `speed`, `temperature`, `top_p`, `seed`, `language`, `instructions`, `max_new_tokens`, `initial_codec_chunk_frames`, `x_vector_only_mode`

## Render Synthesis

### `POST /api/synthesis`
### `POST /v1/render/speech`

Основной endpoint качественной озвучки через render runtime. Под капотом это может быть либо `fish`, либо `vllm-omni`.

Request body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `text` | string | yes | Текст для синтеза |
| `reference_id` | string | no | Имя сохранённого reference |
| `references` | array | no | Явный low-level список reference payloads |
| `chunk_length` | integer | no | Override chunk length |
| `top_p` | number | no | Sampling top-p |
| `repetition_penalty` | number | no | Штраф за повторения |
| `temperature` | number | no | Температура семплирования |
| `seed` | integer or null | no | Seed для воспроизводимости |
| `normalize` | boolean | no | Нормализовать текст перед synthesis |
| `use_memory_cache` | string | no | Режим memory cache |
| `voice` | string | no | Для `vllm-omni`: нативный voice id. Для Fish Speech upstream-путь обычно использует `"default"` |
| `speed` | number | no | Для `vllm-omni`: скорость речи |
| `language` | string | no | Для `vllm-omni`: language hint |
| `instructions` | string | no | Для `vllm-omni`: текстовая инструкция по стилю |
| `max_new_tokens` | integer | no | Для `vllm-omni`: лимит semantic tokens |
| `initial_codec_chunk_frames` | integer | no | Для `vllm-omni`: размер стартового codec chunk |
| `x_vector_only_mode` | boolean | no | Для `vllm-omni`: speaker-embedding-only режим без transcript-based ICL |

Пример:

```bash
curl -o /tmp/render.wav -X POST http://127.0.0.1:7777/v1/render/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "text":"Привет, это полноценный внешний render API.",
    "temperature":0.62,
    "top_p":0.88,
    "repetition_penalty":1.15,
    "seed":12345,
    "chunk_length":240,
    "normalize":true,
    "use_memory_cache":"on"
  }'
```

Успешный ответ:

- `200 OK`
- `Content-Type: audio/wav`

Ограничения:

- если текст длиннее `max_text_length`, runtime вернёт `400`
- если `reference_id` не существует, gateway вернёт `400`
- если reference требует нормализации и подготовка невозможна, gateway вернёт `409`
- если `gateway` уже держит максимум одновременных render-запросов и очередь заполнена, вернётся `429`
- fish-specific knobs (`chunk_length`, `normalize`, `use_memory_cache`, `repetition_penalty`) не применяются на `vllm-omni`; всегда сверяйтесь с `supported_request_fields`
- для Fish Speech на `vllm-omni` saved `reference_id` разворачивается в `ref_audio/ref_text`, а `voice` по умолчанию фиксируется в `"default"` если вы не передали явный upstream voice id
- при `x_vector_only_mode=true` runtime отправляет только audio-reference без `ref_text`, чтобы соответствовать speaker-embedding-only поведению upstream API

### `POST /api/synthesis/stream`

Сейчас это совместимый endpoint, который возвращает готовый WAV-ответ так же, как обычный synthesis.

Важно:

- это не настоящий progressive render stream
- для настоящего low-latency stream используется отдельный `live`-контур

### `GET /api/synthesis/stream/live`

Stream endpoint поверх `tts-live`.

Query params:

| Param | Type | Required | Description |
| --- | --- | --- | --- |
| `text` | string | yes | Текст для stream synthesis |
| `reference_id` | string | no | Reference id |

Возвращает `audio/wav` stream. В render-only режиме `live` обычно отключён, и тогда endpoint вернёт `409`.

### `POST /api/synthesis/benchmark`
### `POST /v1/render/benchmark`

Измеряет время synthesis и считает `RTF`.

Request body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `target` | `"render"` or `"live"` | no | Что бенчмаркать. По умолчанию `render` |
| `text` | string | yes | Текст |
| `reference_id` | string | no | Reference id |
| `references` | array | no | Явные reference payloads |
| `chunk_length` | integer | no | Override chunk length |
| `top_p` | number | no | Override top-p |
| `repetition_penalty` | number | no | Override repetition penalty |
| `temperature` | number | no | Override temperature |
| `seed` | integer | no | Override seed |
| `normalize` | boolean | no | Override normalize |
| `use_memory_cache` | string | no | Override memory cache |
| `language` | string | no | Для `vllm-omni`: language hint |
| `instructions` | string | no | Для `vllm-omni`: текстовая инструкция по стилю |
| `max_new_tokens` | integer | no | Для `vllm-omni`: лимит semantic tokens |
| `initial_codec_chunk_frames` | integer | no | Для `vllm-omni`: размер стартового codec chunk |
| `x_vector_only_mode` | boolean | no | Для `vllm-omni`: speaker-embedding-only режим без transcript-based ICL |

Пример:

```bash
curl -s -X POST http://127.0.0.1:7777/v1/render/benchmark \
  -H 'Content-Type: application/json' \
  -d '{"text":"Короткий бенчмарк для render runtime."}' | jq
```

Ответ:

```json
{
  "target": "render",
  "engine": "fish",
  "model_path": "/app/data/checkpoints/s2-pro",
  "elapsed_sec": 2.531,
  "audio_sec": 3.114,
  "rtf": 0.813,
  "bytes": 250214
}
```

## OpenAI-Style Audio Endpoint

### `POST /v1/audio/speech`

Совместимый слой поверх render runtime.

Request body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `input` | string | yes | Текст |
| `model` | string | no | Имя render модели. Если не активна, вернётся `409` |
| `voice` | string | no | На `fish` маппится на `reference_id`, на `vllm-omni` уходит как нативный `voice` и для Fish Speech обычно равен `"default"` |
| `reference_id` | string | no | Явный reference id. Имеет приоритет над `voice` |
| `response_format` | `"wav"` | no | Сейчас поддерживается только `wav` |
| `speed` | number | no | Поддерживается только на `vllm-omni` |
| `references` | array | no | Явные reference payloads |
| `chunk_length` | integer | no | Override chunk length |
| `top_p` | number | no | Override top-p |
| `repetition_penalty` | number | no | Override repetition penalty |
| `temperature` | number | no | Override temperature |
| `seed` | integer | no | Override seed |
| `normalize` | boolean | no | Override normalize |
| `use_memory_cache` | string | no | Override memory cache |
| `language` | string | no | Для `vllm-omni`: language hint |
| `instructions` | string | no | Для `vllm-omni`: текстовая инструкция по стилю |
| `max_new_tokens` | integer | no | Для `vllm-omni`: лимит semantic tokens |
| `initial_codec_chunk_frames` | integer | no | Для `vllm-omni`: размер стартового codec chunk |
| `x_vector_only_mode` | boolean | no | Для `vllm-omni`: speaker-embedding-only режим без transcript-based ICL |

Пример:

```bash
curl -o /tmp/render-openai.wav -X POST http://127.0.0.1:7777/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "input":"Привет, это OpenAI-style endpoint поверх render runtime.",
    "voice":"my_reference",
    "response_format":"wav",
    "temperature":0.62,
    "top_p":0.88,
    "repetition_penalty":1.15,
    "seed":42
  }'
```

Особенности:

- на `fish` поле `voice` маппится на `reference_id`
- на `vllm-omni` поле `voice` уходит в нативный speech API, а `reference_id` остаётся отдельным saved reference
- для Fish Speech через `vllm-omni` `reference_id` разворачивается в `ref_audio/ref_text`; если `voice` не указан, runtime сам ставит `"default"`
- `response_format` отличное от `wav` приводит к `422` schema validation
- `speed` отличное от `1.0` приводит к `400` только на `fish`

## References

References нужны для voice conditioning.

### `GET /api/references`
### `GET /v1/render/references`

Список сохранённых reference entries.

### `GET /api/references/{name}`
### `GET /v1/render/references/{name}`

Детали одного reference.

Ответ:

```json
{
  "name": "my_reference",
  "path": "/app/references/my_reference",
  "audio_file": "sample.wav",
  "transcript": "Привет, это тестовый референс.",
  "reference_meta": {
    "normalized": true,
    "duration_sec": 8.421,
    "sample_rate": 24000,
    "channels": 1
  }
}
```

### `GET /api/references/{name}/audio`
### `GET /v1/render/references/{name}/audio`

Скачать WAV reference.

### `POST /api/references`
### `POST /v1/render/references`

Upload reference.

Multipart fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | text | yes | Имя reference |
| `transcript` | text | yes | Reference transcript |
| `replace` | bool | no | Заменить существующий |
| `audio_file` | file | yes | WAV/MP3/FLAC |

Пример:

```bash
curl -s -X POST http://127.0.0.1:7777/v1/render/references \
  -F "name=test_ref" \
  -F "transcript=Привет, это тестовый референс." \
  -F "audio_file=@/absolute/path/to/reference.wav" | jq
```

На сохранении gateway автоматически:

- приводит файл к mono
- приводит к `24000 Hz`
- обрезает до `REFERENCE_MAX_SECONDS`
- сохраняет как `sample.wav`

### `DELETE /api/references/{name}`
### `DELETE /v1/render/references/{name}`

Удалить reference.

## Model Management

### `GET /api/models`
### `GET /api/render/models`
### `GET /v1/render/models`

Показать активную модель и список доступных checkpoints.

### `POST /api/models/activate`
### `POST /api/render/models/activate`
### `POST /v1/render/models/activate`

Request body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | no | Имя модели из `/models` |
| `path` | string | no | Прямой путь к модели. Для `render` это директория с `codec.pth` |
| `target` | `"render"` or `"live"` | no | Куда активировать. По умолчанию `render` |

Нужно передать либо `name`, либо `path`.

Пример:

```bash
curl -s -X POST http://127.0.0.1:7777/v1/render/models/activate \
  -H 'Content-Type: application/json' \
  -d '{"name":"s2-pro","target":"render"}' | jq
```

Пример для кастомного render checkpoint по пути:

```bash
curl -s -X POST http://127.0.0.1:7777/api/render/models/activate \
  -H 'Content-Type: application/json' \
  -d '{"path":"/app/data/checkpoints/my-custom-render","target":"render"}' | jq
```

## Text Preprocess

### `POST /api/text/preprocess`
### `POST /v1/render/preprocess`

Нормализация текста перед synthesis.

Пример:

```bash
curl -s -X POST http://127.0.0.1:7777/v1/render/preprocess \
  -H 'Content-Type: application/json' \
  -d '{"text":"Привет ,   мир !"}' | jq
```

## Datasets

Datasets используются в fine-tune pipeline.

### `GET /api/datasets`
### `GET /v1/datasets`

Список датасетов.

### `POST /api/datasets`
### `POST /v1/datasets`

Request body:

```json
{"name":"my_dataset"}
```

### `GET /api/datasets/{name}`
### `GET /v1/datasets/{name}`

Подробная структура датасета:

- `samples`
- `paired`
- `files`

### `DELETE /api/datasets/{name}`
### `DELETE /v1/datasets/{name}`

Удалить датасет.

### `POST /api/datasets/{name}/files`
### `POST /v1/datasets/{name}/files`

Multipart upload произвольных dataset files.

Multipart fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `files` | file[] | yes | Один или несколько файлов |
| `replace` | bool | no | Разрешить замену |

### `DELETE /api/datasets/{name}/files/{filename}`
### `DELETE /v1/datasets/{name}/files/{filename}`

Удалить файл из датасета.

### `POST /api/datasets/{name}/samples`
### `POST /v1/datasets/{name}/samples`

Создать или заменить sample entry.

Multipart fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `sample_name` | text | yes | Базовое имя sample |
| `transcript_text` | text | no | Текст transcript |
| `replace` | bool | no | Разрешить замену |
| `audio_file` | file | yes | WAV/MP3/FLAC |
| `lab_file` | file | no | `.lab` transcript file |

Нужно передать либо `transcript_text`, либо `lab_file`.

### `PUT /api/datasets/{name}/samples/{sample}`
### `PUT /v1/datasets/{name}/samples/{sample}`

Обновить transcript.

Request body:

```json
{"transcript":"Новый текст для sample."}
```

### `DELETE /api/datasets/{name}/samples/{sample}`
### `DELETE /v1/datasets/{name}/samples/{sample}`

Удалить sample.

## Fine-Tune API

### `GET /api/finetune`
### `GET /v1/finetune`

Вернуть defaults, presets и список datasets.

Пример:

```bash
curl -s http://127.0.0.1:7777/v1/finetune | jq
```

### `GET /api/finetune/status`
### `GET /v1/finetune/status`

Показать текущее состояние fine-tune:

- `state`
- `config`
- `started_at`
- `finished_at`
- `steps`
- `log_tail`
- `job`

### `POST /api/finetune/validate`
### `POST /v1/finetune/validate`

Валидация fine-tune конфигурации.

Поддерживаемые поля:

- `project_name`
- `train_data_dir`
- `output_model_dir`
- `base_model_path`
- `vq_batch_size`
- `vq_num_workers`
- `build_dataset_workers`
- `lora_config`
- `model_repo`
- `hf_endpoint`

Пример:

```bash
curl -s -X POST http://127.0.0.1:7777/v1/finetune/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name":"my_voice",
    "train_data_dir":"/app/data/training_data/my_dataset",
    "lora_config":"r_8_alpha_16"
  }' | jq
```

### `POST /api/finetune/start`
### `POST /v1/finetune/start`

Старт fine-tune job.

Request body тот же, что и у validate.

Ответом будет job record.

### `POST /api/finetune/stop`
### `POST /v1/finetune/stop`

Остановить активный job.

Request body:

```json
{}
```

или

```json
{"job_id":"abc123def456"}
```

## Jobs

### `GET /api/jobs`
### `GET /v1/jobs`

Список synthesis и fine-tune jobs.

### `GET /api/jobs/{job_id}`
### `GET /v1/jobs/{job_id}`

Подробности по одному job.

### `POST /api/jobs/{job_id}/cancel`
### `POST /v1/jobs/{job_id}/cancel`

Отменить job.

## Events

### `GET /api/events`
### `GET /v1/events`

SSE stream событий.

Пример:

```bash
curl -N http://127.0.0.1:7777/v1/events
```

Клиент должен ожидать события формата:

```text
event: hello
data: {"kind":"hello","payload":{"history":[...]}, "timestamp":"..."}
```

и затем обычные runtime events, например:

- `job.created`
- `job.updated`
- `synthesis.started`
- `dataset.created`
- `dataset.updated`
- `reference.saved`
- `model.activated`
- `finetune.started`

### `GET /api/events/history`
### `GET /v1/events/history`

Последние события в JSON.

## Example Workflows

### 0. Переключить render на `vllm-omni`

Официальные справки:

- [Fish Speech S2 Pro - vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/fish_speech/)
- [Speech API - vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/)

Минимальный env:

```env
RENDER_ENGINE=vllm-omni
ENABLE_VLLM_OMNI=true
RENDER_MAX_CONCURRENCY=2
VLLM_OMNI_MODEL=fishaudio/s2-pro
VLLM_OMNI_GPU_MEMORY_UTILIZATION=0.9
VLLM_OMNI_START_TIMEOUT=2400
RENDER_HEALTHCHECK_START_PERIOD=2400s
VLLM_OMNI_EXTRA_ARGS=--max-num-seqs 2
```

### 1. Проверить готовность и доступные knobs

```bash
curl -s http://127.0.0.1:7777/healthz | jq
curl -s http://127.0.0.1:7777/v1/render/capabilities | jq '.supported_request_fields,.defaults,.limits'
```

### 2. Создать reference и использовать его в synthesis

```bash
curl -s -X POST http://127.0.0.1:7777/v1/render/references \
  -F "name=test_ref" \
  -F "transcript=Привет, это тестовый референс." \
  -F "audio_file=@/absolute/path/to/reference.wav" | jq

curl -o /tmp/render-ref.wav -X POST http://127.0.0.1:7777/v1/render/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "text":"Привет, это тест с референсом.",
    "reference_id":"test_ref",
    "temperature":0.62,
    "top_p":0.88,
    "repetition_penalty":1.15,
    "seed":42
  }'
```

### 3. Подготовить и запустить fine-tune

```bash
curl -s -X POST http://127.0.0.1:7777/v1/datasets \
  -H 'Content-Type: application/json' \
  -d '{"name":"my_dataset"}' | jq

curl -s -X POST http://127.0.0.1:7777/v1/finetune/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name":"my_voice",
    "train_data_dir":"/app/data/training_data/my_dataset",
    "lora_config":"r_8_alpha_16"
  }' | jq

curl -s -X POST http://127.0.0.1:7777/v1/finetune/start \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name":"my_voice",
    "train_data_dir":"/app/data/training_data/my_dataset",
    "lora_config":"r_8_alpha_16"
  }' | jq
```

## Runtime Limitations

- Render endpoint сейчас возвращает только `wav`.
- `speed` в OpenAI-style endpoint не поддерживается на `fish`, но доступен на `vllm-omni`.
- `response_format` в OpenAI-style endpoint поддерживается только как `wav`.
- `POST /api/synthesis/stream` сейчас не делает progressive render stream и возвращает готовый WAV.
- Настройки `dtype`, `device`, `compile`, `max_text_length` относятся к runtime и задаются через конфигурацию окружения, а не per-request.
- `live` может быть отключён в render-only deployment. Тогда `live` endpoints будут возвращать `409` или статус `disabled`.
- `vllm-omni` в этом проекте живёт за тем же gateway API, но часть fish-specific knobs на нём игнорируется; ориентируйтесь на `supported_request_fields` и `defaults` из capabilities.
