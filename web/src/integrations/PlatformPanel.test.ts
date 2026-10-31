import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { flushUI, render } from '../testHarness'
import { clearActionLedger, getAttempt } from './actionLedger'
import PlatformPanel from './PlatformPanel.vue'
afterEach(() => { vi.unstubAllGlobals(); clearActionLedger() })
it('平台网络结果不明时保留固定 request_id 和参数，换页面后核对仍不换号', async () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError('network'))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('operator-secret')
  const props = { api, shopId: 'shop', products: [], sessions: [{ id: 'session', title: '试播', status: 'active' }], notify: vi.fn(), reload: vi.fn() }
  let view = render(PlatformPanel, props)
  await view.setValue('.platform-action-form input', '9007199254740993')
  await view.submit('.platform-action-form')
  await view.click('.dialog-panel .primary')
  const first = JSON.parse(fetcher.mock.calls[0]![1].body)
  expect(first.item_id).toBe('9007199254740993')
  expect(first.request_id).toMatch(/^[0-9a-f-]{36}$/)
  expect(getAttempt('shop')?.requestId).toBe(first.request_id)
  expect(view.root.textContent).toContain('尚未取得明确结果')
  view.unmount(); view = render(PlatformPanel, props); await flushUI()
  expect(view.root.querySelector('.platform-action-form')).toBeNull()
  await view.click('.action-result > .secondary')
  expect(JSON.parse(fetcher.mock.calls[1]![1].body)).toEqual(first)
  const nextButton = view.find<HTMLButtonElement>('.action-result > .ghost')
  expect(nextButton.disabled).toBe(true)
  view.unmount()
})
