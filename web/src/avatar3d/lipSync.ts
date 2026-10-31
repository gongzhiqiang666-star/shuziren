/**
 * Audio-timed viseme tracks. This module does not infer speech from text or
 * certify Chinese lip-sync quality. Pass HTMLAudioElement.currentTime on every
 * render frame; never advance a separate mouth-animation clock.
 */
export const VISEME_IDS = Object.freeze([
  'sil', 'PP', 'FF', 'TH', 'DD', 'kk', 'CH', 'SS', 'nn', 'RR', 'aa', 'E', 'ih', 'oh', 'ou',
] as const)

export type VisemeId = typeof VISEME_IDS[number]
export type VisemeWeights = Readonly<Record<VisemeId, number>>

export interface AudioIdentity {
  /** Duration of the actual decoded audio, in seconds. */
  readonly duration: number
  /** SHA-256 of the original audio file bytes, not the transcript or its URL. */
  readonly sha256: string
}

export interface LipSyncCue {
  readonly start: number
  readonly end: number
  readonly viseme: VisemeId
}

export interface LipSyncTrack {
  readonly format: 'standard-v1' | 'rhubarb'
  /** A matching hash binds bytes; it does not prove that the cues are accurate. */
  readonly binding: 'sha256-verified' | 'duration-only'
  readonly duration: number
  readonly audioDuration: number
  readonly sourceAudioSha256: string | null
  readonly cues: readonly LipSyncCue[]
}

export const LIP_SYNC_LIMITS = Object.freeze({
  maxJsonBytes: 2 * 1024 * 1024,
  maxCues: 30_000,
  maxDurationSeconds: 300,
  // Rhubarb truncates exported durations to hundredths of a second.
  durationToleranceSeconds: 0.02,
  maxTransitionSeconds: 0.08,
})

export type LipSyncValidationCode =
  | 'INVALID_JSON' | 'INPUT_TOO_LARGE' | 'INVALID_FORMAT' | 'UNKNOWN_FIELD'
  | 'INVALID_AUDIO' | 'INVALID_DURATION' | 'DURATION_MISMATCH'
  | 'INVALID_HASH' | 'AUDIO_HASH_MISMATCH' | 'INVALID_CUES'
  | 'INVALID_TIME' | 'OVERLAPPING_CUES' | 'UNKNOWN_VISEME' | 'UNKNOWN_RHUBARB_CUE'

export class LipSyncValidationError extends Error {
  constructor(readonly code: LipSyncValidationCode, message: string) {
    super(message)
    this.name = 'LipSyncValidationError'
  }
}

const SHA256 = /^[a-f0-9]{64}$/
const VISEME_SET = new Set<string>(VISEME_IDS)
// Rhubarb's nine shapes are coarser than the standard 15-viseme vocabulary.
// B represents several consonants/EE, and H represents L. This is a visual
// approximation, not phoneme recovery. Reference: official README, Mouth shapes:
// https://github.com/DanielSWolf/rhubarb-lip-sync#mouth-shapes
const RHUBARB_VISEMES = Object.freeze({
  A: 'PP', B: 'SS', C: 'E', D: 'aa', E: 'oh', F: 'ou', G: 'FF', H: 'nn', X: 'sil',
} as const)

function fail(code: LipSyncValidationCode, message: string): never {
  throw new LipSyncValidationError(code, message)
}

function record(value: unknown, label: string, allowedFields: readonly string[]): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return fail('INVALID_FORMAT', `${label} 必须是 JSON 对象。`)
  }
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) {
    return fail('INVALID_FORMAT', `${label} 必须是普通 JSON 对象。`)
  }
  const fields = Reflect.ownKeys(value)
  if (fields.length > allowedFields.length || fields.some(field => typeof field !== 'string' || !allowedFields.includes(field))) {
    return fail('UNKNOWN_FIELD', `${label} 包含不支持的字段。`)
  }
  // Object input is supported for an already parsed JSON document, not getters
  // or inherited properties with behavior. Do not evaluate accessor properties.
  for (const field of fields) {
    const descriptor = Object.getOwnPropertyDescriptor(value, field)
    if (!descriptor || !Object.hasOwn(descriptor, 'value')) {
      return fail('INVALID_FORMAT', `${label} 不接受动态属性。`)
    }
  }
  return value as Record<string, unknown>
}

function duration(value: unknown, code: 'INVALID_AUDIO' | 'INVALID_DURATION'): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > LIP_SYNC_LIMITS.maxDurationSeconds) {
    return fail(code, `音频与轨道时长必须大于 0 且不超过 ${LIP_SYNC_LIMITS.maxDurationSeconds} 秒。`)
  }
  return value
}

function hash(value: unknown, code: 'INVALID_AUDIO' | 'INVALID_HASH'): string {
  if (typeof value !== 'string' || !SHA256.test(value)) {
    return fail(code, '音频 SHA-256 必须是 64 位小写十六进制字符。')
  }
  return value
}

