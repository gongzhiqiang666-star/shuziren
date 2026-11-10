import { describe, expect, it } from 'vitest'
import { conclusionLabel, validateGate } from './validation'
import type { ReadinessGate } from './types'

function gate(name: ReadinessGate['name'], evidence: Record<string, unknown>): ReadinessGate {
  return { name, status: 'passed', evidence, note: '', version: 1, updated_at: '' }
}

describe('live readiness evidence', () => {
  it('requires new same-source listened WAV evidence', () => {
    expect(validateGate(gate('generation', { new_text: true, wav_sha256: 'a'.repeat(64), listened: true, same_wav: true }))).toBe('')
    expect(validateGate(gate('generation', { new_text: true, wav_sha256: 'short' }))).toContain('SHA-256')
  })
  it('requires both OBS audio and video', () => {
    expect(validateGate(gate('obs', { output_mode: 'virtual_camera', video: 'recording', audio: '', reviewed: true }))).toContain('声音')
  })
  it('allows platform to remain blocked', () => {
    expect(validateGate({ name: 'platform', status: 'blocked', evidence: { reason: 'not_approved' }, note: '', version: 1, updated_at: '' })).toBe('')
    expect(conclusionLabel('local_chain_passed_platform_blocked')).toContain('本地链路通过')
  })
  it('rejects secret keys and paths', () => {
    expect(validateGate({ name: 'install', status: 'blocked', evidence: { api_token: 'x' }, note: '', version: 1, updated_at: '' })).toContain('敏感')
    expect(validateGate({ name: 'install', status: 'blocked', evidence: { reason: 'C:\\private\\x' }, note: '', version: 1, updated_at: '' })).toContain('路径')
  })
})
