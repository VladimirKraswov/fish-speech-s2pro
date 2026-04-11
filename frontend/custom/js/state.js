export const state = {
  activeTab: "synthesis",
  datasets: [],
  dataset: null,
  references: [],
  activeReference: "",
  models: [],
  activeModel: null,
  liveModel: null,
  renderEngine: "fish",
  liveEngine: "fish",
  finetuneDefaults: null,
  finetuneStatus: null,
  validation: null,
  synthAudioUrl: "",
  currentText: "",
  synthPlaybackError: "",
  synthJob: { running: false, mode: "", phase: "idle", receivedBytes: 0 },
  synthLastUrl: "",
  synthBench: null,
  eventHistory: [],
  jobs: [],
  messages: {},
};

export function setMessage(key, kind, text){
  state.messages[key] = text ? { kind, text } : null;
}
