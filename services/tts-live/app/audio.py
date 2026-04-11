import io
import struct
import wave


def wav_meta(chunk: bytes) -> tuple[int, int, int] | None:
    if len(chunk) < 44 or chunk[:4] != b"RIFF" or chunk[8:12] != b"WAVE":
        return None
    return (int.from_bytes(chunk[22:24], "little"), int.from_bytes(chunk[24:28], "little"), int.from_bytes(chunk[34:36], "little"))


def pcm_payload(chunk: bytes) -> bytes:
    return chunk[44:] if wav_meta(chunk) else chunk


def wav_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.getnframes() / (wav.getframerate() or 1)
    except wave.Error:
        channels, rate, bits, payload = wav_info(data)
        frame_size = channels * max(bits // 8, 1)
        return len(payload) / frame_size / (rate or 1)


def wav_info(data: bytes) -> tuple[int, int, int, bytes]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise wave.Error("invalid wav header")
    pos, channels, rate, bits, payload = 12, 1, 44100, 16, b""
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        body = data[pos + 8:pos + 8 + size]
        if chunk_id == b"fmt " and len(body) >= 16:
            channels = int.from_bytes(body[2:4], "little")
            rate = int.from_bytes(body[4:8], "little")
            bits = int.from_bytes(body[14:16], "little")
        elif chunk_id == b"data":
            payload = body
            break
        pos += 8 + size + (size % 2)
    return channels, rate, bits, payload
