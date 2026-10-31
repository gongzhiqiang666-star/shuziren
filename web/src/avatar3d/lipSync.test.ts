import { describe, expect, it } from 'vitest'
import {
  LIP_SYNC_LIMITS, LipSyncValidationError, VISEME_IDS,
  parseLipSyncTrack, sampleAmplitudeFallback, sampleViseme,
} from './lipSync'
import type { LipSyncValidationCode, VisemeId } from './lipSync'

const audio = { duration: 2, sha256: 'a'.repeat(64) }
const cue = (start: number, end: number, viseme: VisemeId) => ({ start, end, viseme })
function document(cues = [cue(0, 0.5, 'PP'), cue(0.5, 1, 'aa'), cue(1, 1.5, 'FF'), cue(1.5, 2, 'sil')]) {
  return { version: 1, duration: 2, source_audio_sha256: audio.sha256, cues }
}
function rejects(input: unknown, code: LipSyncValidationCode, identity = audio) {
  try {
    parseLipSyncTrack(input, identity)
    expect.fail('Invalid track unexpectedly accepted')
  } catch (error) {
    expect(error).toBeInstanceOf(LipSyncValidationError)
    expect((error as LipSyncValidationError).code).toBe(code)
  }
}

describe('音频绑定与有界轨道导入', () => {
  it('标准 v1 必须绑定实际选中文件的 SHA-256，复制输入后冻结', () => {
    const input = document()
    const track = parseLipSyncTrack(input, audio)
    expect(track).toMatchObject({ format: 'standard-v1', binding: 'sha256-verified', sourceAudioSha256: audio.sha256, audioDuration: 2 })
    input.cues[0].viseme = 'aa'
    expect(track.cues[0].viseme).toBe('PP')
    expect(Object.isFrozen(track)).toBe(true)
    expect(Object.isFrozen(track.cues)).toBe(true)
    expect(Object.isFrozen(track.cues[0])).toBe(true)
  })

  it('同长度的另一份音频不能复用标准轨道，缺失或伪造 SHA 也拒绝', () => {
    rejects(document(), 'AUDIO_HASH_MISMATCH', { ...audio, sha256: 'b'.repeat(64) })
    rejects({ ...document(), source_audio_sha256: undefined }, 'INVALID_HASH')
    rejects({ ...document(), source_audio_sha256: 'A'.repeat(64) }, 'INVALID_HASH')
    rejects(document(), 'INVALID_AUDIO', { ...audio, sha256: 'audio.wav' })
  })

  it('JSON 文本与已经解析的对象使用相同校验，拒绝混合格式和未知版本', () => {
    expect(parseLipSyncTrack(JSON.stringify(document()), audio)).toEqual(parseLipSyncTrack(document(), audio))
    rejects('{bad json', 'INVALID_JSON')
    rejects({ ...document(), version: 2 }, 'INVALID_FORMAT')
    rejects({ ...document(), metadata: { duration: 2 } }, 'UNKNOWN_FIELD')
    rejects({ ...document(), cues: [{ start: 0, end: 2, viseme: 'aa', confidence: 1 }] }, 'UNKNOWN_FIELD')
    rejects([], 'INVALID_FORMAT')
    rejects(null, 'INVALID_FORMAT')
  })

  it('不执行对象访问器或接受继承字段，JSON 中的原型字段也不能进入轨道', () => {
    let called = false
    const accessor = { ...document(), get duration() { called = true; return 2 } }
    rejects(accessor, 'INVALID_FORMAT')
    expect(called).toBe(false)
    rejects(Object.create(document()), 'INVALID_FORMAT')
    rejects(JSON.stringify(document()).replace('"version":1', '"version":1,"__proto__":{}'), 'UNKNOWN_FIELD')
  })

  it('限制 JSON UTF-8 字节数和 cue 数量，包含多字节字符时仍按字节限制', () => {
    rejects(' '.repeat(LIP_SYNC_LIMITS.maxJsonBytes + 1), 'INPUT_TOO_LARGE')
    rejects('中'.repeat(Math.floor(LIP_SYNC_LIMITS.maxJsonBytes / 3) + 1), 'INPUT_TOO_LARGE')
    rejects({ ...document(), cues: new Array(LIP_SYNC_LIMITS.maxCues + 1).fill(cue(0, 1, 'aa')) }, 'INVALID_CUES')
  })

  it('时长允许最多 20ms 导出舍入差，不按音频长度拉伸嘴形时间', () => {
    const input = document([cue(0, 1.98, 'aa')])
    input.duration = 1.98
    const track = parseLipSyncTrack(input, audio)
    expect(track.duration).toBe(1.98)
    expect(track.cues[0].end).toBe(1.98)
    expect(sampleViseme(track, 1.99).sil).toBe(1)
    rejects({ ...input, duration: 1.979 }, 'DURATION_MISMATCH')
    const longer = parseLipSyncTrack({ ...document([cue(0, 2.01, 'aa')]), duration: 2.01 }, audio)
    expect(sampleViseme(longer, audio.duration).sil).toBe(1)
  })

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY, 300.001, '2'])('拒绝无效轨道时长 %s', value => {
    rejects({ ...document(), duration: value }, 'INVALID_DURATION')
  })

  it.each([0, Number.NaN, Number.POSITIVE_INFINITY, 301])('实际音频时长未就绪或越界时不能导入 %s', value => {
    rejects(document(), 'INVALID_AUDIO', { ...audio, duration: value })
  })

  it.each([
    [[], 'INVALID_CUES'],
    [[{ start: 0, end: 2, viseme: 'mouthOpen' }], 'UNKNOWN_VISEME'],
    [[{ start: 0, end: 2, viseme: 'AA' }], 'UNKNOWN_VISEME'],
    [[{ start: '0', end: 2, viseme: 'aa' }], 'INVALID_TIME'],
    [[{ start: 0, end: Number.NaN, viseme: 'aa' }], 'INVALID_TIME'],
    [[{ start: -0.1, end: 1, viseme: 'aa' }], 'INVALID_TIME'],
    [[cue(0.5, 0.5, 'aa')], 'INVALID_TIME'],
    [[cue(1, 0.5, 'aa')], 'INVALID_TIME'],
    [[cue(0, 2.001, 'aa')], 'INVALID_TIME'],
    [[cue(0, 1, 'PP'), cue(0.99, 2, 'aa')], 'OVERLAPPING_CUES'],
    [[cue(1, 2, 'aa'), cue(0, 1, 'PP')], 'OVERLAPPING_CUES'],
  ] as const)('拒绝空、未知、非法或重叠 cue %s', (cues, code) => {
    rejects({ ...document(), cues }, code)
  })
})

