import re

from fastapi import FastAPI


def preprocess(text: str) -> dict:
    raw = str(text or "")
    cleaned = raw.replace("\r\n", "\n").replace("—", "-").replace("ё", "е")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,.;:!?])([^\s])", r"\1 \2", cleaned)
    cleaned = cleaned.strip()
    return {"original": raw, "processed": cleaned, "changed": raw != cleaned}


app = FastAPI(title="text-preprocess", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/internal/preprocess")
async def preprocess_route(payload: dict):
    return preprocess(payload.get("text", ""))
