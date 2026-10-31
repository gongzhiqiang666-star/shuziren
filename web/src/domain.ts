import type { Job, JobStatus, Persona, Product, QualityCheck, Session } from './types'

export function parseMoneyToCents(input: string): number {
  const value = input.trim()
  if (!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error('价格请输入非负金额，最多保留两位小数。')
  const [yuan = '0', fraction = ''] = value.split('.')
  const cents = Number(yuan) * 100 + Number(fraction.padEnd(2, '0'))
  if (!Number.isSafeInteger(cents)) throw new Error('金额过大，请核对商品价格。')
  return cents
}

export function money(cents: number): string { return '¥' + (cents / 100).toFixed(2) }
export function expired(product: Pick<Product, 'expires_at'>, now = Date.now()): boolean {
  return !!product.expires_at && new Date(product.expires_at).getTime() <= now
}
export function productAvailable(product: Product, now = Date.now()): boolean {
  return product.active && !expired(product, now)
}
export function localDateTime(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return adjusted.toISOString().slice(0, 16)
}
export function dateTime(value: string | null | undefined): string {
  if (!value || value.startsWith('0001-')) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}
export const jobLabels: Record<JobStatus, string> = {
  draft: '待审核', blocked: '需人工处理', approved: '已批准', queued: '等待合成', synthesizing: '正在合成',
  ready: '音频就绪', sending: '正在派发', sent: '上游已接收', cancelled: '已取消', failed: '任务失败', delivery_unknown: '派发结果不明',
}
export function jobTone(status: JobStatus): string {
  if (['failed', 'delivery_unknown'].includes(status)) return 'danger'
  if (['blocked', 'draft'].includes(status)) return 'warning'
  if (['ready', 'sent', 'approved'].includes(status)) return 'success'
  return 'neutral'
}
export const sessionLabels: Record<Session['status'], string> = { active: '运行中', paused: '已暂停 · 人工接管', ended: '本地已结束' }

export function jobGuard(job: Job, product: Product | undefined, persona: Persona | null, session: Session | undefined, now = Date.now()): string {
  if (job.expires_at && Date.parse(job.expires_at) <= now) return '任务已过截止时间，请重新生成并审核。'
  if (!session || session.status !== 'active') return '场次未运行，不能继续审批或派发。'
  if (session.epoch !== job.epoch) return '任务属于接管前的旧批次，请重新创建草稿。'
  if (!product || !product.active) return '商品已停用或不存在，请重新选择商品。'
  if (expired(product, now)) return '商品资料已过有效期，请更新资料并重新创建草稿。'
  if (product.version !== job.product_version) return '商品资料已更新，这份旧任务不能继续执行。'
  if (!persona || persona.version !== job.persona_version) return '人格版本已更新，请按新版本创建草稿。'
  return ''
}

export function jobActions(job: Job, guard: string) {
  const fresh = !guard
  return {
    approve: fresh && job.status === 'draft',
    synthesize: fresh && job.status === 'approved',
    send: fresh && job.status === 'ready',
    audio: ['ready', 'sent', 'delivery_unknown'].includes(job.status),
    cancel: ['draft', 'blocked', 'approved', 'queued', 'synthesizing', 'ready', 'failed'].includes(job.status),
  }
}

export function defaultQualityChecks(): QualityCheck[] {
  return [
    ['source', '素材授权、闭嘴状态与清晰度已核对'],
    ['identity', '嘴周、肤色、胡须与人物身份无明显改变'],
    ['lip_sync', '开口、停顿、闭口与实际发音匹配'],
    ['continuity', '无明显接缝、嘴角撕裂或连续闪烁'],
    ['transport', '已在真实接收端测量传输音画偏差'],
    ['duration', '已完成计划负载下的持续运行测试'],
    ['takeover', '接管后旧批次无新增本地输出'],
  ].map(([key, label]) => ({ key: key!, label: label!, passed: false, notes: '' }))
}
