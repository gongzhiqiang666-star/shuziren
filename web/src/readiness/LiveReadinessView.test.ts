import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { flushUI, render } from '../testHarness'
import LiveReadinessView from './LiveReadinessView.vue'
import type { ReadinessRun } from './types'

afterEach(() => vi.unstubAllGlobals())
const blocked = (name: string) => ({ name, status: 'blocked', evidence: { reason: 'not_run' }, note: '', version: 1, updated_at: '' })
const run: ReadinessRun = { id: 'r1', shop_id: 's1', title: '首次验证', output_mode: 'virtual_camera', conclusion: 'incomplete', version: 1, created_at: '', updated_at: '', gates: ['install','generation','obs','platform','stability'].map(blocked) as ReadinessRun['gates'] }
const response = (data: unknown) => new Response(JSON.stringify({ data }))

it('shows fixed external command and never offers process control', async () => {
  const fetcher = vi.fn().mockResolvedValue(response([run]))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(LiveReadinessView, { api, shopId: 's1', notify: vi.fn() })
  await flushUI()
  expect(view.root.textContent).toContain('check-live-readiness.ps1')
  expect(view.root.textContent).toContain('请在外部终端执行')
  expect(view.root.textContent).not.toContain('启动 TTS')
  expect(fetcher.mock.calls.every(call => !/(execute|start|stop|install|upload)/.test(String(call[0])))).toBe(true)
  view.unmount()
})

it('creates a run through the record-only API', async () => {
  const fetcher = vi.fn().mockImplementation((_url: string, init?: RequestInit) => response(init?.method === 'POST' ? run : []))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(LiveReadinessView, { api, shopId: 's1', notify: vi.fn() })
  await flushUI()
  const input = view.root.querySelector<HTMLInputElement>('input[name="readiness-title"]')!
  input.value = '首次验证'; input.dispatchEvent(new Event('input', { bubbles: true }))
  await view.click('form button[type="submit"]')
  expect(fetcher.mock.calls.some(call => call[0] === '/api/v1/live-readiness/runs' && call[1]?.method === 'POST')).toBe(true)
  view.unmount()
})
