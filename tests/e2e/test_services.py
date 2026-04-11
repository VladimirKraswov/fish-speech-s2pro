from __future__ import annotations

import json
import os
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HOST = os.getenv("E2E_HOST", "127.0.0.1")
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "60"))
REQUIRE_READY = os.getenv("E2E_REQUIRE_READY", "1") != "0"
RUN_TTS = os.getenv("E2E_TTS", "0") == "1"


def _url(name: str, port: str) -> str:
    return os.getenv(f"E2E_{name.upper()}_URL", f"http://{HOST}:{os.getenv(f'{name.upper()}_PORT', port)}").rstrip("/")


URLS = {
    "frontend": _url("frontend", "7070"),
    "gateway": _url("gateway", "7777"),
    "render": _url("render", "7778"),
    "live": _url("live", "7779"),
    "preprocess": _url("preprocess", "7780"),
    "finetune": _url("finetune", "7781"),
}


class E2EError(AssertionError):
    pass


def request(method: str, url: str, *, body: dict | None = None, headers: dict | None = None, timeout: float = TIMEOUT) -> tuple[int, dict, bytes]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    merged_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        merged_headers["Content-Type"] = "application/json"
    req = Request(url, data=payload, headers=merged_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise E2EError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise E2EError(f"{method} {url} failed: {exc}") from exc


def expect_http_error(method: str, url: str, *, body: dict | None = None, code: int, timeout: float = TIMEOUT) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout):
            raise E2EError(f"{method} {url} unexpectedly succeeded")
    except HTTPError as exc:
        raw = exc.read()
        if exc.code != code:
            raise E2EError(f"{method} {url} returned HTTP {exc.code}, expected {code}: {raw[:200]!r}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as err:
            raise E2EError(f"{method} {url} did not return JSON error payload: {raw[:200]!r}") from err
    except URLError as exc:
        raise E2EError(f"{method} {url} failed: {exc}") from exc


def json_request(method: str, url: str, *, body: dict | None = None, timeout: float = TIMEOUT) -> dict:
    status, _, raw = request(method, url, body=body, timeout=timeout)
    if status < 200 or status >= 300:
        raise E2EError(f"{method} {url} returned HTTP {status}")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise E2EError(f"{method} {url} did not return JSON: {raw[:200]!r}") from exc


def assert_keys(test: unittest.TestCase, data: dict, keys: set[str]) -> None:
    missing = keys - set(data)
    test.assertFalse(missing, f"Missing keys {sorted(missing)} in {data}")


def assert_ready(test: unittest.TestCase, data: dict, service: str) -> None:
    test.assertEqual(data.get("status"), "ok", f"{service} health status must be ok: {data}")
    if REQUIRE_READY and "ready" in data:
        test.assertTrue(data["ready"], f"{service} must be ready when E2E_REQUIRE_READY=1: {data}")


def assert_wav(test: unittest.TestCase, raw: bytes, service: str) -> None:
    test.assertGreater(len(raw), 44, f"{service} returned too few audio bytes")
    test.assertEqual(raw[:4], b"RIFF", f"{service} did not return WAV/RIFF bytes")
    test.assertEqual(raw[8:12], b"WAVE", f"{service} did not return WAVE bytes")


class FrontendE2ETest(unittest.TestCase):
    def test_frontend_serves_ui(self):
        status, headers, raw = request("GET", f"{URLS['frontend']}/", headers={"Accept": "text/html"})
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertGreater(len(raw), 100)


class PreprocessE2ETest(unittest.TestCase):
    def test_health_and_preprocess_contract(self):
        health = json_request("GET", f"{URLS['preprocess']}/healthz")
        assert_ready(self, health, "text-preprocess")

        data = json_request("POST", f"{URLS['preprocess']}/internal/preprocess", body={"text": "Привет ,  мир!  "})
        assert_keys(self, data, {"original", "processed", "changed"})
        self.assertEqual(data["processed"], "Привет, мир!")
        self.assertTrue(data["changed"])


class FineTuneE2ETest(unittest.TestCase):
    def test_health_defaults_status_and_validation_contracts(self):
        health = json_request("GET", f"{URLS['finetune']}/healthz")
        assert_ready(self, health, "finetune")

        defaults = json_request("GET", f"{URLS['finetune']}/internal/finetune")
        assert_keys(self, defaults, {"defaults", "presets", "datasets"})
        self.assertIn("project_name", defaults["defaults"])
        self.assertIn("lora_configs", defaults["presets"])
        self.assertIsInstance(defaults["datasets"], list)

        status = json_request("GET", f"{URLS['finetune']}/internal/finetune/status")
        assert_keys(self, status, {"state", "log_tail", "job"})

        validation = json_request(
            "POST",
            f"{URLS['finetune']}/internal/finetune/validate",
            body={"train_data_dir": "/definitely/missing/e2e-dataset"},
        )
        assert_keys(self, validation, {"config", "valid", "pairs", "errors", "issues", "warnings"})
        self.assertFalse(validation["valid"])
        self.assertGreaterEqual(len(validation["errors"]), 1)


class RenderE2ETest(unittest.TestCase):
    def test_health_and_status_contract(self):
        health = json_request("GET", f"{URLS['render']}/healthz", timeout=TIMEOUT)
        assert_keys(self, health, {"status", "ready", "engine", "detail"})
        assert_ready(self, health, "tts-render")

        status = json_request("GET", f"{URLS['render']}/internal/status")
        assert_keys(self, status, {"active_model_path", "ready", "engine", "compile_enabled", "dtype", "detail"})
        self.assertEqual(status["engine"], "fish")
        if REQUIRE_READY:
            self.assertTrue(status["ready"])

    def test_render_rejects_empty_text(self):
        data = expect_http_error("POST", f"{URLS['render']}/internal/synthesize", body={"text": ""}, code=400)
        self.assertIn("detail", data)

    def test_render_activate_requires_path(self):
        data = expect_http_error("POST", f"{URLS['render']}/internal/activate", body={"path": ""}, code=400)
        self.assertIn("detail", data)

    @unittest.skipUnless(RUN_TTS, "Set E2E_TTS=1 to run heavy render synthesis")
    def test_render_synthesis_returns_wav(self):
        _, headers, raw = request(
            "POST",
            f"{URLS['render']}/internal/synthesize",
            body={"text": "Hello world."},
            timeout=float(os.getenv("E2E_TTS_TIMEOUT", "900")),
        )
        self.assertIn("audio/wav", headers.get("Content-Type", ""))
        assert_wav(self, raw, "tts-render")


class LiveE2ETest(unittest.TestCase):
    def test_health_and_status_contract(self):
        health = json_request("GET", f"{URLS['live']}/healthz", timeout=TIMEOUT)
        assert_keys(self, health, {"status", "ready", "engine"})
        assert_ready(self, health, "tts-live")
        self.assertEqual(health["engine"], "s2cpp")

        status = json_request("GET", f"{URLS['live']}/internal/status")
        assert_keys(self, status, {"active_model_path", "ready", "engine", "detail"})
        self.assertEqual(status["engine"], "s2cpp")
        if REQUIRE_READY:
            self.assertTrue(status["ready"], status)

    def test_live_rejects_empty_text(self):
        data = expect_http_error("POST", f"{URLS['live']}/internal/synthesize", body={"text": ""}, code=400)
        self.assertIn("detail", data)

    def test_live_activate_requires_path(self):
        data = expect_http_error("POST", f"{URLS['live']}/internal/activate", body={"path": ""}, code=400)
        self.assertIn("detail", data)

    def test_live_stream_rejects_reference_conditioning(self):
        params = urlencode({"text": "Hello world.", "reference_id": "ref1"})
        data = expect_http_error("GET", f"{URLS['live']}/internal/stream/live?{params}", code=409)
        self.assertIn("detail", data)

    @unittest.skipUnless(RUN_TTS, "Set E2E_TTS=1 to run live synthesis")
    def test_live_synthesis_returns_wav(self):
        _, headers, raw = request(
            "POST",
            f"{URLS['live']}/internal/synthesize",
            body={"text": "Hello world."},
            timeout=float(os.getenv("E2E_TTS_TIMEOUT", "900")),
        )
        self.assertIn("audio/wav", headers.get("Content-Type", ""))
        assert_wav(self, raw, "tts-live")

    @unittest.skipUnless(RUN_TTS, "Set E2E_TTS=1 to run live streaming")
    def test_live_stream_returns_wav(self):
        params = urlencode({"text": "Hello world."})
        status, headers, raw = request("GET", f"{URLS['live']}/internal/stream/live?{params}", timeout=float(os.getenv("E2E_TTS_TIMEOUT", "900")))
        self.assertEqual(status, 200)
        self.assertIn("audio/wav", headers.get("Content-Type", ""))
        assert_wav(self, raw, "tts-live stream")


class GatewayE2ETest(unittest.TestCase):
    def test_health_and_proxy_contracts(self):
        health = json_request("GET", f"{URLS['gateway']}/healthz", timeout=TIMEOUT)
        assert_keys(self, health, {"status", "ready", "services"})
        assert_ready(self, health, "api-gateway")
        self.assertEqual(set(health["services"]), {"render", "live", "preprocess", "finetune"})

        datasets = json_request("GET", f"{URLS['gateway']}/api/datasets")
        self.assertIn("datasets", datasets)

        references = json_request("GET", f"{URLS['gateway']}/api/references")
        self.assertIn("references", references)

        jobs = json_request("GET", f"{URLS['gateway']}/api/jobs")
        self.assertIn("jobs", jobs)

        models = json_request("GET", f"{URLS['gateway']}/api/models")
        assert_keys(self, models, {"render", "live", "models", "render_runtime", "live_runtime"})

        preprocessed = json_request("POST", f"{URLS['gateway']}/api/text/preprocess", body={"text": "A  , B"})
        self.assertEqual(preprocessed["processed"], "A, B")

    def test_gateway_preserves_validation_errors(self):
        data = expect_http_error("POST", f"{URLS['gateway']}/api/synthesis", body={"text": ""}, code=400)
        self.assertIn("detail", data)

    def test_gateway_dataset_lifecycle(self):
        name = f"e2e_{int(time.time())}"
        created = json_request("POST", f"{URLS['gateway']}/api/datasets", body={"name": name})
        self.assertEqual(created["name"], name)
        fetched = json_request("GET", f"{URLS['gateway']}/api/datasets/{name}")
        self.assertEqual(fetched["name"], name)
        deleted = json_request("DELETE", f"{URLS['gateway']}/api/datasets/{name}")
        self.assertTrue(deleted["deleted"])

    @unittest.skipUnless(RUN_TTS, "Set E2E_TTS=1 to run gateway benchmark")
    def test_gateway_live_benchmark_contract(self):
        data = json_request(
            "POST",
            f"{URLS['gateway']}/api/synthesis/benchmark",
            body={"target": "live", "text": "Hello world."},
            timeout=float(os.getenv("E2E_TTS_TIMEOUT", "900")),
        )
        assert_keys(self, data, {"target", "engine", "model_path", "elapsed_sec", "audio_sec", "rtf", "bytes"})
        self.assertEqual(data["target"], "live")
        self.assertGreater(data["bytes"], 44)


if __name__ == "__main__":
    unittest.main(verbosity=2)
