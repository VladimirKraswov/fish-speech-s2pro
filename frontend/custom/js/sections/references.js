import { form, json } from "../api.js";
import { state, setMessage } from "../state.js";
import { escapeHtml, labelWithHelp, messageBlock, optionRows, qs } from "../ui.js";

export async function loadReferences(){
  const data = await json("/api/references");
  state.references = data.references || [];
  if (!state.references.some((item) => item.name === state.activeReference)) state.activeReference = "";
}

function activeReferenceRecord(){
  return state.references.find((item) => item.name === state.activeReference) || null;
}

function transcriptValidation(record){
  return record?.reference_meta?.transcript_validation || null;
}

function referenceMetaSummary(record){
  const meta = record?.reference_meta || {};
  const duration = meta.duration_sec ? `${meta.duration_sec}s` : "duration ?";
  const sampleRate = meta.sample_rate ? `${meta.sample_rate} Hz` : "rate ?";
  const channels = meta.channels ? `${meta.channels} ch` : "channels ?";
  return `${duration} · ${sampleRate} · ${channels}`;
}

function transcriptStatusLabel(record){
  const validation = transcriptValidation(record);
  if (!validation) return "transcript unchecked";
  if (validation.valid) return `transcript ok · ${validation.chars} chars / ${validation.words} words`;
  return "transcript needs review";
}

function transcriptEditor(record){
  if (!record) {
    return `<div class="message warn">Выберите reference справа, чтобы проверить transcript и при необходимости исправить его.</div>`;
  }
  const validation = transcriptValidation(record);
  const validationKind = !validation ? "warn" : (validation.valid ? "success" : "error");
  const validationText = !validation
    ? "Проверка transcript пока недоступна."
    : validation.valid
      ? `Transcript выглядит адекватно для этого audio. ${validation.chars} chars / ${validation.words} words.`
      : validation.message;
  return `
    <div class="stack">
      <div class="row">
        <h3>Transcript для ${escapeHtml(record.name)}</h3>
        <span class="compact">${escapeHtml(referenceMetaSummary(record))}</span>
      </div>
      <div class="message ${validationKind}">${escapeHtml(validationText)}</div>
      <label class="field">
        <span>${labelWithHelp("Текст референса", "Здесь должен быть точный текст, который реально звучит в reference audio. Если transcript длиннее самого аудио, Fish Speech может начать читать его вместо целевого текста.")}</span>
        <textarea id="ref-edit-text" placeholder="Точный transcript reference audio">${escapeHtml(record.transcript || "")}</textarea>
      </label>
      <div class="actions">
        <button id="save-ref-text" class="button primary">Обновить transcript</button>
      </div>
    </div>
  `;
}

export function renderReferences(){
  qs("hero-reference").textContent = state.activeReference || "без референса";
  const selected = activeReferenceRecord();
  qs("tab-references").innerHTML = `
    <div class="grid two">
      <div class="panel stack">
        <h2>Новый референс</h2>${messageBlock(state.messages.references)}
        <input id="ref-name" placeholder="alina_ref"><input id="ref-audio" type="file" accept=".wav,.mp3,.flac">
        <textarea id="ref-text" placeholder="Текст для reference audio"></textarea>
        <div class="actions"><button id="save-ref" class="button primary">Сохранить</button></div>
      </div>
      <div class="panel stack">
        <div class="row"><h2>Список reference</h2><button id="clear-ref" class="button ghost">Без референса</button></div>
        <div id="ref-list" class="list">${optionRows(state.references, state.activeReference, (item) => [
          item.audio_file || "audio",
          transcriptStatusLabel(item),
          (item.transcript || "").slice(0, 60),
        ])}</div>
        ${transcriptEditor(selected)}
      </div>
    </div>
  `;
  qs("save-ref").onclick = saveReference;
  qs("clear-ref").onclick = () => { state.activeReference = ""; renderReferences(); window.dispatchEvent(new Event("studio:sync")); };
  qs("ref-list").onclick = async (event) => {
    const item = event.target.closest("[data-name]");
    if (!item) return;
    if (event.target.closest(".delete-ref")) await removeReference(item.dataset.name);
    else { state.activeReference = item.dataset.name; renderReferences(); window.dispatchEvent(new Event("studio:sync")); }
  };
  [...qs("ref-list").querySelectorAll(".item")].forEach((node) => {
    node.insertAdjacentHTML("beforeend", `<div class="actions"><button class="button danger delete-ref">Удалить</button></div>`);
  });
  const updateButton = qs("save-ref-text");
  if (updateButton) updateButton.onclick = updateReferenceTranscript;
}

async function saveReference(){
  const body = new FormData();
  body.append("name", qs("ref-name").value.trim());
  body.append("transcript", qs("ref-text").value);
  body.append("audio_file", qs("ref-audio").files[0]);
  try { await form("/api/references", body, { method: "POST" }); setMessage("references", "success", "Reference сохранён."); }
  catch (error) { setMessage("references", "error", error.message); }
  await bootReferences();
  window.dispatchEvent(new Event("studio:sync"));
}

async function removeReference(name){
  await json(`/api/references/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (state.activeReference === name) state.activeReference = "";
  await bootReferences();
  window.dispatchEvent(new Event("studio:sync"));
}

async function updateReferenceTranscript(){
  const current = activeReferenceRecord();
  if (!current) return;
  try {
    await json(`/api/references/${encodeURIComponent(current.name)}/transcript`, {
      method: "PUT",
      body: JSON.stringify({ transcript: qs("ref-edit-text").value }),
    });
    setMessage("references", "success", "Transcript reference обновлён.");
  } catch (error) {
    setMessage("references", "error", error.message);
  }
  await bootReferences();
  window.dispatchEvent(new Event("studio:sync"));
}

export async function bootReferences(){
  try { await loadReferences(); } catch (error) { setMessage("references", "error", error.message); }
  renderReferences();
}
