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

Render-only стек стартует из [compose/render-stack.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/render-stack.yml) и включает:

- `tts-render` на порту `7778`
- `text-preprocess` на порту `7780`
- `finetune-api` на порту `7781`
- `api-gateway` на порту `7777`
- `frontend` на порту `7070`

Внутри этого стека `live` явно отключён, поэтому он не съедает VRAM и не влияет на latency качественного synthesis.

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

Если заходите с другой машины в локальной сети, замените `127.0.0.1` на IP сервера.

## Что важно про первый старт

`tts-render` в render-only стеке запускается с `torch.compile`.

Это означает:
- холодный старт дольше
- первый `healthy` может появиться не сразу
- после прогрева synthesis обычно работает заметно быстрее

Именно поэтому [scripts/deploy-render-stack.sh](/Volumes/Extend/work/fish-speech-s2pro/scripts/deploy-render-stack.sh) ждёт реальной готовности `render`, `gateway` и `frontend`, а не просто старта контейнеров.

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

Если нужен только benchmark без UI:

```bash
curl -s -X POST http://127.0.0.1:7777/api/synthesis/benchmark \
  -H 'Content-Type: application/json' \
  -d '{"target":"render","text":"Загружайте датасеты, обучайте голосовые профили и запускайте качественный синтез речи."}'
```

## Render profile

Render-only стек использует quality-first профиль:

- `DTYPE=bfloat16`
- `RENDER_STACK_ENABLE_COMPILE=true`
- `RENDER_STACK_CHUNK_LENGTH=240`
- `NORMALIZE_TEXT=true`
- `USE_MEMORY_CACHE=on`

Практический смысл:
- качество остаётся высоким
- throughput после прогрева лучше
- старт контейнера дольше, чем в fast-restart режиме

Если нужен более быстрый cold start ценой части производительности после прогрева, можно в `.env` поменять:

```env
RENDER_STACK_ENABLE_COMPILE=false
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
DTYPE=bfloat16
ENABLE_COMPILE=false
RENDER_STACK_ENABLE_COMPILE=true
CHUNK_LENGTH=240
RENDER_STACK_CHUNK_LENGTH=240
NORMALIZE_TEXT=true
USE_MEMORY_CACHE=on
TEMPERATURE=0.62
TOP_P=0.88
REPETITION_PENALTY=1.15
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Замысел тут такой:
- глобальный `ENABLE_COMPILE` оставлен безопасным
- для render-only bundle включается отдельный `RENDER_STACK_ENABLE_COMPILE=true`

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

Файлы compose для этого лежат в каталоге [compose](/Volumes/Extend/work/fish-speech-s2pro/compose):

- [compose/render.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/render.yml)
- [compose/preprocess.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/preprocess.yml)
- [compose/finetune-api.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/finetune-api.yml)
- [compose/gateway.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/gateway.yml)
- [compose/frontend.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/frontend.yml)
- [compose/live.yml](/Volumes/Extend/work/fish-speech-s2pro/compose/live.yml)

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

## Live

`live` сейчас не нужен для качественного render-запуска и не входит в рекомендуемый стек.

Если позже понадобится вернуть его отдельно:

```bash
make live-up
make live-health
```

Но для одного GPU это почти всегда отдельное решение по VRAM и latency, поэтому лучше подключать его уже осознанно и отдельно от render-only режима.

Если нужен полный стек с UI и `live`, поднимайте его отдельно:

```bash
make up
make health
```
