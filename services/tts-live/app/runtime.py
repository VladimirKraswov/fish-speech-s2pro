import asyncio
import http.client
import os
import secrets
import shlex
import socket
import subprocess
import tempfile
import time
from pathlib import Path


class S2CppRuntime:
    def __init__(self, settings, model_path: str | None = None) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._model_path = model_path or str(settings.live_model_path)
        self._proc: subprocess.Popen | None = None
        self._error = ""
        self._host = "127.0.0.1"
        self._port = 31415
        self._log_path = Path(tempfile.gettempdir()) / "fish-speech-s2cpp.log"

    async def startup(self) -> None:
        async with self._lock:
            self._error = ""
            try:
                self._ensure_files()
                await asyncio.to_thread(self._restart_server)
            except Exception as exc:
                self._error = str(exc)

    async def shutdown(self) -> None:
        async with self._lock:
            self._stop_server()
            self._error = ""

    async def switch_model(self, model_path: str) -> dict:
        async with self._lock:
            target = str(model_path or "").strip()
            if not target:
                raise ValueError("Model path is required.")
            previous = self._model_path
            self._error = ""
            self._model_path = target
            try:
                self._ensure_files()
                await asyncio.to_thread(self._restart_server)
            except Exception as exc:
                self._error = str(exc)
                self._model_path = previous
                if previous != target and Path(previous).is_file():
                    try:
                        await asyncio.to_thread(self._restart_server)
                        self._error = ""
                    except Exception as restore_exc:
                        self._error = str(restore_exc)
                raise RuntimeError(self._error)
        return self.status()

    def status(self) -> dict:
        return {
            "active_model_path": self._model_path,
            "ready": self._files_ready() and self._server_ready(),
            "engine": "s2cpp",
            "detail": self._error,
        }

    def synthesize(self, text: str) -> bytes:
        if not str(text or "").strip():
            raise ValueError("Text must not be empty.")
        self._ensure_files()
        if not self._server_ready():
            self._restart_server()
        body, boundary = _multipart({"text": text})
        conn = http.client.HTTPConnection(self._host, self._port, timeout=600)
        conn.request(
            "POST",
            "/generate",
            body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        resp = conn.getresponse()
        audio = resp.read()
        conn.close()
        if resp.status != 200:
            raise RuntimeError(audio.decode("utf-8", errors="replace").strip() or resp.reason)
        return audio

    def _restart_server(self) -> None:
        self._stop_server()
        env = os.environ.copy()
        lib_dir = str(self.settings.s2cpp_bin.parent)
        env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
        argv = [
            str(self.settings.s2cpp_bin),
            "-m",
            self._model_path,
            "-t",
            str(self.settings.s2cpp_tokenizer_path),
            "-c",
            "0",
            "--server",
            "--host",
            self._host,
            "--port",
            str(self._port),
            *shlex.split(self.settings.s2cpp_extra_args),
        ]
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path.write_text("", encoding="utf-8")
        log_handle = self._log_path.open("a", encoding="utf-8")
        try:
            self._proc = subprocess.Popen(argv, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True)
        finally:
            log_handle.close()
        if not _wait_port(self._host, self._port, 120):
            detail = self._tail_log() or "s2.cpp server did not start."
            self._stop_server()
            self._error = detail
            raise RuntimeError(detail)

    def _stop_server(self) -> None:
        if not self._proc:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
        self._proc = None

    def _server_ready(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and _port_open(self._host, self._port)

    def _files_ready(self) -> bool:
        return (
            self.settings.s2cpp_bin.is_file()
            and self.settings.s2cpp_tokenizer_path.is_file()
            and Path(self._model_path).is_file()
        )

    def _ensure_files(self) -> None:
        if not self._files_ready():
            raise RuntimeError("s2.cpp binary, tokenizer.json or GGUF model is missing.")

    def _tail_log(self) -> str:
        if not self._log_path.exists():
            return ""
        rows = [line.strip() for line in self._log_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        return rows[-1] if rows else ""


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _wait_port(host: str, port: int, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.25)
    return False


def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----s2cpp-{secrets.token_hex(8)}"
    lines = []
    for key, value in fields.items():
        lines.extend([f"--{boundary}", f'Content-Disposition: form-data; name="{key}"', "", value])
    lines.extend([f"--{boundary}--", ""])
    return "\r\n".join(lines).encode("utf-8"), boundary
