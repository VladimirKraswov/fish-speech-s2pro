import { json } from "../api.js";
import { state, setMessage } from "../state.js";
import { escapeHtml, messageBlock, qs } from "../ui.js";

export async function loadModels(){
  const data = await json("/api/models");
  state.models = data.models || [];
  state.activeModel = data.render?.name || "base";
  state.liveModel = data.live?.name || "base";
  state.renderEngine = data.render_runtime?.engine || "fish";
  state.liveEngine = data.live_runtime?.engine || "fish";
}

function badges(name){
  const rows = [];
  if (name === state.activeModel) rows.push(`<span class="badge">synthesis</span>`);
  if (name === state.liveModel) rows.push(`<span class="badge alt">live</span>`);
  return rows.join("");
}

function modelCard(item){
  const liveLocked = state.liveEngine === "s2cpp" && item.engine !== "s2cpp";
  const renderLocked = item.engine !== "fish";
  return `
    <div class="item card model-card">
      <div class="row">
        <h3>${escapeHtml(item.name)}</h3>
        <div class="badge-row">${badges(item.name)}</div>
      </div>
      <div class="meta"><span>${escapeHtml(item.kind)}</span><span>${escapeHtml(item.engine)}</span><span>${escapeHtml(item.path)}</span></div>
      <div class="actions">
        <button class="button ghost" data-target="render" data-name="${escapeHtml(item.name)}" ${renderLocked ? "disabled" : ""}>Для synthesis</button>
        <button class="button secondary" data-target="live" data-name="${escapeHtml(item.name)}" ${liveLocked ? "disabled" : ""}>Для live</button>
      </div>
    </div>
  `;
}

export function renderModels(){
  qs("hero-model").textContent = `${state.activeModel || "base"} / ${state.liveModel || "base"}`;
  qs("tab-models").innerHTML = `
    <div class="section">
      <div class="panel">
        <div class="row"><h2>Models & LoRA</h2><button id="refresh-models" class="button ghost">Обновить</button></div>
        ${messageBlock(state.messages.models)}
        <div class="message success">Synthesis: ${state.activeModel || "base"} (${state.renderEngine}) · Live: ${state.liveModel || "base"} (${state.liveEngine})</div>
        <div id="models-list" class="list">${state.models.map(modelCard).join("")}</div>
      </div>
    </div>
  `;
  qs("refresh-models").onclick = bootModels;
  qs("models-list").onclick = async (event) => {
    const button = event.target.closest("button[data-name][data-target]");
    if (!button) return;
    await json("/api/models/activate", { method: "POST", body: JSON.stringify({ name: button.dataset.name, target: button.dataset.target }) });
    setMessage("models", "success", `Назначена модель ${button.dataset.name} для ${button.dataset.target}.`);
    await bootModels();
    window.dispatchEvent(new Event("studio:sync"));
  };
}

export async function bootModels(){
  try { await loadModels(); } catch (error) { setMessage("models", "error", error.message); }
  renderModels();
}
