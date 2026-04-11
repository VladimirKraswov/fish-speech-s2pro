import { form, json } from "../api.js";
import { state, setMessage } from "../state.js";
import { escapeHtml, messageBlock, optionRows, qs } from "../ui.js";

export async function loadDatasets(){
  const data = await json("/api/datasets");
  state.datasets = data.datasets || [];
  if (state.dataset && !state.datasets.some((item) => item.name === state.dataset.name)) state.dataset = null;
  if (!state.dataset && state.datasets[0]) state.dataset = await json(`/api/datasets/${state.datasets[0].name}`);
}

export function renderDatasets(){
  const samples = (state.dataset?.samples || []).map((item) => `
    <div class="sample"><div class="row"><h3>${escapeHtml(item.stem)}</h3>
    <div class="actions"><button class="button secondary" data-save="${escapeHtml(item.stem)}">Сохранить .lab</button>
    <button class="button danger" data-drop="${escapeHtml(item.stem)}">Удалить</button></div></div>
    <div class="pillrow">${item.audio_files.map((name) => `<span class="badge">${escapeHtml(name)}</span>`).join("")}${item.has_lab ? `<span class="badge">lab</span>` : `<span class="badge bad">нет lab</span>`}</div>
    <textarea data-text="${escapeHtml(item.stem)}">${escapeHtml(item.transcript)}</textarea></div>`).join("");
  qs("tab-datasets").innerHTML = `
    <div class="grid two">
      <div class="panel stack">
        <h2>Datasets</h2>${messageBlock(state.messages.datasets)}
        <div class="actions"><input id="dataset-name" placeholder="speaker_alina"><button id="dataset-create" class="button primary">Создать</button></div>
        <div id="dataset-list" class="list">${optionRows(state.datasets, state.dataset?.name, (item) => [`${item.audio_files} audio`, `${item.matched_pairs} pairs`])}</div>
      </div>
      <div class="panel stack">
        <div class="row"><h2>${escapeHtml(state.dataset?.name || "Dataset manager")}</h2><button id="dataset-delete" class="button danger">Удалить dataset</button></div>
        ${state.dataset ? datasetBody(samples) : `<div class="message warn">Создайте или выберите датасет.</div>`}
      </div>
    </div>
  `;
  bindDatasetEvents();
}

function datasetBody(samples){
  return `<div class="summary"><div class="card"><span>Audio</span><strong>${state.dataset.audio_files}</strong></div><div class="card"><span>Pairs</span><strong>${state.dataset.matched_pairs}</strong></div><div class="card"><span>Lab</span><strong>${state.dataset.lab_files}</strong></div></div>
  <div class="grid two"><div class="stack"><input id="sample-name" placeholder="0001"><input id="sample-audio" type="file" accept=".wav,.mp3,.flac"><textarea id="sample-text" placeholder="Текст .lab"></textarea><button id="sample-save" class="button primary">Добавить sample</button></div>
  <div class="stack"><input id="bulk-files" type="file" accept=".wav,.mp3,.flac,.lab" multiple><button id="bulk-upload" class="button secondary">Bulk upload</button><div class="compact">${escapeHtml(state.dataset.path)}</div></div></div>
  <div class="stack"><h3>Samples</h3>${samples || `<div class="message warn">Сэмплов пока нет.</div>`}</div>`;
}

async function refreshDataset(name){
  state.dataset = await json(`/api/datasets/${encodeURIComponent(name)}`);
  await loadDatasets();
  window.dispatchEvent(new Event("studio:sync"));
}

async function bindSaveSample(){
  const body = new FormData();
  body.append("sample_name", qs("sample-name").value.trim() || qs("sample-audio").files[0]?.name || "");
  body.append("audio_file", qs("sample-audio").files[0]);
  body.append("transcript_text", qs("sample-text").value);
  await form(`/api/datasets/${state.dataset.name}/samples`, body, { method: "POST" });
  await refreshDataset(state.dataset.name);
}

function bindDatasetEvents(){
  qs("dataset-create").onclick = async () => { await json("/api/datasets", { method: "POST", body: JSON.stringify({ name: qs("dataset-name").value.trim() }) }); await loadDatasets(); renderDatasets(); };
  qs("dataset-list").onclick = async (event) => { const item = event.target.closest("[data-name]"); if (item) { await refreshDataset(item.dataset.name); renderDatasets(); } };
  if (!state.dataset) return;
  qs("dataset-delete").onclick = async () => { await json(`/api/datasets/${state.dataset.name}`, { method: "DELETE" }); await loadDatasets(); renderDatasets(); };
  qs("sample-save").onclick = async () => { try { await bindSaveSample(); } catch (error) { setMessage("datasets", "error", error.message); renderDatasets(); } };
  qs("bulk-upload").onclick = async () => { const body = new FormData(); [...qs("bulk-files").files].forEach((file) => body.append("files", file)); await form(`/api/datasets/${state.dataset.name}/files`, body, { method: "POST" }); await refreshDataset(state.dataset.name); renderDatasets(); };
  qs("tab-datasets").onclick = async (event) => { const save = event.target.closest("[data-save]"); const drop = event.target.closest("[data-drop]"); if (save) { const text = qs("tab-datasets").querySelector(`[data-text="${save.dataset.save}"]`).value; await json(`/api/datasets/${state.dataset.name}/samples/${save.dataset.save}`, { method: "PUT", body: JSON.stringify({ transcript: text }) }); await refreshDataset(state.dataset.name); renderDatasets(); } if (drop) { await json(`/api/datasets/${state.dataset.name}/samples/${drop.dataset.drop}`, { method: "DELETE" }); await refreshDataset(state.dataset.name); renderDatasets(); } };
}

export async function bootDatasets(){
  try { await loadDatasets(); } catch (error) { setMessage("datasets", "error", error.message); }
  renderDatasets();
  window.dispatchEvent(new Event("studio:sync"));
}
