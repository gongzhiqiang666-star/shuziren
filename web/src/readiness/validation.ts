import type { ReadinessConclusion, ReadinessGate } from './types'

const sensitive = /(^|_)(password|passwd|secret|cookie|session|token|api_key|app_key|app_secret)($|_)/i
const sha256 = /^[a-f0-9]{64}$/
const truth = (gate: ReadinessGate, key: string) => gate.evidence[key] === true
const text = (gate: ReadinessGate, key: string) => typeof gate.evidence[key] === 'string' ? String(gate.evidence[key]).trim() : ''

export const preflightCommand = [
  'powershell -ExecutionPolicy Bypass -File scripts/check-live-readiness.ps1 `',
  '  -Manifest config/live-readiness.local.json `',
  '  -Output live-readiness-evidence/windows-preflight.json',
].join('\n')

export function validateGate(gate: ReadinessGate): string {
  for (const [key, value] of Object.entries(gate.evidence)) {
    if (sensitive.test(key)) return '证据字段不能包含密钥、令牌、Cookie 或其他敏感信息。'
    if (typeof value === 'string' && (/[\\/]/.test(value) || value.includes('://'))) return '证据只填写简短标签，不能保存本地路径或带地址的日志。'
  }
  if (gate.status !== 'passed') return ''
  if (gate.name === 'install' && (!text(gate, 'preflight_report') || !truth(gate, 'nvidia') || !truth(gate, 'assets') || !truth(gate, 'operator_confirmed'))) return '通过环境关需要预检报告标签、NVIDIA、资产和人工确认。'
  if (gate.name === 'generation' && (!truth(gate, 'new_text') || !sha256.test(text(gate, 'wav_sha256')) || !truth(gate, 'listened') || !truth(gate, 'same_wav'))) return '通过真实语音关需要新句、有效 WAV SHA-256、试听和同一份 WAV 确认。'
  if (gate.name === 'obs' && (!['virtual_camera', 'srs'].includes(text(gate, 'output_mode')) || !text(gate, 'video') || !text(gate, 'audio') || !truth(gate, 'reviewed'))) return '通过 OBS 关需要输出模式、画面证据、声音证据和录制回放确认。'
  if (gate.name === 'platform' && (!truth(gate, 'approved') || !text(gate, 'viewer_record'))) return '通过平台关需要已获授权和观看端证据。'
  if (gate.name === 'stability' && !text(gate, 'operator_record')) return '通过稳定性关需要人工记录。'
  return ''
}

export function conclusionLabel(value: ReadinessConclusion): string {
  return ({ incomplete: '尚未完成最小链路', failed: '验证失败，先处理当前断点', local_chain_passed_platform_blocked: '本地链路通过，平台验证尚未获准', platform_chain_passed: '平台链路已有真实证据' })[value]
}
