from pathlib import Path

from shared.filesystem import pair_stats


def validate_config(config: dict) -> dict:
    path = Path(config["train_data_dir"])
    dataset_exists = path.exists() and path.is_dir()
    pairs = pair_stats(path)["paired"] if dataset_exists else 0
    valid = dataset_exists and pairs > 0
    errors = [] if valid else ["Dataset directory is missing or does not contain valid audio/transcript pairs."]
    return {"valid": valid, "pairs": pairs, "errors": errors, "issues": errors, "warnings": []}
