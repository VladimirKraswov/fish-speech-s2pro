import { form, json } from "../api.js";
import { state, setMessage } from "../state.js";
import { messageBlock, optionRows, qs } from "../ui.js";

export async function loadReferences(){
  const data = await json("/api/references");
  state.references = data.references || [];
  if (!state.references.some((item) => item.name === state.activeReference)) state.activeReference = "";
}

export function renderReferences(){
  qs("hero-reference").textContent = state.activeReference || "без референса";
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
        <div id="ref-list" class="list">${optionRows(state.references, state.activeReference, (item) => [item.audio_file || "audio", item.transcript.slice(0, 60)])}</div>
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

export async function bootReferences(){
  try { await loadReferences(); } catch (error) { setMessage("references", "error", error.message); }
  renderReferences();
}
