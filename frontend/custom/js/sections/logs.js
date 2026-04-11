import { json } from "../api.js";
import { state } from "../state.js";
import { escapeHtml, qs } from "../ui.js";

export async function refreshLogs(){
  const [status, jobs] = await Promise.all([json("/api/finetune/status"), json("/api/jobs")]);
  state.finetuneStatus = status;
  state.jobs = jobs.jobs || [];
  qs("hero-finetune").textContent = state.finetuneStatus.state || "idle";
  renderLogs();
}

export function renderLogs(){
  const log = escapeHtml(state.finetuneStatus?.log_tail || "Лог пока пуст.");
  const steps = (state.finetuneStatus?.steps || []).map((item, index) => `<div class="card"><strong>${index + 1}</strong><span>${escapeHtml(item.label.replace(/^Step \d\/\d: /, ""))}</span><div class="compact">${item.state}</div></div>`).join("");
  const events = state.eventHistory.slice().reverse().slice(0, 12).map((item) => `<div class="message success"><strong>${escapeHtml(item.kind)}</strong>${escapeHtml(item.timestamp || "")}</div>`).join("");
  const jobs = state.jobs.slice(0, 10).map((item) => `<div class="message ${item.status === "failed" ? "error" : item.status === "completed" ? "success" : "warn"}"><div class="row"><strong>${escapeHtml(item.kind)} #${escapeHtml(item.id)}</strong>${["queued","running"].includes(item.status) ? `<button class="button danger" data-cancel-job="${escapeHtml(item.id)}">Cancel</button>` : ""}</div>${escapeHtml(item.status)} · ${escapeHtml(item.updated_at || "")}</div>`).join("");
  qs("tab-logs").innerHTML = `
    <div class="section">
      <div class="panel stack"><div class="row"><h2>Логи и прогресс</h2><button id="logs-refresh" class="button ghost">Обновить</button></div><div class="steps">${steps}</div></div>
      <div class="panel stack"><h2>Jobs</h2>${jobs || `<div class="message warn">Задач пока нет.</div>`}</div>
      <div class="panel stack"><h2>Event history</h2>${events || `<div class="message warn">Событий пока нет.</div>`}</div>
      <div class="logbox">${log}</div>
    </div>
  `;
  qs("logs-refresh").onclick = refreshLogs;
  qs("tab-logs").onclick = async (event) => {
    const button = event.target.closest("[data-cancel-job]");
    if (!button) return;
    await json(`/api/jobs/${button.dataset.cancelJob}/cancel`, { method: "POST" });
    await refreshLogs();
  };
}

export async function bootLogs(){ await refreshLogs(); }
