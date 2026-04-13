const state = {
  status: null,
  selectedReference: null,
  audioUrl: null,
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value){
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function fetchJson(url, options = {}){
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload.detail || payload.message || JSON.stringify(payload);
    throw new Error(detail);
  }
  return payload;
}

function setStatus(message, ready){
  const chip = $("#status-chip");
  const copy = $("#status-copy");
  chip.textContent = message;
  chip.classList.toggle("ready", !!ready);
  chip.classList.toggle("waiting", !ready);
  copy.textContent = ready
    ? "Runtime готов. Можно сразу использовать встроенный demo-голос или загрузить собственный референс."
    : "Runtime ещё поднимается. На первом старте Docker скачивает веса и это может занять 5-15 минут.";
}

function setFeedback(message, kind = "info"){
  const node = $("#synth-feedback");
  node.textContent = message;
  node.dataset.kind = kind;
}

function currentReferenceData(){
  return state.status?.references?.find((item) => item.name === state.selectedReference) || null;
}

function selectReference(name, { syncPrompt = true } = {}){
  state.selectedReference = name;
  const reference = currentReferenceData();
  if (reference && syncPrompt) {
    $("#synth-prompt-text").value = reference.transcript || "";
    $("#synth-prompt-lang").value = reference.language || "en";
  }
  renderReferences();
  renderSelection();
}

function renderSelection(){
  const reference = currentReferenceData();
  $("#current-reference").textContent = reference
    ? `${reference.display_name || reference.name} · ${reference.language.toUpperCase()}`
    : "Референс не выбран";
}

function renderReferences(){
  const container = $("#reference-list");
  const references = state.status?.references || [];
  container.innerHTML = references.map((reference) => {
    const selected = reference.name === state.selectedReference;
    const badge = reference.kind === "builtin-demo" ? '<span class="badge">built-in</span>' : '<span class="badge badge-muted">upload</span>';
    const deleteButton = reference.kind === "builtin-demo"
      ? ""
      : `<button class="tiny danger" type="button" data-delete-reference="${escapeHtml(reference.name)}">Удалить</button>`;
    const duration = reference.reference_meta?.duration_sec ? `${reference.reference_meta.duration_sec}s` : "n/a";
    return `
      <article class="reference-card ${selected ? "selected" : ""}">
        <div class="reference-top">
          <div>
            <h3>${escapeHtml(reference.display_name || reference.name)}</h3>
            <p>${escapeHtml(reference.language.toUpperCase())} · ${escapeHtml(duration)}</p>
          </div>
          ${badge}
        </div>
        <p class="reference-transcript">${escapeHtml(reference.transcript || "Transcript not set")}</p>
        <audio controls preload="metadata" src="${escapeHtml(reference.audio_url || "")}"></audio>
        <div class="reference-actions">
          <button class="tiny" type="button" data-select-reference="${escapeHtml(reference.name)}">
            ${selected ? "Выбран" : "Выбрать"}
          </button>
          ${deleteButton}
        </div>
      </article>
    `;
  }).join("");
}

async function refreshStatus({ preserveSelection = true } = {}){
  const status = await fetchJson("/api/status");
  state.status = status;
  setStatus(status.ready ? "Runtime готов" : "Runtime поднимается", status.ready);

  const available = new Set((status.references || []).map((item) => item.name));
  if (!preserveSelection || !state.selectedReference || !available.has(state.selectedReference)) {
    state.selectedReference = status.default_reference;
  }
  if (!$("#synth-text").value.trim()) {
    $("#synth-text").value = status.default_target_text || "";
  }
  renderReferences();
  renderSelection();
  if (currentReferenceData()) {
    $("#synth-prompt-text").value ||= currentReferenceData().transcript || "";
    $("#synth-prompt-lang").value = currentReferenceData().language || "en";
  }
}

async function handleUpload(event){
  event.preventDefault();
  const button = $("#upload-button");
  const form = $("#upload-form");
  const formData = new FormData(form);
  button.disabled = true;
  button.textContent = "Загружаю…";
  try {
    const response = await fetch("/api/references", { method: "POST", body: formData });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || payload.message || "Upload failed");
    }
    const payload = await response.json();
    form.reset();
    await refreshStatus({ preserveSelection: false });
    selectReference(payload.name, { syncPrompt: true });
    setFeedback("Референс сохранён. Теперь можно запускать синтез.", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Сохранить референс";
  }
}

async function handleDelete(name){
  if (!window.confirm(`Удалить референс "${name}"?`)) return;
  try {
    await fetchJson(`/api/references/${encodeURIComponent(name)}`, { method: "DELETE" });
    await refreshStatus({ preserveSelection: false });
    setFeedback("Референс удалён.", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function handleSynthesis(event){
  event.preventDefault();
  if (!state.status?.ready) {
    setFeedback("Runtime ещё не готов. Дождитесь окончания первой загрузки.", "error");
    return;
  }
  const button = $("#synth-button");
  button.disabled = true;
  button.textContent = "Генерирую…";
  setFeedback("Запрос отправлен. Генерация может занять несколько секунд.", "info");

  try {
    const payload = {
      text: $("#synth-text").value,
      text_lang: $("#synth-text-lang").value,
      prompt_lang: $("#synth-prompt-lang").value,
      prompt_text: $("#synth-prompt-text").value,
      reference_id: state.selectedReference,
    };
    const response = await fetch("/api/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : await response.text();
      throw new Error(typeof payload === "string" ? payload : payload.detail || payload.message || "Synthesis failed");
    }

    const blob = await response.blob();
    if (state.audioUrl) {
      URL.revokeObjectURL(state.audioUrl);
    }
    state.audioUrl = URL.createObjectURL(blob);
    $("#audio-player").src = state.audioUrl;
    $("#download-link").href = state.audioUrl;
    $("#result-card").classList.remove("hidden");
    setFeedback("Аудио готово. Можно прослушать результат или скачать WAV.", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Сгенерировать аудио";
  }
}

function bindEvents(){
  $("#upload-form").addEventListener("submit", handleUpload);
  $("#synth-form").addEventListener("submit", handleSynthesis);
  $("#refresh-button").addEventListener("click", () => refreshStatus({ preserveSelection: true }).catch((error) => setFeedback(error.message, "error")));
  document.addEventListener("click", (event) => {
    const selectButton = event.target.closest("[data-select-reference]");
    if (selectButton) {
      selectReference(selectButton.dataset.selectReference, { syncPrompt: true });
      return;
    }
    const deleteButton = event.target.closest("[data-delete-reference]");
    if (deleteButton) {
      handleDelete(deleteButton.dataset.deleteReference);
    }
  });
}

async function boot(){
  bindEvents();
  try {
    await refreshStatus({ preserveSelection: false });
  } catch (error) {
    setStatus("Gateway недоступен", false);
    setFeedback(error.message, "error");
  }
  window.setInterval(() => {
    refreshStatus({ preserveSelection: true }).catch(() => {});
  }, 15000);
}

boot();
