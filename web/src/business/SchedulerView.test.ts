import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { flushUI, render } from '../testHarness'
import SchedulerView from './SchedulerView.vue'
afterEach(() => vi.unstubAllGlobals())
it('轮询返回同一任务的新对象时保留正在编辑的优先级，再提交实际输入', async () => {
  const job = { id: 'j', shop_id: 's', session_id: 'session', text: '已批准的话术', status: 'approved', priority: 50, expires_at: null }
  const usage = { limits: { requests_per_minute: 10, daily_request_limit: 0, daily_token_limit: 0, version: 0, global_max_concurrent: 1, request_reservation_tokens: 100000 }, date_utc: '2026-10-31', requests_today: 0, charged_tokens_today: 0, unknown_requests_today: 0, pending_requests_today: 0, enforcement: '本地规则' }
  const fetcher = vi.fn().mockImplementation((url: string) => new Response(JSON.stringify({ data: url.includes('generation/usage') ? usage : url.includes('dispatch-policy') ? { ...job, priority: 90 } : [] })))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('operator')
  const view = render(SchedulerView, { api, shopId: 's', jobs: [job], sessions: [{ id: 'session', title: '测试场次' }], notify: vi.fn(), reload: vi.fn().mockResolvedValue(undefined) })
  await flushUI(); await view.setValue('input[type="number"]', '90')
  await view.updateProps({ jobs: [{ ...job }] })
  expect(view.find<HTMLInputElement>('input[type="number"]').value).toBe('90')
  await view.submit('form')
  const call = fetcher.mock.calls.find(item => String(item[0]).includes('dispatch-policy'))
  expect(call).toBeDefined(); expect(JSON.parse(call![1].body).priority).toBe(90)
  view.unmount()
})
