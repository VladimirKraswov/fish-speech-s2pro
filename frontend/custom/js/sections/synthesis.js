import { audio, json } from "../api.js";
import { playLiveAudio, stopLiveAudio } from "../live-audio.js";
import { state, setMessage } from "../state.js";
import { escapeHtml, messageBlock, qs } from "../ui.js";

export function renderSynthesis(){
  const job = state.synthJob;
  const bench = !state.synthBench ? "" : `
    <div class="message success">
      Benchmark ${escapeHtml(state.synthBench.target)} · ${escapeHtml(state.synthBench.engine)} ·
      RTF ${escapeHtml(state.synthBench.rtf ?? "n/a")} ·
      ${escapeHtml(state.synthBench.elapsed_sec)}s / ${escapeHtml(state.synthBench.audio_sec)}s
    </div>
  `;
  const progress = !job.running ? "" : `
    <div class="message warn">
      <strong>${escapeHtml(job.mode || "synthesis")}</strong> · ${escapeHtml(job.phase)}
      <div class="compact">Получено: ${(job.receivedBytes / 1024).toFixed(1)} KB</div>
    </div>
  `;
  const playback = state.synthPlaybackError ? `<div class="message warn">${escapeHtml(state.synthPlaybackError)}</div>` : "";
  qs("tab-synthesis").innerHTML = `
    <div class="grid two">
      <div class="panel stack">
        <div class="row"><h2>Synthesis</h2><button id="text-preprocess" class="button ghost">Preprocess</button></div>
        ${messageBlock(state.messages.synthesis)}
        ${bench}
        ${progress}
        ${playback}
        <textarea id="synth-text" placeholder="Введите текст для синтеза">${state.currentText || ""}</textarea>
        <div class="grid two">
          <input id="synth-reference" value="${state.activeReference || ""}" placeholder="reference id или пусто">
          <input id="synth-model" value="${state.activeModel || ""}" readonly>
        </div>
        <div class="actions"><button id="synth-run" class="button primary" ${job.running ? "disabled" : ""}>Синтезировать</button><button id="synth-stream" class="button secondary" ${job.running ? "disabled" : ""}>Live Streaming</button></div>
        <div class="actions"><button id="bench-render" class="button ghost" ${job.running ? "disabled" : ""}>RTF synthesis</button><button id="bench-live" class="button ghost" ${job.running ? "disabled" : ""}>RTF live</button></div>
        ${state.synthAudioUrl ? `<audio id="synth-player" class="audio" controls preload="metadata" src="${state.synthAudioUrl}"></audio>` : ""}
      </div>
      <div class="panel stack">
        <h2>Что будет использовано</h2>
        <div class="message success">Synthesis model: ${state.activeModel || "base"} (${state.renderEngine})</div>
        <div class="message success">Live model: ${state.liveModel || "base"} (${state.liveEngine})</div>
        <div class="message ${state.activeReference ? "success" : "warn"}">Reference: ${state.activeReference || "без референса"}</div>
        ${state.liveEngine === "s2cpp" ? `<div class="message warn">Live через s2.cpp не использует reference. Если указан reference, backend автоматически вернётся к Fish runtime.</div>` : ""}
      </div>
    </div>
  `;
  qs("text-preprocess").onclick = preprocessText;
  qs("synth-run").onclick = () => runSynthesis("/api/synthesis");
  qs("synth-stream").onclick = runLiveStream;
  qs("bench-render").onclick = () => runBenchmark("render");
  qs("bench-live").onclick = () => runBenchmark("live");
  qs("synth-text").oninput = (event) => { state.currentText = event.target.value; };
}

async function preprocessText(){
  const data = await json("/api/text/preprocess", { method: "POST", body: JSON.stringify({ text: qs("synth-text").value }) });
  state.currentText = data.processed;
  renderSynthesis();
}

