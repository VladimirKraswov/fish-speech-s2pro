import { connectEvents } from "./events.js";
import { state } from "./state.js";
import { bindTabs } from "./ui.js";
import { bootDatasets } from "./sections/datasets.js";
import { bootFinetune } from "./sections/finetune.js";
import { bootLogs } from "./sections/logs.js";
import { bootModels } from "./sections/models.js";
import { bootReferences } from "./sections/references.js";
import { bootSynthesis } from "./sections/synthesis.js";

async function boot(){
  bindTabs(state);
  await bootModels();
  await bootReferences();
  await bootDatasets();
  await bootFinetune();
  await bootLogs();
  await bootSynthesis();
  window.addEventListener("studio:sync", async () => {
    await bootSynthesis();
    await bootFinetune();
  });
  connectEvents();
}

boot().catch((error) => {
  document.body.innerHTML = `<main class="page"><div class="message error">Не удалось загрузить интерфейс: ${error.message}</div></main>`;
});
