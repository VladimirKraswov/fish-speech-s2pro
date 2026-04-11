import httpx


async def json_request(method: str, url: str, **kwargs):
    timeout = kwargs.pop("timeout", 3600)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Request to {url} failed: {exc}") from exc

    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}

    if response.status_code >= 400:
        raise RuntimeError(data.get("detail") or response.text or f"Upstream error from {url}: {response.status_code}")
    return data
