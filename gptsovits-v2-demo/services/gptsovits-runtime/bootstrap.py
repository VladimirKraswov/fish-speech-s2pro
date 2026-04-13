from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml
from huggingface_hub import snapshot_download


APP_ROOT = Path("/opt/GPT-SoVITS-V2")
REPO_ROOT = APP_ROOT / "GPT_SoVITS"
DATA_ROOT = Path("/app/data")
PRETRAINED_DATA_ROOT = DATA_ROOT / "pretrained_models"
PRETRAINED_LINK = REPO_ROOT / "pretrained_models"
G2PW_DATA_ROOT = DATA_ROOT / "G2PWModel"
G2PW_LINK = REPO_ROOT / "text" / "G2PWModel"
CONFIG_PATH = DATA_ROOT / "tts_infer.yaml"


def log(message: str) -> None:
    print(f"[gptsovits-bootstrap] {message}", flush=True)


def bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def ensure_directory_link(link_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink():
        if link_path.resolve() == target_path.resolve():
            return
        link_path.unlink()
    elif link_path.exists():
        if link_path.is_dir():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target_path, target_is_directory=True)


def download_required_models() -> None:
    PRETRAINED_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    allow_patterns = [
        "gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
        "gsv-v2final-pretrained/s2G2333k.pth",
        "chinese-hubert-base/*",
        "chinese-roberta-wwm-ext-large/*",
    ]
    repo_id = os.getenv("GPTSOVITS_MODEL_REPO", "lj1995/GPT-SoVITS")
    log(f"downloading required model assets from {repo_id}")
    snapshot_download(
        repo_id=repo_id,
        allow_patterns=allow_patterns,
        local_dir=str(PRETRAINED_DATA_ROOT),
        max_workers=int(os.getenv("GPTSOVITS_DOWNLOAD_CONCURRENCY", "8")),
    )
    log("required model assets are present")


def write_runtime_config() -> None:
    version = os.getenv("GPTSOVITS_VERSION", "v2").strip().lower()
    if version != "v2":
        version = "v2"

    repo_pretrained_root = PRETRAINED_LINK.resolve()
    config = {
        "custom": {
            "bert_base_path": str(repo_pretrained_root / "chinese-roberta-wwm-ext-large"),
            "cnhuhbert_base_path": str(repo_pretrained_root / "chinese-hubert-base"),
            "device": os.getenv("GPTSOVITS_DEVICE", "cuda"),
            "is_half": bool_env("GPTSOVITS_HALF", True),
            "t2s_weights_path": str(
                repo_pretrained_root / "gsv-v2final-pretrained" / "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"
            ),
            "version": version,
            "vits_weights_path": str(repo_pretrained_root / "gsv-v2final-pretrained" / "s2G2333k.pth"),
        },
        "version": version,
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    log(f"runtime config written to {CONFIG_PATH}")


def main() -> None:
    log("preparing cache directories")
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "hf-cache").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "torch-cache").mkdir(parents=True, exist_ok=True)
    log("linking pretrained model directories into upstream checkout")
    ensure_directory_link(PRETRAINED_LINK, PRETRAINED_DATA_ROOT)
    ensure_directory_link(G2PW_LINK, G2PW_DATA_ROOT)
    download_required_models()
    write_runtime_config()
    log("bootstrap complete")


if __name__ == "__main__":
    main()
