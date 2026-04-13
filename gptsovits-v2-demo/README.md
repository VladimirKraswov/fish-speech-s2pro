# GPT-SoVITS V2 Demo

Этот каталог содержит полностью автономное демонстрационное окружение для [GPT-SoVITS-V2](https://github.com/TZFC/GPT-SoVITS-V2).

- `gptsovits-runtime` поднимает upstream `api_v2.py`
- `gptsovits-gateway` принимает upload референсов, хранит их в volume и проксирует synth-запросы
- `gptsovits-frontend` отдаёт отдельную страницу на `7070`

Подпроект живёт в своей папке и не использует `Makefile`, `compose`, `services` или `shared` из основного `fish-speech` проекта.

Текущий demo-frontend и gateway намеренно ограничены языками `English` и `Chinese`, чтобы инференс-контур оставался компактным и предсказуемым для серверного one-command deploy.

## Требования

- Debian / Ubuntu с Docker
- Docker Compose v2
- NVIDIA Driver
- NVIDIA Container Toolkit
- GPU уровня `RTX 5090` или близко к нему

Runtime собран на `CUDA 12.8` и `PyTorch cu128`, чтобы не тащить старый `CUDA 11.x` профиль upstream-репозитория.

## One-Command Deploy

```bash
git clone <этот-репозиторий>
cd fish-speech-s2pro/gptsovits-v2-demo
cp .env.example .env
make deploy
```

После этого:

- frontend: `http://127.0.0.1:7070`
- gateway API: `http://127.0.0.1:7088`

Если заходите с другой машины, замените `127.0.0.1` на IP сервера.

## Что происходит на первом старте

`gptsovits-runtime` автоматически:

1. Клонирует upstream `TZFC/GPT-SoVITS-V2` на этапе сборки image.
2. При первом старте скачивает обязательные `v2` веса из [lj1995/GPT-SoVITS](https://huggingface.co/lj1995/GPT-SoVITS).
3. Создаёт `tts_infer.yaml` под GPU runtime.

`gptsovits-gateway` дополнительно создаёт встроенный demo-референс через `espeak-ng`, чтобы UI был рабочим сразу после деплоя даже без ручной загрузки своего голоса.

Важно:

- первая загрузка обычно самая долгая
- первый прогрев runtime может занимать 10-20 минут, поэтому `gptsovits-gateway` и `gptsovits-frontend` какое-то время могут висеть в `Waiting`
- веса и кэши сохраняются в `data`
- референсы сохраняются в `references`
- все compose-тома и служебные файлы остаются внутри этой папки

## Команды

```bash
make build
make up
make down
make logs
make health
make ps
make deploy
```

Логи runtime смотрятся так:

```bash
docker compose -f docker-compose.yml logs -f gptsovits-runtime
```

Важно: `gptsovits-runtime` — это имя сервиса в compose. `gptsovits-v2-runtime` — имя контейнера.

Если `make deploy` долго висит на `Waiting`, это обычно означает не падение, а ожидание `healthy`-статуса runtime. Самые полезные команды диагностики:

```bash
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs -f gptsovits-runtime
docker inspect --format='{{json .State.Health}}' gptsovits-v2-runtime
```

Пока в логах появляются строки `gptsovits-bootstrap` или идёт загрузка весов, процесс живой. Настоящая проблема обычно проявляется как traceback или полностью остановившиеся логи на 10+ минут.

Самая удобная команда:

```bash
make deploy
```

Она:

- валидирует compose
- собирает image
- поднимает все сервисы
- ждёт готовности gateway и frontend
- печатает адреса UI и API

## Что умеет страница

- использовать встроенный demo-голос сразу после старта
- загружать свой reference-аудио и transcript
- хранить reference-ы на диске
- запускать synthesis и сразу прослушивать результат в браузере

Для лучших результатов загружайте чистый голос 5-10 секунд с точной расшифровкой.

## Переменные окружения

Новые переменные уже добавлены в `.env.example`:

- `GPTSOVITS_FRONTEND_PORT=7070`
- `GPTSOVITS_GATEWAY_PORT=7088`
- `GPTSOVITS_API_PORT=9880`
- `GPTSOVITS_SHM_SIZE=16g`
- `GPTSOVITS_RUNTIME_HEALTH_START_PERIOD=1200s`
- `GPTSOVITS_DEVICE=cuda`
- `GPTSOVITS_HALF=false`
- `GPTSOVITS_MODEL_REPO=lj1995/GPT-SoVITS`
- `GPTSOVITS_UPSTREAM_REPO=https://github.com/TZFC/GPT-SoVITS-V2.git`
- `GPTSOVITS_UPSTREAM_REF=main`

Для `RTX 5090` и других современных GPU в этом demo по умолчанию отключён `half`-режим. Это немного тяжелее по памяти, но заметно снижает вероятность runtime-ошибок инференса в `api_v2.py` на новых CUDA / PyTorch стеках. Если захотите максимум скорости и убедитесь, что всё стабильно, можно вернуть `GPTSOVITS_HALF=true`.

## Источники

- upstream runtime: [TZFC/GPT-SoVITS-V2](https://github.com/TZFC/GPT-SoVITS-V2)
- pretrained weights: [lj1995/GPT-SoVITS](https://huggingface.co/lj1995/GPT-SoVITS)
