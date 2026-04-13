import io
import wave

import numpy as np
import soundfile as sf


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


def audio_array_to_wav(audio, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def concatenate_audio_segments(segments: list, sample_rate: int, silence_ms: int = 0):
    if not segments:
        raise ValueError("Audio segment list must not be empty")

    arrays = [np.asarray(segment) for segment in segments]
    if len(arrays) == 1:
        return arrays[0]

    silence_samples = max(int(sample_rate * max(silence_ms, 0) / 1000), 0)
    if silence_samples <= 0:
        return np.concatenate(arrays, axis=0)

    first = arrays[0]
    silence_shape = (silence_samples,) if first.ndim == 1 else (silence_samples, first.shape[1])
    silence = np.zeros(silence_shape, dtype=first.dtype)

    stitched: list[np.ndarray] = []
    for index, array in enumerate(arrays):
        if index:
            stitched.append(silence)
        stitched.append(array)
    return np.concatenate(stitched, axis=0)
