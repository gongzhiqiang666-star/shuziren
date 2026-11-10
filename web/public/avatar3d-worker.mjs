/* Local integration around HeadAudio (MIT), pinned source in vendor/headaudio.
 * This is acoustic classification using the upstream EN model, not Mandarin
 * forced alignment. Analyze once, then animate against the playback clock. */
import { Processor } from './vendor/headaudio/modules/processor.mjs';
import { Training } from './vendor/headaudio/modules/training.mjs';

const names = ['aa', 'E', 'ih', 'oh', 'ou', 'PP', 'SS', 'TH', 'DD', 'FF', 'kk', 'nn', 'RR', 'CH', 'sil'];
const modelSHA = '0358f68989b5861f9b7d18871b010fa6cbf88a53bda4954a954d8c548bbcf251';
let used = false;
self.onmessage = async ({ data }) => {
  if (used) return;
  used = true;
  try {
    const { samples, sampleRate, duration, sha256 } = data;
    if (!(samples instanceof Float32Array) || !Number.isInteger(sampleRate) || sampleRate < 16000 || sampleRate > 96000 ||
        !Number.isFinite(duration) || duration <= 0 || duration > 300 || Math.abs(samples.length / sampleRate - duration) > 0.002 ||
        samples.length > 28_800_000 || !/^[a-f0-9]{64}$/.test(sha256)) throw new Error('音频分析输入无效。');
    for (const value of samples) if (!Number.isFinite(value)) throw new Error('音频含无效采样。');
    const response = await fetch('./vendor/headaudio/dist/model-en-mixed.bin', { credentials: 'omit', redirect: 'error' });
    if (!response.ok) throw new Error('本地声学模型缺失，请重新准备验证版资源。');
    const bin = await response.arrayBuffer();
    if (bin.byteLength !== 14352) throw new Error('本地声学模型长度不符。');
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bin)), b => b.toString(16).padStart(2, '0')).join('');
    if (digest !== modelSHA) throw new Error('本地声学模型校验失败。');
    const training = new Training();
    const model = [];
    for (let offset = 0; offset < bin.byteLength; offset += 368) model.push(training.decodeBinaryRecord(new Float32Array(bin, offset, 92)));
    const events = [{ time: 0, viseme: 'sil' }];
    let active = 'sil';
    const change = (time, viseme) => {
      const t = Math.max(0, Math.min(duration, time));
      if (!Number.isFinite(t) || active === viseme) return;
      const last = events[events.length - 1];
      if (t < last.time) return;
      if (t === last.time) last.viseme = viseme;
      else events.push({ time: t, viseme });
      active = viseme;
    };
    const processor = new Processor({ sampleRate, parameterData: { silMode: 0 }, processorOptions: {} }, {
      port: { postMessage(event) {
        if (event.event === 'viseme' && Number.isInteger(event.viseme) && event.viseme >= 0 && event.viseme < names.length) change(event.t, names[event.viseme]);
        else if (event.event === 'ended' || event.event === 'end') change(event.t, 'sil');
      } }
    });
    processor._onmessage({ data: { event: 'model', model, reset: true } });
    const chunk = 8192;
    let progress = -1;
    for (let offset = 0; offset < samples.length; offset += chunk) {
      processor.process(samples.subarray(offset, Math.min(samples.length, offset + chunk)));
      const next = Math.floor(100 * Math.min(samples.length, offset + chunk) / samples.length);
      if (next !== progress) { progress = next; self.postMessage({ type: 'progress', progress }); }
    }
    const cues = events.map((event, i) => ({ start: event.time, end: events[i + 1]?.time ?? duration, viseme: event.viseme })).filter(cue => cue.end > cue.start);
    if (cues.length > 30000) throw new Error('口型轨道过长，请缩短测试音频。');
    self.postMessage({ type: 'result', track: {
      version: 1, duration, source_audio_sha256: sha256, cues
    } });
  } catch (error) { self.postMessage({ type: 'error', message: error instanceof Error ? error.message : '本地分析失败。' }); }
};
