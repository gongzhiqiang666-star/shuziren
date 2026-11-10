export type GateName = 'install' | 'generation' | 'obs' | 'platform' | 'stability'
export type GateStatus = 'passed' | 'failed' | 'blocked'
export type ReadinessConclusion = 'incomplete' | 'failed' | 'local_chain_passed_platform_blocked' | 'platform_chain_passed'
export type ReadinessGate = { name: GateName; status: GateStatus; evidence: Record<string, unknown>; note: string; version: number; updated_at: string }
export type ReadinessRun = { id: string; shop_id: string; title: string; output_mode: 'virtual_camera' | 'srs'; conclusion: ReadinessConclusion; version: number; created_at: string; updated_at: string; gates: ReadinessGate[] }

export const gateOrder: GateName[] = ['install', 'generation', 'obs', 'platform', 'stability']
export const gateNames: Record<GateName, string> = { install: '环境与资产', generation: '真实语音', obs: '数字人与 OBS', platform: '平台验证', stability: '稳定性记录' }