describe('Rhubarb 兼容导入', () => {
  it('保留 duration-only 状态，区分闭唇、唇齿音、圆唇和静息', () => {
    const values = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X']
    const track = parseLipSyncTrack({
      metadata: { duration: 2, soundFile: 'C:\\private\\reference.wav' },
      mouthCues: values.map((value, index) => ({ start: index * 0.2, end: (index + 1) * 0.2, value })),
    }, audio)
    expect(track).toMatchObject({ format: 'rhubarb', binding: 'duration-only', sourceAudioSha256: null })
    expect(track.cues.map(value => value.viseme)).toEqual(['PP', 'SS', 'E', 'aa', 'oh', 'ou', 'FF', 'nn', 'sil'])
    expect(JSON.stringify(track)).not.toContain('private')
    expect(sampleViseme(track, 0.1).PP).toBe(1)
    expect(sampleViseme(track, 1.1).ou).toBe(1)
    expect(sampleViseme(track, 1.3).FF).toBe(1)
    expect(sampleViseme(track, 1.9).sil).toBe(1)
  })

  it('拒绝未知 Rhubarb 嘴形、缺失 duration 与未声明的额外身份字段', () => {
    const input = { metadata: { duration: 2 }, mouthCues: [{ start: 0, end: 2, value: 'I' }] }
    rejects(input, 'UNKNOWN_RHUBARB_CUE')
    rejects({ ...input, metadata: {} }, 'INVALID_DURATION')
    rejects({ ...input, source_audio_sha256: audio.sha256 }, 'UNKNOWN_FIELD')
    rejects({ ...input, metadata: { duration: 2, soundFile: 'a'.repeat(2049) } }, 'INVALID_FORMAT')
  })
})

