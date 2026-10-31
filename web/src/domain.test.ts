import { describe, expect, it } from 'vitest'
import { defaultQualityChecks, expired, jobActions, jobGuard, parseMoneyToCents } from './domain'
import type { Job, Persona, Product, Session } from './types'

const product: Product = { id: 'p', shop_id: 's', title: '茶杯', sku: 'CUP', description: '', specs: '', price_cents: 1990, stock: 5, active: true, version: 2, expires_at: null, updated_at: '' }
const persona: Persona = { shop_id: 's', name: '小禾', tone: '', prompt: '', version: 3, updated_at: '' }
const session: Session = { id: 'live', shop_id: 's', title: '试播', status: 'active', epoch: 4, media_session_id: null, created_at: '', updated_at: '' }
const job: Job = { id: 'j', shop_id: 's', session_id: 'live', product_id: 'p', product_version: 2, persona_version: 3, epoch: 4, source: 'manual', question: '', text: '杯子十九元九角。', status: 'draft', reason: '', error_code: '', input_tokens: 0, output_tokens: 0, created_at: '', updated_at: '' }

describe('精确商品金额', () => {
  it('精确转换小数，不因浮点运算多出或缺少一分', () => {
    expect(parseMoneyToCents('19.90')).toBe(1990)
    expect(parseMoneyToCents('1.01')).toBe(101)
    expect(parseMoneyToCents('0.29')).toBe(29)
    expect(parseMoneyToCents('0')).toBe(0)
    expect(parseMoneyToCents(' 12.5 ')).toBe(1250)
  })
  it.each(['', '-1', '1.001', '1e3', 'NaN', '1,200', '999999999999999999'])('拒绝无效或不安全金额 %s', value => {
    expect(() => parseMoneyToCents(value)).toThrow()
  })
})

describe('任务执行前的前端防误操作', () => {
  it('允许新鲜草稿进入人工审核，禁止跳过审批直接合成', () => {
    expect(jobGuard(job, product, persona, session)).toBe('')
    expect(jobActions(job, '')).toMatchObject({ approve: true, synthesize: false, send: false })
  })
  it('商品、人格或执行批次变更后禁用继续执行', () => {
    const reasons = [
      jobGuard(job, { ...product, version: 3 }, persona, session),
      jobGuard(job, product, { ...persona, version: 4 }, session),
      jobGuard(job, product, persona, { ...session, epoch: 5 }),
    ]
    for (const reason of reasons) {
      expect(reason).not.toBe('')
      expect(jobActions({ ...job, status: 'ready' }, reason).send).toBe(false)
    }
  })
  it('恰好到期时停止使用商品，暂停场次也不能派发', () => {
    const now = Date.parse('2026-11-01T00:00:00Z')
    const past = { ...product, expires_at: '2026-11-01T00:00:00Z' }
    expect(expired(past, now)).toBe(true)
    expect(jobGuard(job, past, persona, session, now)).toContain('有效期')
    expect(jobGuard(job, product, persona, { ...session, status: 'paused' })).toContain('未运行')
  })
  it('派发结果不明时不提供重新派发或取消的假象', () => {
    expect(jobActions({ ...job, status: 'delivery_unknown' }, '')).toEqual({ approve: false, synthesize: false, send: false, audio: true, cancel: false })
    expect(jobActions({ ...job, status: 'sending' }, '').send).toBe(false)
  })
})

it('默认核验清单没有任何伪造的通过结果', () => {
  const checks = defaultQualityChecks()
  expect(checks.length).toBeGreaterThan(4)
  expect(checks.every(check => !check.passed && !check.notes)).toBe(true)
  expect(new Set(checks.map(check => check.key)).size).toBe(checks.length)
})
