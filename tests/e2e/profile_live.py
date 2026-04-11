from __future__ import annotations

import argparse
import io
import json
import sys
import time
import wave
from http.client import HTTPConnection
from urllib.parse import quote_plus, urlparse


def wav_seconds(data: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.getnframes() / (wav.getframerate() or 1)
    except wave.Error:
        return None


def stream_profile(url: str, read_size: int) -> tuple[dict, bytes]:
    parsed = urlparse(url)
    conn = HTTPConnection(parsed.hostname, parsed.port or 80, timeout=3600)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    started = time.perf_counter()
    conn.request("GET", path)
    response = conn.getresponse()
    headers = {k.lower(): v for k, v in response.getheaders()}
    if response.status >= 400:
        body = response.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {response.status}: {body}")

    first_byte = None
    chunks = 0
    total = 0
    payload = bytearray()
    while True:
        chunk = response.read(read_size)
        if not chunk:
            break
        if first_byte is None:
            first_byte = time.perf_counter()
        chunks += 1
        total += len(chunk)
        payload.extend(chunk)
    finished = time.perf_counter()
    conn.close()

    seconds = wav_seconds(payload)
    return {
        "url": url,
        "status": response.status,
        "content_type": headers.get("content-type", ""),
        "bytes": total,
        "chunks": chunks,
        "ttfb_ms": round(((first_byte or finished) - started) * 1000, 1),
        "elapsed_sec": round(finished - started, 3),
        "audio_sec": round(seconds, 3) if seconds else None,
        "rtf": round((finished - started) / seconds, 3) if seconds else None,
        "server": headers.get("server", ""),
    }, bytes(payload)


def build_url(args) -> str:
    if args.url:
        return args.url
    if args.target == "gateway":
        return f"http://{args.host}:{args.port}/api/synthesis/stream/live?text={quote_plus(args.text)}"
    return f"http://{args.host}:{args.port}/internal/stream/live?text={quote_plus(args.text)}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile live TTS stream latency and throughput.")
    parser.add_argument("--target", choices=("gateway", "live"), default="gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--url", help="Full URL override")
    parser.add_argument("--text", default="Привет, это проверка live streaming производительности.")
    parser.add_argument("--read-size", type=int, default=65536)
    parser.add_argument("--save", help="Optional output wav path")
    args = parser.parse_args()

    if args.port is None:
        args.port = 7777 if args.target == "gateway" else 7779

    url = build_url(args)
    data, audio = stream_profile(url, args.read_size)

    if args.save:
        with open(args.save, "wb") as handle:
            handle.write(audio)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