function documentInput(input: unknown): unknown {
  if (typeof input !== 'string') return input
  if (input.length > LIP_SYNC_LIMITS.maxJsonBytes || new TextEncoder().encode(input).byteLength > LIP_SYNC_LIMITS.maxJsonBytes) {
    return fail('INPUT_TOO_LARGE', '口型轨道 JSON 不能超过 2 MiB。')
  }
  try {
    return JSON.parse(input) as unknown
  } catch {
    return fail('INVALID_JSON', '口型轨道不是有效的 JSON。')
  }
}

function parseCues(input: unknown, trackDuration: number, format: LipSyncTrack['format']): readonly LipSyncCue[] {
  if (!Array.isArray(input) || input.length === 0 || input.length > LIP_SYNC_LIMITS.maxCues) {
    return fail('INVALID_CUES', `口型轨道必须包含 1 至 ${LIP_SYNC_LIMITS.maxCues} 条时间标记。`)
  }
  const cues: LipSyncCue[] = []
  const valueField = format === 'rhubarb' ? 'value' : 'viseme'
  let previousEnd = 0
  for (let index = 0; index < input.length; index += 1) {
    const cue = record(input[index], `第 ${index + 1} 条口型`, ['start', 'end', valueField])
    const { start, end } = cue
    if (typeof start !== 'number' || typeof end !== 'number' || !Number.isFinite(start) || !Number.isFinite(end)
      || start < 0 || end <= start || end > trackDuration) {
      return fail('INVALID_TIME', `第 ${index + 1} 条口型必须具有轨道时长内、有限且递增的起止时间。`)
    }
    if (start < previousEnd) {
      return fail('OVERLAPPING_CUES', `第 ${index + 1} 条口型与前一条重叠或顺序错误。`)
    }
    const value = cue[valueField]
    let viseme: VisemeId
    if (format === 'rhubarb') {
      if (typeof value !== 'string' || !Object.hasOwn(RHUBARB_VISEMES, value)) {
        return fail('UNKNOWN_RHUBARB_CUE', `第 ${index + 1} 条 Rhubarb 口型必须是 A 至 H 或 X。`)
      }
      viseme = RHUBARB_VISEMES[value as keyof typeof RHUBARB_VISEMES]
    } else {
      if (typeof value !== 'string' || !VISEME_SET.has(value)) {
        return fail('UNKNOWN_VISEME', `第 ${index + 1} 条口型名称不在支持的 15 种嘴形中。`)
      }
      viseme = value as VisemeId
    }
    cues.push(Object.freeze({ start, end, viseme }))
    previousEnd = end
  }
  return Object.freeze(cues)
}

/**
 * Accepts a standard v1 document or unmodified Rhubarb JSON. Standard documents
 * must bind the exact selected audio bytes via source_audio_sha256. Rhubarb
 * lacks that field: its duration-only binding must remain visible to the user.
 * Missing cue intervals are intentional silence; no timestamps are invented.
 */
export function parseLipSyncTrack(input: unknown, audio: AudioIdentity): LipSyncTrack {
  const audioRecord = record(audio, '实际音频信息', ['duration', 'sha256'])
  const audioDuration = duration(audioRecord.duration, 'INVALID_AUDIO')
  const audioHash = hash(audioRecord.sha256, 'INVALID_AUDIO')
  const parsed = documentInput(input)
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return fail('INVALID_FORMAT', '口型轨道必须是 JSON 对象。')
  }
  const isStandard = Object.hasOwn(parsed, 'version')
  const root = record(parsed, '口型轨道', isStandard
    ? ['version', 'duration', 'source_audio_sha256', 'cues']
    : ['metadata', 'mouthCues'])
  let trackDuration: number
  let sourceAudioSha256: string | null = null
  if (isStandard) {
    if (root.version !== 1) return fail('INVALID_FORMAT', '仅支持 version: 1 的标准口型轨道。')
    trackDuration = duration(root.duration, 'INVALID_DURATION')
    sourceAudioSha256 = hash(root.source_audio_sha256, 'INVALID_HASH')
    if (sourceAudioSha256 !== audioHash) {
      return fail('AUDIO_HASH_MISMATCH', '口型轨道不属于当前音频，请选择生成该轨道时使用的同一份音频文件。')
    }
  } else {
    const metadata = record(root.metadata, 'Rhubarb metadata', ['duration', 'soundFile'])
    if (Object.hasOwn(metadata, 'soundFile') && (typeof metadata.soundFile !== 'string' || metadata.soundFile.length > 2048)) {
      return fail('INVALID_FORMAT', 'Rhubarb soundFile 必须是不超过 2048 个字符的字符串。')
    }
    trackDuration = duration(metadata.duration, 'INVALID_DURATION')
  }
  // A nanosecond epsilon only absorbs floating-point subtraction noise at the
  // exact tolerance boundary. It never stretches/rescales the cue timeline.
  if (Math.abs(trackDuration - audioDuration) > LIP_SYNC_LIMITS.durationToleranceSeconds + 1e-9) {
    return fail('DURATION_MISMATCH', '口型轨道与当前音频时长不匹配，允许的导出舍入误差最多为 20 毫秒。')
  }
  const format = isStandard ? 'standard-v1' : 'rhubarb'
  const cues = parseCues(isStandard ? root.cues : root.mouthCues, trackDuration, format)
  return Object.freeze({
    format,
    binding: isStandard ? 'sha256-verified' : 'duration-only',
    duration: trackDuration,
    audioDuration,
    sourceAudioSha256,
    cues,
  })
}

