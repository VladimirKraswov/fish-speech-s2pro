let ctx;
let nextTime = 0;
let current;
let tail = new Uint8Array();

function parseHeader(bytes){
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return {
    formatTag: view.getUint16(20, true),
    channels: view.getUint16(22, true),
    sampleRate: view.getUint32(24, true),
    bitsPerSample: view.getUint16(34, true),
  };
}

function pcmToBuffer(bytes, meta){
  const frame = meta.channels * (meta.bitsPerSample / 8);
  const size = bytes.byteLength - (bytes.byteLength % frame);
  const body = bytes.slice(0, size);
  tail = bytes.slice(size);
  let input;
  if (meta.formatTag === 3 && meta.bitsPerSample === 32) {
    input = new Float32Array(body.buffer, body.byteOffset, body.byteLength / 4);
  } else if (meta.bitsPerSample === 16) {
    const src = new Int16Array(body.buffer, body.byteOffset, body.byteLength / 2);
    input = new Float32Array(src.length);
    for (let i = 0; i < src.length; i += 1) input[i] = src[i] / 32768;
  } else {
    throw new Error(`Unsupported live audio format: format=${meta.formatTag} bits=${meta.bitsPerSample}`);
  }
  const frames = input.length / meta.channels;
  const buffer = ctx.createBuffer(meta.channels, frames, meta.sampleRate);
  for (let ch = 0; ch < meta.channels; ch += 1) {
    const out = buffer.getChannelData(ch);
    for (let i = 0; i < frames; i += 1) out[i] = input[i * meta.channels + ch];
  }
  return buffer;
}

function schedule(buffer){
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  nextTime = Math.max(nextTime, ctx.currentTime + 0.05);
  source.start(nextTime);
  nextTime += buffer.duration;
}

export async function stopLiveAudio(){
  current?.abort();
  current = null;
  tail = new Uint8Array();
  nextTime = 0;
}

export async function playLiveAudio(url, onProgress){
  await stopLiveAudio();
  ctx = ctx || new AudioContext({ latencyHint: "interactive" });
  if (ctx.state !== "running") await ctx.resume();
  const ctrl = new AbortController();
  current = ctrl;
  const res = await fetch(url, { signal: ctrl.signal });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Streaming failed");
  const reader = res.body?.getReader();
  if (!reader) throw new Error("Streaming is not available in this browser");
  let meta, seen = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done || ctrl.signal.aborted) break;
    seen += value.byteLength;
    onProgress?.(seen);
    let chunk = value;
    if (!meta) {
      const full = new Uint8Array(tail.byteLength + value.byteLength);
      full.set(tail);
      full.set(value, tail.byteLength);
      if (full.byteLength < 44) {
        tail = full;
        continue;
      }
      meta = parseHeader(full.slice(0, 44));
      chunk = full.slice(44);
      tail = new Uint8Array();
    } else if (tail.byteLength) {
      const full = new Uint8Array(tail.byteLength + value.byteLength);
      full.set(tail);
      full.set(value, tail.byteLength);
      chunk = full;
    }
    if (!meta || !chunk.byteLength) continue;
    schedule(pcmToBuffer(chunk, meta));
  }
  current = null;
}
