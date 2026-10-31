import { parseMoneyToCents } from '../domain'

export function optionalAmount(value: string): number | null {
  if (!value.trim()) return null
  const amount = parseMoneyToCents(value)
  if (amount > 1_000_000_000_000) throw new Error('金额超出允许范围。')
  return amount
}
export function optionalRate(value: string): number | null {
  if (!value.trim()) return null
  if (!/^\d+(\.\d+)?$/.test(value.trim())) throw new Error('费率、功率与预算请输入非负数；留空表示未设置。')
  const number = Number(value)
  if (!Number.isFinite(number) || number > 10_000_000) throw new Error('费率、功率或预算超出允许范围。')
  return number
}
export function dateRange(start: string, end: string): { starts_at: string; ends_at: string } {
  const first = new Date(start), last = new Date(end)
  if (!start || !end || !Number.isFinite(first.getTime()) || !Number.isFinite(last.getTime()) || last.getTime() <= first.getTime()) throw new Error('请填写有效时间，结束时间必须晚于开始时间。')
  return { starts_at: first.toISOString(), ends_at: last.toISOString() }
}
export function validHash(value: string): boolean { return /^[0-9a-f]{64}$/.test(value) }
