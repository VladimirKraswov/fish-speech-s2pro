import { audio, json } from "../api.js";
import { playLiveAudio, stopLiveAudio } from "../live-audio.js";
import { state, setMessage } from "../state.js";
import { escapeHtml, labelWithHelp, messageBlock, qs, helpTip } from "../ui.js";

const SYNTH_SETTINGS_KEY = "fish-speech-studio.synth-options.v1";
const FALLBACK_DEFAULTS = Object.freeze({
  chunk_length: 240,
  temperature: 0.62,
  top_p: 0.88,
  repetition_penalty: 1.15,
  seed: null,
  normalize: true,
  use_memory_cache: "on",
  x_vector_only_mode: false,
});
const VLLM_FALLBACK_DEFAULTS = Object.freeze({
  voice: "default",
  speed: 1.0,
  temperature: 0.62,
  top_p: 0.88,
  seed: null,
  language: "auto",
  instructions: "",
  max_new_tokens: 1024,
  initial_codec_chunk_frames: 6,
  x_vector_only_mode: false,
});
const FALLBACK_LIMITS = Object.freeze({
  max_text_length: 1500,
  reference_max_seconds: 30,
  reference_sample_rate: 24000,
  reference_channels: 1,
});
const FISH_SUPPORTED_FIELDS = Object.freeze([
  "text",
  "reference_id",
  "references",
  "chunk_length",
  "top_p",
  "repetition_penalty",
  "temperature",
  "seed",
  "normalize",
  "use_memory_cache",
]);
const VLLM_SUPPORTED_FIELDS = Object.freeze([
  "text",
  "voice",
  "reference_id",
  "references",
  "speed",
  "temperature",
  "top_p",
  "seed",
  "language",
  "instructions",
  "max_new_tokens",
  "initial_codec_chunk_frames",
  "x_vector_only_mode",
]);

function safeParseSavedOptions(){
  try {
    return JSON.parse(window.localStorage.getItem(SYNTH_SETTINGS_KEY) || "null") || {};
  } catch {
    return {};
  }
}

function persistSynthOptions(){
  if (!state.synthOptions) return;
  try {
    window.localStorage.setItem(SYNTH_SETTINGS_KEY, JSON.stringify(state.synthOptions));
  } catch {
    // Ignore browsers with disabled storage.
  }
}