function emptyWeights(): Record<VisemeId, number> {
  return Object.fromEntries(VISEME_IDS.map(id => [id, 0])) as Record<VisemeId, number>
}

const STATIC_WEIGHTS = Object.freeze(Object.fromEntries(VISEME_IDS.map(id => {
  const weights = emptyWeights()
  weights[id] = 1
  return [id, Object.freeze(weights)]
})) as Record<VisemeId, VisemeWeights>)

function blend(left: VisemeId, right: VisemeId, amount: number): VisemeWeights {
  if (left === right) return STATIC_WEIGHTS[left]
  const weights = emptyWeights()
  weights[left] = 1 - amount
  weights[right] = amount
  return Object.freeze(weights)
}

function transitionWidth(left: LipSyncCue, right: LipSyncCue, seconds: number): number {
  // Preserve both bilabial contact and silence. In particular, an adjacent vowel
  // must not leave PP half open or make a silent pause move the mouth.
  if (left.end !== right.start || left.viseme === right.viseme
    || left.viseme === 'sil' || right.viseme === 'sil' || left.viseme === 'PP' || right.viseme === 'PP') return 0
  return Math.min(seconds / 2, (left.end - left.start) / 4, (right.end - right.start) / 4)
}

function blendAt(left: LipSyncCue, right: LipSyncCue, time: number, width: number): VisemeWeights {
  const position = Math.max(0, Math.min(1, (time - (right.start - width)) / (2 * width)))
  const eased = position * position * (3 - 2 * position)
  return blend(left.viseme, right.viseme, eased)
}

/**
 * Stateless, bounded interpolation on the actual audio timeline. Repeated calls
 * at a paused time return the same pose; seeking/replaying needs no reset.
 * Intervals are [start,end). Outside the audio or in a gap, the result is idle.
 */
export function sampleViseme(track: LipSyncTrack, currentTimeSeconds: number, transitionSeconds = 0.04): VisemeWeights {
  if (!Number.isFinite(transitionSeconds) || transitionSeconds < 0 || transitionSeconds > LIP_SYNC_LIMITS.maxTransitionSeconds) {
    throw new RangeError('口型过渡时长必须是 0 至 80 毫秒之间的有限数值。')
  }
  if (!Number.isFinite(currentTimeSeconds) || currentTimeSeconds < 0
    || currentTimeSeconds >= track.audioDuration || currentTimeSeconds >= track.duration) return STATIC_WEIGHTS.sil
  let low = 0
  let high = track.cues.length - 1
  let index = -1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    if (track.cues[middle].start <= currentTimeSeconds) {
      index = middle
      low = middle + 1
    } else high = middle - 1
  }
  const cue = track.cues[index]
  if (!cue || currentTimeSeconds >= cue.end) return STATIC_WEIGHTS.sil
  if (transitionSeconds > 0) {
    const previous = track.cues[index - 1]
    if (previous) {
      const width = transitionWidth(previous, cue, transitionSeconds)
      if (width > 0 && currentTimeSeconds < cue.start + width) return blendAt(previous, cue, currentTimeSeconds, width)
    }
    const next = track.cues[index + 1]
    if (next) {
      const width = transitionWidth(cue, next, transitionSeconds)
      if (width > 0 && currentTimeSeconds >= cue.end - width) return blendAt(cue, next, currentTimeSeconds, width)
    }
  }
  return STATIC_WEIGHTS[cue.viseme]
}

export interface AmplitudeFallbackSample {
  readonly kind: 'amplitude-fallback'
  readonly quality: 'preview-only'
  readonly weights: VisemeWeights
}

/** Optional volume-only preview. Never called automatically on parsing failure. */
export function sampleAmplitudeFallback(rms: number): AmplitudeFallbackSample {
  if (!Number.isFinite(rms) || rms < 0 || rms > 1) throw new RangeError('音量 RMS 必须在 0 至 1 之间。')
  const opening = Math.max(0, Math.min(1, (rms - 0.02) / 0.18))
  return Object.freeze({ kind: 'amplitude-fallback', quality: 'preview-only', weights: blend('sil', 'aa', opening) })
}
