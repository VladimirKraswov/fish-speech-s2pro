import { state } from "./state.js";
import { bootDatasets } from "./sections/datasets.js";
import { bootFinetune } from "./sections/finetune.js";
import { refreshLogs } from "./sections/logs.js";
import { bootModels } from "./sections/models.js";
import { bootReferences } from "./sections/references.js";
import { bootSynthesis } from "./sections/synthesis.js";

const tasks = new Map();

function schedule(key, fn){
  if (tasks.has(key)) return;
  tasks.set(key, window.setTimeout(async () => {
    tasks.delete(key);
    await fn();
  }, 120));
}

export function connectEvents(){
  const source = new EventSource("/api/events");
  source.addEventListener("hello", (event) => {
    const data = JSON.parse(event.data);
    state.eventHistory = data.history || [];
    refreshLogs();
  });
  source.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    state.eventHistory = [...state.eventHistory.slice(-149), data];
  });
  const bindHistory = (name) => {
    source.addEventListener(name, (event) => {
      const data = JSON.parse(event.data);
      state.eventHistory = [...state.eventHistory.slice(-149), data];
    });
  };
  ["model.activated","reference.saved","reference.deleted","dataset.created","dataset.deleted","dataset.updated","finetune.started","finetune.stopping","finetune.state","synthesis.started"].forEach(bindHistory);
  ["job.created","job.updated"].forEach(bindHistory);
  source.addEventListener("model.activated", () => {
    schedule("models", bootModels);
    schedule("synthesis", bootSynthesis);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("reference.saved", () => {
    schedule("references", bootReferences);
    schedule("synthesis", bootSynthesis);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("reference.deleted", () => {
    schedule("references", bootReferences);
    schedule("synthesis", bootSynthesis);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("dataset.created", () => {
    schedule("datasets", bootDatasets);
    schedule("finetune", bootFinetune);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("dataset.deleted", () => {
    schedule("datasets", bootDatasets);
    schedule("finetune", bootFinetune);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("dataset.updated", () => {
    schedule("datasets", bootDatasets);
    schedule("finetune", bootFinetune);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("finetune.started", () => {
    schedule("finetune", bootFinetune);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("finetune.stopping", () => {
    schedule("finetune", bootFinetune);
    schedule("logs", refreshLogs);
  });
  source.addEventListener("finetune.state", () => {
    schedule("finetune", bootFinetune);
    schedule("logs", refreshLogs);
    schedule("models", bootModels);
  });
  source.addEventListener("synthesis.started", () => {
    schedule("logs", refreshLogs);
  });
  source.addEventListener("job.created", () => {
    schedule("logs", refreshLogs);
  });
  source.addEventListener("job.updated", () => {
    schedule("logs", refreshLogs);
  });
  source.onerror = () => {
    window.setTimeout(connectEvents, 2000);
    source.close();
  };
  return source;
}