function finiteNumber(value, fallback){
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function finiteInteger(value, fallback){
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function synthEngine(){
  return state.synthCapabilities?.engine || state.renderEngine || "fish";
}

function usingVllmOmni(){
  return synthEngine() === "vllm-omni";
}

function fallbackDefaultsForEngine(){
  return usingVllmOmni() ? VLLM_FALLBACK_DEFAULTS : FALLBACK_DEFAULTS;
}

function fallbackSupportedFieldsForEngine(){
  return usingVllmOmni() ? VLLM_SUPPORTED_FIELDS : FISH_SUPPORTED_FIELDS;
}

function runtimeDefaults(){
  return state.synthCapabilities?.defaults || fallbackDefaultsForEngine();
}

function runtimeLimits(){
  return state.synthCapabilities?.limits || FALLBACK_LIMITS;
}

function supportedRequestFields(){
  return new Set(state.synthCapabilities?.supported_request_fields || fallbackSupportedFieldsForEngine());
}

function supportsRequestField(name){
  return supportedRequestFields().has(name);
}

function referenceRecord(name){
  if (!name) return null;
  return state.references.find((item) => item.name === name) || null;
}

function ensureSynthOptions(){
  const defaults = runtimeDefaults();
  const seedDefault = defaults.seed ?? 12345;
  const source = state.synthSettingsInitialized ? (state.synthOptions || {}) : safeParseSavedOptions();
  state.synthOptions = {
    temperature: finiteNumber(source.temperature, defaults.temperature ?? FALLBACK_DEFAULTS.temperature),
    top_p: finiteNumber(source.top_p, defaults.top_p ?? FALLBACK_DEFAULTS.top_p),
    repetition_penalty: finiteNumber(
      source.repetition_penalty,
      defaults.repetition_penalty ?? FALLBACK_DEFAULTS.repetition_penalty,
    ),
    chunk_length: finiteInteger(source.chunk_length, defaults.chunk_length ?? FALLBACK_DEFAULTS.chunk_length),
    normalize: source.normalize ?? defaults.normalize ?? FALLBACK_DEFAULTS.normalize,
    use_memory_cache: String(source.use_memory_cache ?? defaults.use_memory_cache ?? FALLBACK_DEFAULTS.use_memory_cache),
    seedEnabled: Boolean(source.seedEnabled ?? false),
    seedValue: finiteInteger(source.seedValue, seedDefault),
    x_vector_only_mode: Boolean(source.x_vector_only_mode ?? defaults.x_vector_only_mode ?? false),
  };
  state.synthSettingsInitialized = true;
  persistSynthOptions();
}

async function loadCapabilities(){
  try {
    state.synthCapabilities = await json("/api/synthesis/capabilities");
  } catch (error) {
    if (!state.synthCapabilities) {
      const engine = synthEngine();
      state.synthCapabilities = {
        engine,
        ready: true,
        defaults: { ...(engine === "vllm-omni" ? VLLM_FALLBACK_DEFAULTS : FALLBACK_DEFAULTS) },
        limits: { ...FALLBACK_LIMITS },
        supported_request_fields: [...(engine === "vllm-omni" ? VLLM_SUPPORTED_FIELDS : FISH_SUPPORTED_FIELDS)],
      };
    }
    if (!state.messages.synthesis) {
      setMessage("synthesis", "warn", `Не удалось загрузить runtime defaults, использую fallback. ${error.message}`);
    }
  }
  ensureSynthOptions();
}

function cacheModes(){
  const defaults = runtimeDefaults();
  return [...new Set([state.synthOptions?.use_memory_cache, defaults.use_memory_cache, "on", "off"].filter(Boolean))];
}

function resolvedRenderReference(){
  return state.renderReferenceDraft ?? state.activeReference ?? "";
}

function resolvedLiveReference(){
  return state.liveReferenceDraft ?? state.activeReference ?? "";
}

function resolvedLiveText(){
  return state.liveText ?? state.currentText ?? "";
}

function settingsSummary(){
  const options = state.synthOptions || {};
  const parts = [];
  if (supportsRequestField("temperature")) parts.push(`Temperature ${options.temperature}`);
  if (supportsRequestField("top_p")) parts.push(`Top P ${options.top_p}`);
  if (supportsRequestField("repetition_penalty")) parts.push(`Repetition ${options.repetition_penalty}`);
  if (supportsRequestField("chunk_length")) parts.push(`Chunk ${options.chunk_length}`);
  if (supportsRequestField("seed")) parts.push(options.seedEnabled ? `seed ${options.seedValue}` : "seed runtime default");
  if (supportsRequestField("normalize")) parts.push(`Normalize ${options.normalize ? "on" : "off"}`);
  if (supportsRequestField("use_memory_cache")) parts.push(`Cache ${options.use_memory_cache}`);
  if (supportsRequestField("x_vector_only_mode")) parts.push(`X-vector only ${options.x_vector_only_mode ? "on" : "off"}`);
  return parts.join(" · ");
}

function defaultsSummary(){
  const defaults = runtimeDefaults();
  const parts = [];
  if (supportsRequestField("temperature")) parts.push(`temp ${defaults.temperature}`);
  if (supportsRequestField("top_p")) parts.push(`top_p ${defaults.top_p}`);
  if (supportsRequestField("repetition_penalty")) parts.push(`repetition ${defaults.repetition_penalty}`);
  if (supportsRequestField("chunk_length")) parts.push(`chunk ${defaults.chunk_length}`);
  if (supportsRequestField("seed")) parts.push(`seed ${defaults.seed == null ? "runtime random/default" : defaults.seed}`);
  if (supportsRequestField("normalize")) parts.push(`normalize ${defaults.normalize ? "on" : "off"}`);
  if (supportsRequestField("use_memory_cache")) parts.push(`cache ${defaults.use_memory_cache}`);
  if (supportsRequestField("x_vector_only_mode")) parts.push(`x-vector only ${defaults.x_vector_only_mode ? "on" : "off"}`);
  return `Defaults: ${parts.join(", ")}`;
}

function limitsSummary(){
  const limits = runtimeLimits();
  return `Limits: max text ${limits.max_text_length} chars · reference ${limits.reference_max_seconds}s · ${limits.reference_sample_rate} Hz · ${limits.reference_channels} ch`;
}

function capabilitySummary(){
  const caps = state.synthCapabilities || {};
  const compile = caps.compile_enabled ? "compile on" : "compile off";
  return `${caps.device || "device ?"} · ${caps.dtype || "dtype ?"} · ${compile}`;
}

function heroCards(){
  if (usingVllmOmni()) {
    return [
      { title: "Когда выбирать", text: "Быстрый итоговый TTS через vllm-omni, когда нужен нормальный WAV без прежнего обрезания." },
      { title: "Что доступно", text: "Здесь реально применяются temperature, top_p, seed и X-vector only mode для проблемных reference." },
      { title: "Что не применяется", text: "Fish-специфичные repetition penalty, chunk length, normalize text и memory cache в этом backend игнорируются." },
    ];
  }
  return [
    { title: "Когда выбирать", text: "Итоговый рендер, озвучка длинных фрагментов, работа с reference и повторяемый результат через seed." },
    { title: "Что доступно", text: "Temperature, top_p, repetition penalty, chunk length, normalize, memory cache и фиксированный seed." },
    { title: "Как быстрее начать", text: "Оставьте reference пустым для базового голоса или выберите сохранённый reference на вкладке References." },
  ];
}

function advancedSettingsNotice(referenceValue){
  if (!usingVllmOmni()) return "";
  const record = referenceRecord(referenceValue);
  const duration = Number(record?.reference_meta?.duration_sec || 0);
  const referenceNote = referenceValue
    ? (duration > 12
      ? `Reference ${referenceValue} длится ${duration.toFixed(1)}s. Для vllm-omni cloning обычно стабильнее короткий чистый сэмпл на 6-12 секунд с точным transcript. Длинные reference чаще дают шёпот, роботизацию или бульканье.`
      : "Если cloning уходит в шёпот или становится слишком роботизированным, попробуйте включить X-vector only mode. Этот режим меньше зависит от in-context cloning и часто стабильнее на проблемных reference.")
    : "Для vllm-omni в этой карточке оставлены только реально рабочие ручки. Fish-настройки вроде chunk length и repetition penalty здесь не применяются.";
  return `
    <div class="message warn">
      В этом backend реально используются только temperature, top_p, seed и X-vector only mode.
    </div>
    <div class="message warn">${escapeHtml(referenceNote)}</div>
  `;
}

function updateSettingsSummary(){
  const summary = qs("synth-settings-summary");
  if (summary) summary.textContent = settingsSummary();
}

function updateSeedControls(){
  const enabled = Boolean(state.synthOptions?.seedEnabled);
  const input = qs("synth-seed");
  const line = qs("synth-seed-line");
  if (input) input.disabled = !enabled;
  if (line) line.classList.toggle("disabled", !enabled);
}

function setOption(key, value){
  state.synthOptions = { ...(state.synthOptions || {}), [key]: value };
  persistSynthOptions();
  updateSettingsSummary();
  updateSeedControls();
}

function resetSynthOptions(){
  try {
    window.localStorage.removeItem(SYNTH_SETTINGS_KEY);
  } catch {
    // Ignore storage errors.
  }
  state.synthOptions = null;
  state.synthSettingsInitialized = false;
  ensureSynthOptions();
  setMessage("synthesis", "success", "Render settings сброшены к runtime defaults.");
  renderSynthesis();
}

function currentRenderPayload(extra = {}, referenceId = null, textValue = state.currentText){
  const options = state.synthOptions || {};
  const payload = {
    ...extra,
    text: textValue,
    reference_id: referenceId,
  };
  if (supportsRequestField("temperature")) payload.temperature = options.temperature;
  if (supportsRequestField("top_p")) payload.top_p = options.top_p;
  if (supportsRequestField("repetition_penalty")) payload.repetition_penalty = options.repetition_penalty;
  if (supportsRequestField("chunk_length")) payload.chunk_length = options.chunk_length;
  if (supportsRequestField("normalize")) payload.normalize = options.normalize;
  if (supportsRequestField("use_memory_cache")) payload.use_memory_cache = options.use_memory_cache;
  if (supportsRequestField("x_vector_only_mode")) payload.x_vector_only_mode = options.x_vector_only_mode;
  if (supportsRequestField("seed") && options.seedEnabled) payload.seed = options.seedValue;
  return payload;
}

function liveDisabled(){
  return state.liveEngine === "disabled";
}

function benchmarkBlock(bench, label){
  if (!bench) return "";
  return `
    <div class="message success">
      Benchmark ${escapeHtml(label)} · ${escapeHtml(bench.engine)} ·
      RTF ${escapeHtml(bench.rtf ?? "n/a")} ·
      ${escapeHtml(bench.elapsed_sec)}s / ${escapeHtml(bench.audio_sec)}s
    </div>
  `;
}

function progressBlock(mode){
  if (!state.synthJob.running) return "";
  if (mode === "live" && state.synthJob.mode !== "live") return "";
  if (mode === "render" && state.synthJob.mode === "live") return "";
  return `
    <div class="message warn">
      <strong>${escapeHtml(state.synthJob.mode || mode)}</strong> · ${escapeHtml(state.synthJob.phase)}
      <div class="compact">Получено: ${(state.synthJob.receivedBytes / 1024).toFixed(1)} KB</div>
    </div>
  `;
}

function renderGuideCard(title, text){
  return `
    <div class="guide-card">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(text)}</span>
    </div>
  `;
}

function renderModeHero({ badge, title, tip, description, cards }){
  return `
    <div class="panel mode-hero stack">
      <div class="badge-row">${badge}</div>
      <div class="mode-copy">
        <h2>${escapeHtml(title)} ${helpTip(tip)}</h2>
        <p class="lead-copy">${escapeHtml(description)}</p>
      </div>
      <div class="guide-grid">${cards.map((item) => renderGuideCard(item.title, item.text)).join("")}</div>
    </div>
  `;
}

function renderRenderTab(){
  ensureSynthOptions();
  const options = state.synthOptions;
  const playback = state.synthPlaybackError ? `<div class="message warn">${escapeHtml(state.synthPlaybackError)}</div>` : "";
  const referenceValue = resolvedRenderReference();
  const renderBadges = [
    `<span class="badge">render</span>`,
    `<span class="badge alt">${escapeHtml(state.activeReference ? "reference ready" : "reference optional")}</span>`,
  ].join("");
  qs("tab-synthesis").innerHTML = `
    <div class="section">
      ${renderModeHero({
        badge: renderBadges,
        title: "Synthesis",
        tip: usingVllmOmni()
          ? "Текущий render backend работает через vllm-omni. Text-only путь уже стабилен, а cloning с reference чувствителен к длине и чистоте образца."
          : "Обычный render-режим даёт лучший итоговый WAV, поддерживает reference cloning и тонкие настройки.",
        description: "Используйте этот режим, когда важнее качество, воспроизводимость и контроль над результатом, а не минимальная задержка.",
        cards: heroCards(),
      })}
      <div class="grid two">
        <div class="panel stack">
          <div class="row">
            <div class="panel-title">
              <h2>Что синтезировать</h2>
              <p>Введите текст, при необходимости прогоните его через preprocess и затем получите финальный WAV.</p>
            </div>
            <button id="text-preprocess" class="button ghost">Preprocess</button>
          </div>
          ${messageBlock(state.messages.synthesis)}
          ${benchmarkBlock(state.synthBench, "render")}
          ${progressBlock("render")}
          ${playback}
          <label class="field">
            <span>${labelWithHelp("Текст", "Итоговый текст для render-синтеза. Для длинных текстов ориентируйтесь на лимит max text справа.")}</span>
            <textarea id="synth-text" placeholder="Введите текст для финального синтеза">${escapeHtml(state.currentText || "")}</textarea>
          </label>
          <div class="grid two">
            <label class="field">
              <span>${labelWithHelp("Reference ID", "Сохранённый reference. Оставьте поле пустым, если нужен синтез без cloning.")}</span>
              <input id="synth-reference" value="${escapeHtml(referenceValue)}" placeholder="reference id или пусто">
            </label>
            <label class="field">
              <span>${labelWithHelp("Render model", "Текущая активная модель render. Меняется на вкладке Models.")}</span>
              <input id="synth-model" value="${escapeHtml(state.activeModel || "")}" readonly>
            </label>
          </div>
          ${advancedSettingsNotice(referenceValue)}
          <div class="helper-note">
            ${usingVllmOmni()
              ? "Для vllm-omni обычно имеет смысл трогать только <strong>temperature</strong>, <strong>top_p</strong>, <strong>seed</strong> и при проблемном reference попробовать <strong>X-vector only mode</strong>."
              : "Если вы только начали, используйте дефолтные настройки ниже. Обычно имеет смысл трогать только <strong>temperature</strong>, <strong>seed</strong> и иногда <strong>chunk length</strong>."}
          </div>
          <div class="card synth-advanced stack">
            <div class="row">
              <div class="stack synth-heading">
                <h3>Тонкая настройка render</h3>
                <div class="compact">${escapeHtml(defaultsSummary())}</div>
              </div>
              <button id="synth-reset" class="button ghost" ${state.synthJob.running ? "disabled" : ""}>Сбросить defaults</button>
            </div>
            <div class="grid three synth-grid">
              ${supportsRequestField("temperature") ? `<label class="field">
                <span>${labelWithHelp("Temperature", "Управляет вариативностью. Ниже - стабильнее и спокойнее, выше - разнообразнее и смелее.")}</span>
                <input id="synth-temperature" type="number" min="0" step="0.01" value="${options.temperature}">
              </label>` : ""}
              ${supportsRequestField("top_p") ? `<label class="field">
                <span>${labelWithHelp("Top P", "Ограничивает выбор вероятностной массы. Ниже - более консервативный результат.")}</span>
                <input id="synth-top-p" type="number" min="0" max="1" step="0.01" value="${options.top_p}">
              </label>` : ""}
              ${supportsRequestField("repetition_penalty") ? `<label class="field">
                <span>${labelWithHelp("Repetition penalty", "Помогает бороться с повторами. Слишком высокое значение может сделать речь менее естественной.")}</span>
                <input id="synth-repetition" type="number" min="0" step="0.01" value="${options.repetition_penalty}">
              </label>` : ""}
              ${supportsRequestField("chunk_length") ? `<label class="field">
                <span>${labelWithHelp("Chunk length", "Размер текстового куска для render. Меньше - безопаснее по памяти, больше - больше контекста за проход.")}</span>
                <input id="synth-chunk-length" type="number" min="1" step="1" value="${options.chunk_length}">
              </label>` : ""}
              ${supportsRequestField("use_memory_cache") ? `<label class="field">
                <span>${labelWithHelp("Use memory cache", "Управляет промежуточным кешированием в runtime. Обычно оставляйте on, если не отлаживаете поведение.")}</span>
                <select id="synth-memory-cache">
                  ${cacheModes().map((mode) => `<option value="${escapeHtml(mode)}" ${mode === options.use_memory_cache ? "selected" : ""}>${escapeHtml(mode)}</option>`).join("")}
                </select>
              </label>` : ""}
              ${supportsRequestField("normalize") ? `<div class="field field-check">
                <span>${labelWithHelp("Normalize text", "Нормализует числа, символы и служебные конструкции перед рендером.")}</span>
                <label class="checkline">
                  <input id="synth-normalize" type="checkbox" ${options.normalize ? "checked" : ""}>
                  <span>Включить нормализацию перед render</span>
                </label>
              </div>` : ""}
              ${supportsRequestField("x_vector_only_mode") ? `<div class="field field-check">
                <span>${labelWithHelp("X-vector only mode", "Использует только speaker embedding из reference и меньше полагается на in-context cloning. Полезно, если голос уходит в тихий шёпот, роботизацию или бульканье.")}</span>
                <label class="checkline">
                  <input id="synth-x-vector-only" type="checkbox" ${options.x_vector_only_mode ? "checked" : ""}>
                  <span>Использовать только speaker embedding</span>
                </label>
              </div>` : ""}
            </div>
            ${supportsRequestField("seed") ? `<div class="grid two synth-seed-grid">
              <div class="field field-check">
                <span>${labelWithHelp("Seed", "Фиксирует случайность. С одинаковым текстом и параметрами помогает повторять результат.")}</span>
                <label class="checkline">
                  <input id="synth-seed-enabled" type="checkbox" ${options.seedEnabled ? "checked" : ""}>
                  <span>Фиксировать seed в запросе</span>
                </label>
              </div>
              <label class="field" id="synth-seed-line">
                <span>${labelWithHelp("Seed value", "Число, которое будет отправлено в runtime, если фиксация seed включена.")}</span>
                <input id="synth-seed" type="number" step="1" value="${options.seedValue}">
              </label>
            </div>` : ""}
            <div class="compact">${escapeHtml(limitsSummary())}</div>
          </div>
          <div class="actions">
            <button id="synth-run" class="button primary" ${state.synthJob.running ? "disabled" : ""}>Синтезировать WAV</button>
            <button id="bench-render" class="button ghost" ${state.synthJob.running ? "disabled" : ""}>Измерить RTF render</button>
          </div>
          ${state.synthAudioUrl ? `<audio id="synth-player" class="audio" controls preload="metadata" src="${state.synthAudioUrl}"></audio>` : ""}
        </div>
        <div class="panel stack">
          <div class="panel-title">
            <h2>Что будет использовано</h2>
            <p>Короткая сводка по текущему render-контуру перед запуском.</p>
          </div>
          <div class="status-stack">
            <div class="message success">Synthesis model: ${escapeHtml(state.activeModel || "base")} (${escapeHtml(state.renderEngine)})</div>
            <div class="message ${state.activeReference || referenceValue ? "success" : "warn"}">Reference: ${escapeHtml(referenceValue || "без референса")}</div>
            <div class="message success">${escapeHtml(capabilitySummary())}</div>
            <div class="message success" id="synth-settings-summary">${escapeHtml(settingsSummary())}</div>
            <div class="message warn">${escapeHtml(limitsSummary())}</div>
          </div>
          <div class="helper-note">
            ${usingVllmOmni()
              ? "Если reference начинает звучать слишком тихо или невнятно, сначала попробуйте <strong>X-vector only mode</strong>. Если не помогло, сделайте отдельный короткий reference на 6-12 секунд."
              : "Для воспроизводимых тестов включите <strong>seed</strong>. Если текст начинает не помещаться в память, уменьшайте <strong>chunk length</strong> или сокращайте объём текста."}
          </div>
        </div>
      </div>
    </div>
  `;
  qs("text-preprocess").onclick = preprocessText;
  qs("synth-run").onclick = () => runSynthesis("/api/synthesis");
  qs("bench-render").onclick = () => runBenchmark("render");
  qs("synth-text").oninput = (event) => { state.currentText = event.target.value; };
  qs("synth-reference").oninput = (event) => { state.renderReferenceDraft = event.target.value; };
  bindAdvancedSettings();
}

function renderLiveTab(){
  const referenceValue = resolvedLiveReference();
  const textValue = resolvedLiveText();
  const disabled = liveDisabled();
  const liveBadges = [
    `<span class="badge alt">low latency</span>`,
    `<span class="badge">${escapeHtml(disabled ? "disabled" : state.liveEngine || "live")}</span>`,
  ].join("");
  let guidance = "Live-режим удобен для быстрого предпрослушивания и диалоговых сценариев. Он не повторяет все render-настройки один в один.";
  if (disabled) {
    guidance = "В текущем деплое live runtime выключен. Вкладка остаётся видимой как отдельный сценарий, но кнопки запуска будут недоступны.";
  } else if (state.liveEngine === "s2cpp") {
    guidance = "Текущий live engine оптимизирован под низкую задержку. Некоторые reference-сценарии и render-knobs здесь не применяются.";
  }
  qs("tab-live").innerHTML = `
    <div class="section">
      ${renderModeHero({
        badge: liveBadges,
        title: "Live Streaming",
        tip: "Потоковый режим подходит для быстрого прослушивания и низкой задержки, но обычно даёт меньше контроля, чем обычный render.",
        description: guidance,
        cards: [
          { title: "Когда выбирать", text: "Быстрый предпросмотр, разговорные сценарии, реактивный UI и минимизация задержки." },
          { title: "Что важно помнить", text: "Advanced render settings не переносятся в live один в один, поэтому итоговый звук может отличаться от Synthesis." },
          { title: "Reference", text: disabled ? "Пока live runtime выключен, reference здесь не используется." : "Некоторые live engines умеют reference ограниченно или игнорируют его полностью." },
        ],
      })}
      <div class="grid two">
        <div class="panel stack">
          <div class="panel-title">
            <h2>Текст для live-потока</h2>
            <p>Этот режим пытается начать воспроизведение раньше. Он хорош для проверки темпа и общего звучания.</p>
          </div>
          ${messageBlock(state.messages.live)}
          ${benchmarkBlock(state.liveBench, "live")}
          ${progressBlock("live")}
          <label class="field">
            <span>${labelWithHelp("Текст", "Текст для потоковой генерации. Для первого теста лучше использовать 1-2 короткие фразы.")}</span>
            <textarea id="live-text" placeholder="Введите текст для live streaming">${escapeHtml(textValue)}</textarea>
          </label>
          <div class="grid two">
            <label class="field">
              <span>${labelWithHelp("Reference ID", "Заполняйте только если ваш live engine действительно умеет использовать reference. Для s2cpp это может быть проигнорировано.")}</span>
              <input id="live-reference" value="${escapeHtml(referenceValue)}" placeholder="reference id или пусто" ${disabled ? "disabled" : ""}>
            </label>
            <label class="field">
              <span>${labelWithHelp("Live model", "Текущая активная модель live runtime. Назначается на вкладке Models.")}</span>
              <input id="live-model" value="${escapeHtml(state.liveModel || "")}" readonly>
            </label>
          </div>
          <div class="helper-note">
            Live streaming запускается без advanced render-карточки: здесь приоритет у скорости отклика. Для итогового качества и детерминированного seed переключайтесь обратно на вкладку <strong>Synthesis</strong>.
          </div>
          <div class="actions">
            <button id="live-stream" class="button secondary" ${(disabled || state.synthJob.running) ? "disabled" : ""}>Запустить live streaming</button>
            <button id="bench-live" class="button ghost" ${(disabled || state.synthJob.running) ? "disabled" : ""}>Измерить RTF live</button>
          </div>
        </div>
        <div class="panel stack">
          <div class="panel-title">
            <h2>Сводка live-контура</h2>
            <p>Перед запуском можно быстро понять, что доступно именно в live-режиме сейчас.</p>
          </div>
          <div class="status-stack">
            <div class="message ${disabled ? "warn" : "success"}">Live model: ${escapeHtml(state.liveModel || "base")} (${escapeHtml(state.liveEngine || "disabled")})</div>
            <div class="message ${referenceValue ? "success" : "warn"}">Reference draft: ${escapeHtml(referenceValue || "без референса")}</div>
            <div class="message success">Render model остаётся: ${escapeHtml(state.activeModel || "base")} (${escapeHtml(state.renderEngine)})</div>
            <div class="message warn">${escapeHtml(disabled ? "Live runtime currently disabled in this deployment." : "Live mode prioritizes latency over full parity with Synthesis settings.")}</div>
          </div>
          <div class="helper-note">
            ${escapeHtml(disabled
              ? "Если хотите включить live позже, понадобится поднять live runtime и назначить для него активную модель."
              : "Если нужен reference-conditioned итоговый файл или точное повторение через seed, оставайтесь в обычном render-режиме.")}
          </div>
        </div>
      </div>
    </div>
  `;
  qs("live-text").oninput = (event) => { state.liveText = event.target.value; };
  qs("live-reference").oninput = (event) => { state.liveReferenceDraft = event.target.value; };
  qs("live-stream").onclick = runLiveStream;
  qs("bench-live").onclick = () => runBenchmark("live");
}

function bindAdvancedSettings(){
  const defaults = runtimeDefaults();
  const reset = qs("synth-reset");
  const temperature = qs("synth-temperature");
  const topP = qs("synth-top-p");
  const repetition = qs("synth-repetition");
  const chunkLength = qs("synth-chunk-length");
  const memoryCache = qs("synth-memory-cache");
  const normalize = qs("synth-normalize");
  const seedEnabled = qs("synth-seed-enabled");
  const seed = qs("synth-seed");
  const xVectorOnly = qs("synth-x-vector-only");

  if (reset) reset.onclick = resetSynthOptions;
  if (temperature) temperature.oninput = (event) => setOption("temperature", finiteNumber(event.target.value, defaults.temperature ?? FALLBACK_DEFAULTS.temperature));
  if (topP) topP.oninput = (event) => setOption("top_p", finiteNumber(event.target.value, defaults.top_p ?? FALLBACK_DEFAULTS.top_p));
  if (repetition) repetition.oninput = (event) => setOption("repetition_penalty", finiteNumber(event.target.value, defaults.repetition_penalty ?? FALLBACK_DEFAULTS.repetition_penalty));
  if (chunkLength) chunkLength.oninput = (event) => setOption("chunk_length", finiteInteger(event.target.value, defaults.chunk_length ?? FALLBACK_DEFAULTS.chunk_length));
  if (memoryCache) memoryCache.onchange = (event) => setOption("use_memory_cache", event.target.value || defaults.use_memory_cache || FALLBACK_DEFAULTS.use_memory_cache);
  if (normalize) normalize.onchange = (event) => setOption("normalize", Boolean(event.target.checked));
  if (seedEnabled) seedEnabled.onchange = (event) => setOption("seedEnabled", Boolean(event.target.checked));
  if (seed) seed.oninput = (event) => setOption("seedValue", finiteInteger(event.target.value, defaults.seed ?? 12345));
  if (xVectorOnly) xVectorOnly.onchange = (event) => setOption("x_vector_only_mode", Boolean(event.target.checked));
  updateSeedControls();
  updateSettingsSummary();
}

export function renderSynthesis(){
  renderRenderTab();
  renderLiveTab();
}

async function preprocessText(){
  try {
    const data = await json("/api/text/preprocess", {
      method: "POST",
      body: JSON.stringify({ text: qs("synth-text").value }),
    });
    state.currentText = data.processed;
  } catch (error) {
    setMessage("synthesis", "error", error.message);
  }
  renderSynthesis();
}

async function runSynthesis(url){
  try {
    await stopLiveAudio();
    const textValue = qs("synth-text").value;
    const referenceId = qs("synth-reference").value || null;
    state.currentText = textValue;
    state.renderReferenceDraft = qs("synth-reference").value;
    state.synthPlaybackError = "";
    state.synthJob = { running: true, mode: url.endsWith("/stream") ? "streaming" : "regular", phase: "Подготовка запроса", receivedBytes: 0 };
    setMessage("synthesis", "warn", "Идёт синтез, это может занять несколько секунд.");
    renderSynthesis();
    const result = await audio(url, currentRenderPayload({}, referenceId, textValue));
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
  if (liveDisabled()) {
    setMessage("live", "warn", "Live runtime сейчас выключен в этом деплое.");
    renderSynthesis();
    return;
  }
  try {
    await stopLiveAudio();
    const liveInput = qs("live-text");
    const referenceInput = qs("live-reference");
    const value = liveInput ? liveInput.value : resolvedLiveText();
    const referenceId = referenceInput ? referenceInput.value : resolvedLiveReference();
    state.liveText = value;
    state.liveReferenceDraft = referenceId;
    state.synthJob = { running: true, mode: "live", phase: "Буферизация первых чанков", receivedBytes: 0 };
    setMessage("live", "warn", "Идёт live streaming. Advanced render settings из вкладки Synthesis сюда не применяются.");
    renderSynthesis();
    const query = new URLSearchParams({ text: value });
    if (referenceId) query.set("reference_id", referenceId);
    await playLiveAudio(`/api/synthesis/stream/live?${query.toString()}`, (receivedBytes) => {
      state.synthJob = { running: true, mode: "live", phase: "Играем поток", receivedBytes };
      renderSynthesis();
    });
    state.synthJob = { running: false, mode: "live", phase: "Поток завершён", receivedBytes: state.synthJob.receivedBytes };
    setMessage("live", "success", "Live streaming завершён.");
  } catch (error) {
    state.synthJob = { running: false, mode: "live", phase: "Ошибка", receivedBytes: state.synthJob.receivedBytes };
    setMessage("live", "error", error.message);
  }
  renderSynthesis();
}

function benchmarkPayload(target, referenceId, textValue){
  if (target === "live") {
    return {
      target,
      text: textValue,
      reference_id: referenceId,
    };
  }
  return currentRenderPayload({ target }, referenceId, textValue);
}

async function runBenchmark(target){
  try {
    await stopLiveAudio();
    const isLive = target === "live";
    const textInput = qs(isLive ? "live-text" : "synth-text");
    const referenceInput = qs(isLive ? "live-reference" : "synth-reference");
    const textValue = textInput ? textInput.value : (isLive ? resolvedLiveText() : state.currentText);
    const referenceId = referenceInput ? (referenceInput.value || null) : (isLive ? resolvedLiveReference() : resolvedRenderReference()) || null;
    if (isLive) {
      state.liveText = textValue;
      state.liveReferenceDraft = referenceInput ? referenceInput.value : resolvedLiveReference();
    } else {
      state.currentText = textValue;
      state.renderReferenceDraft = referenceInput ? referenceInput.value : resolvedRenderReference();
    }
    setMessage(isLive ? "live" : "synthesis", "warn", `Считаю RTF для ${target}...`);
    renderSynthesis();
    const result = await json("/api/synthesis/benchmark", {
      method: "POST",
      body: JSON.stringify(benchmarkPayload(target, referenceId, textValue)),
    });
    if (isLive) state.liveBench = result;
    else state.synthBench = result;
    setMessage(isLive ? "live" : "synthesis", "success", `RTF ${target}: ${result.rtf ?? "n/a"} (${result.engine}).`);
  } catch (error) {
    setMessage(target === "live" ? "live" : "synthesis", "error", error.message);
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
  await loadCapabilities();
  renderSynthesis();
}
