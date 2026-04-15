# SGLang S2 Low-TTFB Inference

Отдельный вариант инференса лежит в `services/tts-sglang-s2`. Он запускает upstream `sgl-omni serve` для FishAudio S2-Pro и поверх него даёт два режима:

- `POST /v1/audio/speech` — OpenAI-compatible proxy. При `stream: true` возвращает upstream SSE.
- `POST /internal/stream` — WAV stream для минимального HTTP time-to-first-byte. Сервис сразу отдаёт WAV header, а аудио добавляет PCM чанками из upstream SSE.

SGLang Omni в своём README заявляет около `140 ms` Time-to-First-Audio за счёт radix prefix caching; здесь целевой HTTP first byte выставлен в `200 ms`.

## Запуск

```bash
make sglang-s2-up
make sglang-s2-health
```

По умолчанию сервис доступен на `http://127.0.0.1:7782`.

Для первой сборки используется образ из upstream инструкции:

```bash
SGLANG_OMNI_IMAGE=frankleeeee/sglang-omni:dev make sglang-s2-build
```

Модель ожидается в контейнере по пути `/app/data/checkpoints/s2-pro`. Если нужно скачать из Hugging Face напрямую, можно переопределить:

```bash
SGLANG_S2_MODEL_PATH=fishaudio/s2-pro make sglang-s2-up
```

## Проверка первого байта

```bash
make sglang-s2-profile
```

Или напрямую:

```bash
python3 services/tts-sglang-s2/tools/measure_first_byte.py \
  --url http://127.0.0.1:${SGLANG_S2_PORT:-7782}/internal/stream \
  --deadline-ms 200
```

Скрипт выводит два значения:

- `first_byte_ms` — первый HTTP byte; при `SGLANG_S2_EARLY_WAV_HEADER=true` это WAV header.
- `first_audio_byte_ms` — первый PCM byte после WAV header.

## Примеры

WAV stream:

```bash
curl -N -o /tmp/s2-stream.wav \
  -H 'Content-Type: application/json' \
  -d '{"text":"Привет, это быстрый поток FishAudio S2 через SGLang Omni."}' \
  http://127.0.0.1:7782/internal/stream
```

OpenAI-compatible SSE:

```bash
curl -N \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from SGLang Omni S2.","stream":true}' \
  http://127.0.0.1:7782/v1/audio/speech
```

Saved reference из общей папки `references`:

```bash
curl -N -o /tmp/s2-ref.wav \
  -H 'Content-Type: application/json' \
  -d '{"text":"Тест клонирования голоса.", "reference_id":"my_voice"}' \
  http://127.0.0.1:7782/internal/stream
```

## Настройки задержки

Основные переменные:

- `SGLANG_S2_TARGET_FIRST_BYTE_MS=200`
- `SGLANG_S2_EARLY_WAV_HEADER=true`
- `SGLANG_S2_WARMUP=true`
- `SGLANG_S2_WARMUP_MAX_NEW_TOKENS=32`
- `SGLANG_S2_STREAM_SAMPLE_RATE=44100`
- `SGLANG_S2_EXTRA_ARGS=...`

В `config/s2pro_low_ttfb.yaml` первый streaming vocoder chunk настроен через `stream_stride: 5`; последующие чанки идут чаще, чем upstream default, через `stream_followup_stride: 25`.
