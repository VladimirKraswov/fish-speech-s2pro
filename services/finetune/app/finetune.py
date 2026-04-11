import asyncio
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .finetune_validation import validate_config


class FineTuneService:
    def __init__(self, settings, events, jobs, queue) -> None:
        self.settings, self.events, self.jobs, self.queue = settings, events, jobs, queue
        self.runner = Path("/app/fine_tune_runner.sh")
        self.log_path = settings.logs_root / "fine_tune.log"
        self.process: subprocess.Popen[str] | None = None
        self.active_job: str | None = None

    def defaults(self) -> dict:
        project = "my_voice"
        return {
            "project_name": project,
            "train_data_dir": str(self.settings.training_root),
            "output_model_dir": str(self.settings.finetuned_root / project),
            "base_model_path": str(self.settings.model_path),
            "vq_batch_size": 8,
            "vq_num_workers": 2,
            "build_dataset_workers": 8,
            "lora_config": "r_8_alpha_16",
            "model_repo": self.settings.model_repo,
            "hf_endpoint": self.settings.hf_endpoint,
        }

    def validate(self, payload: dict) -> dict:
        config = {**self.defaults(), **payload}
        return {"config": config, **validate_config(config)}

    def start(self, payload: dict) -> dict:
        check = self.validate(payload)
        if not check["valid"]:
            raise ValueError("; ".join(check.get("errors") or ["Dataset validation failed."]))
        job = self.jobs.create("finetune", {"project": check["config"]["project_name"], "config": check["config"]})
        self.queue.submit(job["id"], lambda: self._run(job["id"], check["config"]), self._cancel_active)
        return job

    def stop(self, job_id: str | None = None) -> dict:
        target = job_id or self.active_job or self._latest_pending()
        if not target:
            raise RuntimeError("No queued or running fine-tune job.")
        return self.queue.cancel(target)

    def status(self) -> dict:
        log = self._log()
        job = self._latest()
        state = job["status"] if job else "idle"
        config = job["payload"].get("config") if job else None
        result = job.get("result") if job else {}
        return {"state": state, "config": config, "started_at": result.get("started_at"), "finished_at": result.get("finished_at"), "steps": self._steps(log, state), "log_tail": log[-12000:], "job": job}

    async def _run(self, job_id: str, config: dict) -> None:
        self.active_job = job_id
        self.log_path.write_text("", encoding="utf-8")
        self.jobs.update(job_id, "running", {"started_at": self._now()})
        env = self._env(config)
        with self.log_path.open("a", encoding="utf-8") as log:
            self.process = subprocess.Popen(["/bin/bash", str(self.runner)], cwd="/app/fish-speech", env=env, stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        while self.process and self.process.poll() is None:
            await asyncio.sleep(1)
        log = self._log()
        status = self.jobs.get(job_id)["status"]
        if status != "cancelled":
            status = "completed" if self.process and self.process.returncode == 0 else "failed"
            error = None if status == "completed" else self._last_error(log)
            self.jobs.update(job_id, status, {"started_at": self.jobs.get(job_id)["result"]["started_at"], "finished_at": self._now()}, error)
        self.process, self.active_job = None, None

    def _cancel_active(self) -> None:
        if self.process and self.process.poll() is None:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

    def _env(self, config: dict) -> dict:
        env = os.environ.copy()
        env.update({"PROJECT_NAME": config["project_name"], "TRAIN_DATA_DIR": config["train_data_dir"], "OUTPUT_MODEL_DIR": config["output_model_dir"], "BASE_MODEL_PATH": config["base_model_path"], "MODEL_REPO": config["model_repo"], "VQ_BATCH_SIZE": str(config["vq_batch_size"]), "VQ_NUM_WORKERS": str(config["vq_num_workers"]), "BUILD_DATASET_WORKERS": str(config["build_dataset_workers"]), "LORA_CONFIG": str(config["lora_config"])})
        if config.get("hf_endpoint"):
            env["HF_ENDPOINT"] = str(config["hf_endpoint"])
        return env

    def _latest(self) -> dict | None:
        return next((job for job in self.jobs.list() if job["kind"] == "finetune"), None)

    def _latest_pending(self) -> str | None:
        job = next((job for job in self.jobs.list() if job["kind"] == "finetune" and job["status"] in {"queued", "running"}), None)
        return job["id"] if job else None

    def _log(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace") if self.log_path.exists() else ""

    def _last_error(self, log: str) -> str | None:
        rows = [line.strip() for line in log.splitlines() if line.strip()]
        return rows[-1] if rows else None

    def _steps(self, log: str, state: str) -> list[dict]:
        labels = ["Step 1/4: extracting semantic tokens", "Step 2/4: building protobuf dataset", "Step 3/4: training LoRA", "Step 4/4: merging LoRA into regular weights"]
        active = max((i for i, label in enumerate(labels) if label in log), default=-1)
        if "Done. Merged model saved to:" in log:
            return [{"label": label, "state": "done"} for label in labels]
        return [{"label": label, "state": "failed" if state in {"failed", "cancelled"} and i == max(active, 0) else "pending" if active < 0 or i > active else "done" if i < active else "active"} for i, label in enumerate(labels)]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
