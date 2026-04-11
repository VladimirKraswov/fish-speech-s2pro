async function readJson(response){
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}

export async function json(url, options = {}){
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  return readJson(response);
}

export async function form(url, body, options = {}){
  const response = await fetch(url, { ...options, body });
  return readJson(response);
}

export async function audio(url, payload){
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Audio request failed");
  }
  const reader = response.body?.getReader();
  const chunks = [];
  let receivedBytes = 0;
  if (!reader) {
    return { url: URL.createObjectURL(await response.blob()), receivedBytes: 0 };
  }
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    receivedBytes += value.byteLength;
    window.dispatchEvent(new CustomEvent("studio:synthesis-progress", { detail: { receivedBytes } }));
  }
  const blob = new Blob(chunks, { type: response.headers.get("content-type") || "audio/wav" });
  return { url: URL.createObjectURL(blob), receivedBytes };
}
