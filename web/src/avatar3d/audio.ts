export interface PreparedAudio {
  file: File
  sha256: string
  duration: number
  sampleRate: number
  mono: Float32Array
}

export async function sha256(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('')
}

/** Decode locally; the original file is both hashed and played. No upload. */
export async function prepareAudio(file: File): Promise<PreparedAudio> {
  if (!file.size || file.size > 32 * 1024 * 1024) throw new Error('请选择不超过 32 MiB 的 WAV 音频。')
  const bytes = await file.arrayBuffer()
  const header = new Uint8Array(bytes, 0, Math.min(12, bytes.byteLength))
  if (header.length < 12 || String.fromCharCode(...header.slice(0, 4)) !== 'RIFF' || String.fromCharCode(...header.slice(8, 12)) !== 'WAVE') {
    throw new Error('首版支持 WAV 文件。请先将其他格式转换为 WAV，再导入。')
  }
  const identity = await sha256(bytes)
  const decoder = new OfflineAudioContext(1, 1, 48000)
  let decoded: AudioBuffer
  try { decoded = await decoder.decodeAudioData(bytes) } catch { throw new Error('浏览器无法解码这份 WAV，请使用完整的 PCM WAV 音频。') }
  if (!Number.isFinite(decoded.duration) || decoded.duration <= 0 || decoded.duration > 300 || decoded.numberOfChannels > 2) {
    throw new Error('音频须为单声道或双声道，时长大于 0 且不超过 5 分钟。')
  }
  const mono = new Float32Array(decoded.length)
  for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
    const samples = decoded.getChannelData(channel)
    for (let index = 0; index < mono.length; index++) {
      const value = samples[index]
      if (!Number.isFinite(value)) throw new Error('音频包含无效采样值，无法分析。')
      mono[index] += value / decoded.numberOfChannels
    }
  }
  return { file, sha256: identity, duration: decoded.duration, sampleRate: decoded.sampleRate, mono }
}

export function pcmToWav(buffer: AudioBuffer): File {
  const count = buffer.length
  if (buffer.duration > 60 || buffer.numberOfChannels > 2) throw new Error('测试录音最长 60 秒，最多双声道。')
  const bytes = new ArrayBuffer(44 + count * 2)
  const view = new DataView(bytes)
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)) }
  text(0, 'RIFF'); view.setUint32(4, 36 + count * 2, true); text(8, 'WAVE'); text(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, buffer.sampleRate, true); view.setUint32(28, buffer.sampleRate * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, count * 2, true)
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i))
  for (let i = 0; i < count; i++) {
    const sample = Math.max(-1, Math.min(1, channels.reduce((sum, channel) => sum + channel[i]!, 0) / channels.length))
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true)
  }
  return new File([bytes], '我的测试录音.wav', { type: 'audio/wav' })
}
