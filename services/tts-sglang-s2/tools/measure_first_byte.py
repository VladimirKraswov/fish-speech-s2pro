#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure first HTTP byte and first PCM byte for the SGLang S2 WAV stream.")
    parser.add_argument("--url", default="http://127.0.0.1:7782/internal/stream")
    parser.add_argument("--text", default="Привет, это короткая проверка задержки первого байта.")
    parser.add_argument("--reference-id", default=None)
    parser.add_argument("--deadline-ms", type=float, default=200.0)
    parser.add_argument("--audio-deadline-ms", type=float, default=None)
    parser.add_argument("--header-bytes", type=int, default=44)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    payload = {"text": args.text}
    if args.reference_id:
        payload["reference_id"] = args.reference_id

    first_byte_ms = None
    first_audio_ms = None
    received = 0
    started = time.perf_counter()

    with httpx.stream("POST", args.url, json=payload, timeout=args.timeout) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            now_ms = (time.perf_counter() - started) * 1000
            if first_byte_ms is None:
                first_byte_ms = now_ms
            received += len(chunk)
            if first_audio_ms is None and received > args.header_bytes:
                first_audio_ms = now_ms
                break

    result = {
        "url": args.url,
        "first_byte_ms": round(first_byte_ms or 0, 2),
        "first_audio_byte_ms": round(first_audio_ms or 0, 2),
        "target_first_byte_ms": args.deadline_ms,
        "target_first_audio_byte_ms": args.audio_deadline_ms,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failed = False
    if first_byte_ms is None or first_byte_ms > args.deadline_ms:
        failed = True
    if args.audio_deadline_ms is not None and (first_audio_ms is None or first_audio_ms > args.audio_deadline_ms):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
