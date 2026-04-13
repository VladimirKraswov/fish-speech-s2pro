const state = {
  status: null,
  audioUrl: null,
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload.detail || payload.message || JSON.stringify(payload);
    throw new Error(detail);
  }
  return payload;
}

function setStatus(status) {
  const chip = $("#status-chip");
  const copy = $("#status-copy");
  const ready = !!status?.ready;
  chip.textContent = ready ? "Runtime готов" : "Runtime поднимается";
  chip.classList.toggle("ready", ready);
  chip.classList.toggle("waiting", !ready);
  copy.textContent = ready
    ? `Модель ${status.model_id} готова. Device: ${status.device}.`
    : "На первом старте runtime скачивает модель и поднимает Silero API.";
  $("#runtime-meta").textContent = ready
    ? `${status.model_id} · ${status.language.toUpperCase()} · ${status.device}`
    : "Runtime не готов";
}

function setFeedback(message, kind = "info") {
  const node = $("#feedback");
  node.textContent = message;
  node.dataset.kind = kind;
}

function fillSelect(select, values, currentValue) {
  const html = values.map((value) => {
    const selected = String(value) === String(currentValue) ? " selected" : "";
    return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(value)}</option>`;
  }).join("");
  select.innerHTML = html;
}

function renderExamples(examples = []) {
  $("#example-list").innerHTML = examples.map((item) => `
    <button class="example-card" type="button" data-example-id="${escapeHtml(item.id)}">
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.text)}</span>
    </button>
  `).join("");
}

function renderNotes(notes = []) {
  $("#notes").innerHTML = notes.map((item) => `<p>${escapeHtml(item)}</p>`).join("");
}

function applyExample(exampleId) {
  const example = state.status?.examples?.find((item) => item.id === exampleId);
  if (!example) return;
  $("#speaker").value = example.speaker;
  $("#sample-rate").value = String(example.sample_rate);
  $("#put-accent").checked = !!example.put_accent;
  $("#put-yo").checked = !!example.put_yo;
  $("#use-ssml").checked = !!example.use_ssml;
  $("#text").value = example.text;
  setFeedback(`Загружен пресет «${example.title}».`, "success");
}

async function refreshStatus() {
  const status = await fetchJson("/api/status");
  state.status = status;
  setStatus(status);

  const speakerSelect = $("#speaker");
  const sampleRateSelect = $("#sample-rate");
  const currentSpeaker = speakerSelect.value || status.default_speaker;
  const currentSampleRate = sampleRateSelect.value || status.default_sample_rate;

  fillSelect(speakerSelect, status.speakers || [], currentSpeaker);
  fillSelect(sampleRateSelect, status.sample_rates || [], currentSampleRate);
  renderExamples(status.examples || []);
  renderNotes(status.notes || []);

  if (!$("#text").value.trim() && status.examples?.length) {
    applyExample(status.examples[0].id);
  }
}

async function handleSynthesis(event) {
  event.preventDefault();
  if (!state.status?.ready) {
    setFeedback("Runtime ещё не готов. Дождитесь окончания загрузки модели.", "error");
    return;
  }

  const button = $("#synth-button");
  button.disabled = true;
  button.textContent = "Генерирую…";
  setFeedback("Синтез запущен. Для длинного текста это может занять несколько секунд.", "info");

  try {
    const payload = {
      text: $("#text").value,
      speaker: $("#speaker").value,
      sample_rate: Number($("#sample-rate").value),
      put_accent: $("#put-accent").checked,
      put_yo: $("#put-yo").checked,
      use_ssml: $("#use-ssml").checked,
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

    const segments = response.headers.get("X-Silero-Segments");
    const duration = response.headers.get("X-Silero-Duration-Sec");
    setFeedback(`Аудио готово. Сегментов: ${segments || "1"}, длительность: ${duration || "n/a"} сек.`, "success");
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Сгенерировать аудио";
  }
}

function bindEvents() {
  $("#refresh-button").addEventListener("click", () => {
    refreshStatus().catch((error) => setFeedback(error.message, "error"));
  });
  $("#synth-form").addEventListener("submit", handleSynthesis);
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-example-id]");
    if (!button) return;
    applyExample(button.dataset.exampleId);
  });
}

async function boot() {
  bindEvents();
  try {
    await refreshStatus();
  } catch (error) {
    setStatus({ ready: false });
    setFeedback(error.message, "error");
  }
  window.setInterval(() => {
    refreshStatus().catch(() => {});
  }, 15000);
}

boot();
