import { json } from "../api.js";
import { state, setMessage } from "../state.js";
import { messageBlock, qs } from "../ui.js";

export async function loadFinetune(){
  const [defaults, status] = await Promise.all([json("/api/finetune"), json("/api/finetune/status")]);
  state.finetuneDefaults = defaults;
  state.finetuneStatus = status;
}

export function renderFinetune(){
  qs("hero-finetune").textContent = state.finetuneStatus?.state || "idle";
  const cfg = state.finetuneDefaults?.defaults || {};
  const datasets = state.datasets.map((item) => `<option value="${item.path}">${item.name}</option>`).join("");
  qs("tab-finetune").innerHTML = `
    <div class="section">
      <div class="panel stack">
        <h2>Fine-tune</h2>${messageBlock(state.messages.finetune)}
        <div class="grid two"><input id="ft-project" value="${cfg.project_name || "my_voice"}"><select id="ft-dataset">${datasets}</select></div>
        <div class="grid three"><input id="ft-output" value="${cfg.output_model_dir || ""}"><input id="ft-base" value="${cfg.base_model_path || ""}"><input id="ft-repo" value="${cfg.model_repo || ""}"></div>
        <div class="grid three"><input id="ft-vq" value="${cfg.vq_batch_size || 8}" type="number"><input id="ft-vqw" value="${cfg.vq_num_workers || 1}" type="number"><input id="ft-build" value="${cfg.build_dataset_workers || 4}" type="number"></div>
        <select id="ft-lora">${(state.finetuneDefaults?.presets?.lora_configs || []).map((item) => `<option ${item === cfg.lora_config ? "selected" : ""}>${item}</option>`).join("")}</select>
        <div class="actions"><button id="ft-validate" class="button secondary">Проверить</button><button id="ft-start" class="button primary">Запустить</button><button id="ft-stop" class="button danger">Остановить</button></div>
      </div>
      <div class="panel stack"><h2>Статус</h2><div class="message success">Состояние: ${state.finetuneStatus?.state || "idle"}</div>${validationBlock()}</div>
    </div>
  `;
  qs("ft-validate").onclick = validateFineTune;
  qs("ft-start").onclick = startFineTune;
  qs("ft-stop").onclick = async () => { await json("/api/finetune/stop", { method: "POST" }); await bootFinetune(); };
}

function payload(){
  return {
    project_name: qs("ft-project").value.trim(),
    train_data_dir: qs("ft-dataset").value,
    output_model_dir: qs("ft-output").value.trim(),
    base_model_path: qs("ft-base").value.trim(),
    model_repo: qs("ft-repo").value.trim(),
    vq_batch_size: Number(qs("ft-vq").value),
    vq_num_workers: Number(qs("ft-vqw").value),
    build_dataset_workers: Number(qs("ft-build").value),
    lora_config: qs("ft-lora").value,
  };
}

function validationBlock(){
  if (!state.validation) return "";
  return [...(state.validation.issues || []).map((item) => `<div class="message error">${item}</div>`), ...(state.validation.warnings || []).map((item) => `<div class="message warn">${item}</div>`)].join("");
}

async function validateFineTune(){
  state.validation = await json("/api/finetune/validate", { method: "POST", body: JSON.stringify(payload()) });
  renderFinetune();
}

async function startFineTune(){
  try { await json("/api/finetune/start", { method: "POST", body: JSON.stringify(payload()) }); setMessage("finetune", "success", "Fine-tune запущен."); }
  catch (error) { setMessage("finetune", "error", error.message); }
  await bootFinetune();
}

export async function bootFinetune(){ try { await loadFinetune(); } catch (error) { setMessage("finetune", "error", error.message); } renderFinetune(); }