describe('使用实际音频时间采样', () => {
  const track = parseLipSyncTrack(document(), audio)

  it('暂停、向前/向后 seek 和重播不会累计口型时钟误差', () => {
    const expected = sampleViseme(track, 0.75)
    for (const time of [0, 0.75, 1.25, 2, 0.1, 0.75, 1.9, 0.75]) sampleViseme(track, time)
    expect(sampleViseme(track, 0.75)).toEqual(expected)
    expect(sampleViseme(track, 0.75)).toEqual(sampleViseme(track, 0.75))
    expect(sampleViseme(track, 0.1).PP).toBe(1)
    expect(sampleViseme(track, 1.25).FF).toBe(1)
  })

  it('精确按半开区间切换，负时间、结束及未就绪时间均回到静息', () => {
    expect(sampleViseme(track, 0.499, 0).PP).toBe(1)
    expect(sampleViseme(track, 0.5, 0).aa).toBe(1)
    expect(sampleViseme(track, 1, 0).FF).toBe(1)
    for (const time of [-1, 2, 300, Number.NaN, Number.POSITIVE_INFINITY]) expect(sampleViseme(track, time).sil).toBe(1)
  })

  it('空隙和首尾未覆盖时间都闭口，不按文字长度或邻近音量补动作', () => {
    const sparse = parseLipSyncTrack(document([cue(0.2, 0.7, 'aa'), cue(1.2, 1.6, 'ou')]), audio)
    for (const time of [0, 0.19, 0.7, 1, 1.19, 1.6, 1.99]) expect(sampleViseme(sparse, time).sil).toBe(1)
    expect(sampleViseme(sparse, 0.2).aa).toBe(1)
    expect(sampleViseme(sparse, 1.2).ou).toBe(1)
  })

  it('相邻开口嘴形在时间域平滑，所有权重有限、归一且没有播放历史状态', () => {
    const transition = sampleViseme(track, 1)
    expect(transition.aa).toBeCloseTo(0.5)
    expect(transition.FF).toBeCloseTo(0.5)
    for (const time of [0.97, 0.98, 0.99, 1, 1.01, 1.02, 1.03]) {
      const weights = sampleViseme(track, time)
      expect(Object.keys(weights)).toEqual([...VISEME_IDS])
      expect(Object.values(weights).every(weight => Number.isFinite(weight) && weight >= 0 && weight <= 1)).toBe(true)
      expect(Object.values(weights).reduce((sum, weight) => sum + weight, 0)).toBeCloseTo(1)
    }
    expect(sampleViseme(track, 1)).toEqual(transition)
    expect(Object.isFrozen(transition)).toBe(true)
  })

  it('闭唇与静息段不混入邻居的开口权重，短 cue 仍有完整保持段', () => {
    expect(sampleViseme(track, 0.499).PP).toBe(1)
    expect(sampleViseme(track, 1.5).sil).toBe(1)
    const fast = parseLipSyncTrack(document([cue(0, 0.01, 'aa'), cue(0.01, 0.02, 'ou'), cue(0.02, 2, 'PP')]), audio)
    expect(sampleViseme(fast, 0.015).ou).toBe(1)
    expect(sampleViseme(fast, 0.02).PP).toBe(1)
    expect(() => sampleViseme(fast, 0.01, 0.1)).toThrow(RangeError)
  })
})

it('音量驱动是独立且明确标注的预览降级，不能伪装成音素轨道', () => {
  const silent = sampleAmplitudeFallback(0)
  const talking = sampleAmplitudeFallback(0.1)
  expect(silent).toMatchObject({ kind: 'amplitude-fallback', quality: 'preview-only' })
  expect(silent.weights.sil).toBe(1)
  expect(talking.weights.aa).toBeGreaterThan(0)
  expect(talking.weights.PP).toBe(0)
  expect(talking.weights.FF).toBe(0)
  expect(talking.weights.ou).toBe(0)
  expect(() => sampleAmplitudeFallback(Number.NaN)).toThrow(RangeError)
  expect(() => sampleAmplitudeFallback(1.1)).toThrow(RangeError)
})