async function runSynthesis(url){
  try {
    await stopLiveAudio();
    state.currentText = qs("synth-text").value;
    state.synthPlaybackError = "";
    state.synthJob = { running: true, mode: url.endsWith("/stream") ? "streaming" : "regular", phase: "Подготовка запроса", receivedBytes: 0 };
    setMessage("synthesis", "warn", "Идёт синтез, это может занять несколько секунд.");
    renderSynthesis();
    const result = await audio(url, { text: state.currentText, reference_id: qs("synth-reference").value || null });
    const oldUrl = state.synthAudioUrl;
    state.synthAudioUrl = result.url;
    state.synthLastUrl = result.url;
    state.synthJob = { running: false, mode: state.synthJob.mode, phase: "Готово", receivedBytes: result.receivedBytes };
    setMessage("synthesis", "success", `Аудио успешно сгенерировано, получено ${(result.receivedBytes / 1024).toFixed(1)} KB.`);
    if (oldUrl && oldUrl !== result.url) window.setTimeout(() => URL.revokeObjectURL(oldUrl), 30000);
  } catch (error) {
    state.synthJob = { running: false, mode: state.synthJob.mode, phase: "Ошибка", receivedBytes: state.synthJob.receivedBytes };
    setMessage("synthesis", "error", error.message);
  }
  renderSynthesis();
  await playAudio();
}

async function runLiveStream(){
  try {
    await stopLiveAudio();
    state.currentText = qs("synth-text").value;
    state.synthAudioUrl = "";
    state.synthPlaybackError = "";
    state.synthJob = { running: true, mode: "live", phase: "Буферизация первых чанков", receivedBytes: 0 };
    setMessage("synthesis", "warn", "Идёт live streaming. Звук начнётся сразу после первых PCM-чанков.");
    renderSynthesis();
    const query = new URLSearchParams({ text: state.currentText });
    const ref = qs("synth-reference").value || "";
    if (ref) query.set("reference_id", ref);
    await playLiveAudio(`/api/synthesis/stream/live?${query.toString()}`, (receivedBytes) => {
      state.synthJob = { running: true, mode: "live", phase: "Играем поток", receivedBytes };
      renderSynthesis();
    });
    state.synthJob = { running: false, mode: "live", phase: "Поток завершён", receivedBytes: state.synthJob.receivedBytes };
    setMessage("synthesis", "success", "Live streaming завершён.");
  } catch (error) {
    state.synthJob = { running: false, mode: "live", phase: "Ошибка", receivedBytes: state.synthJob.receivedBytes };
    setMessage("synthesis", "error", error.message);
  }
  renderSynthesis();
}

async function runBenchmark(target){
  try {
    state.currentText = qs("synth-text").value;
    setMessage("synthesis", "warn", `Считаю RTF для ${target}...`);
    renderSynthesis();
    state.synthBench = await json("/api/synthesis/benchmark", {
      method: "POST",
      body: JSON.stringify({ target, text: state.currentText, reference_id: qs("synth-reference").value || null }),
    });
    setMessage("synthesis", "success", `RTF ${target}: ${state.synthBench.rtf ?? "n/a"} (${state.synthBench.engine}).`);
  } catch (error) {
    setMessage("synthesis", "error", error.message);
  }
  renderSynthesis();
}

async function playAudio(){
  const player = qs("synth-player");
  if (!player) return;
  try {
    player.load();
    player.currentTime = 0;
    await player.play();
  } catch {
    state.synthPlaybackError = "Аудио готово, но браузер не разрешил автозапуск. Нажмите Play на плеере.";
    renderSynthesis();
  }
}

function bindProgress(){
  window.addEventListener("studio:synthesis-progress", (event) => {
    if (!state.synthJob.running) return;
    state.synthJob = { ...state.synthJob, phase: "Получаем аудио", receivedBytes: event.detail.receivedBytes || 0 };
    renderSynthesis();
  });
}

export async function bootSynthesis(){
  if (!window.__studioSynthProgressBound) {
    bindProgress();
    window.__studioSynthProgressBound = true;
  }
  renderSynthesis();
}
