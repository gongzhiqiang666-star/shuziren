import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { render } from '../testHarness'
import WorkbenchView from './WorkbenchView.vue'
import type { Job, Persona, Product, Session, SystemStatus } from '../types'

afterEach(() => vi.unstubAllGlobals())
const product: Product = { id: 'p', shop_id: 's', title: '茶杯', sku: 'CUP', description: '', specs: '', price_cents: 1990, stock: 5, active: true, version: 2, expires_at: null, updated_at: '' }
const persona: Persona = { shop_id: 's', name: '小禾', tone: '亲切', prompt: '', version: 3, updated_at: '' }
const session: Session = { id: 'live', shop_id: 's', title: '试播', status: 'active', epoch: 4, media_session_id: 'previous-peer-uuid', created_at: '', updated_at: '' }
const job: Job = { id: 'j', shop_id: 's', session_id: 'live', product_id: 'p', product_version: 2, persona_version: 3, epoch: 4, source: 'manual', question: '', text: '杯子十九元九角。', status: 'ready', reason: '', error_code: '', input_tokens: 0, output_tokens: 0, created_at: '', updated_at: '' }
const status: SystemStatus = { version: '0.1.0', storage: 'postgresql', deepseek: { configured: true, model: 'deepseek-flash' }, media: { tts_configured: true, live_configured: true }, taobao: { status: 'not_connected' }, retrieval: { mode: 'keyword' } }
function props(api: ApiClient) { return { api, shopId: 's', products: [product], persona, sessions: [session], jobs: [job], status, reload: vi.fn().mockResolvedValue(undefined), notify: vi.fn() } }

it('旧媒体会话编号存在但 Peer 未连接时，禁止派发音频', async () => {
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(WorkbenchView, props(api))
  await view.click('.job-table .button')
  const send = [...document.querySelectorAll<HTMLButtonElement>('.review-actions button')].find(button => button.textContent?.includes('发送到媒体'))
  expect(send?.disabled).toBe(true)
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('保留的媒体会话编号不代表连接仍然有效')
  view.unmount()
})

it('结束本地场次后仍明确展示媒体停止失败，要求手动停止输出', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { session: { ...session, status: 'ended', epoch: 5 }, media_stop_status: 'failed' } })))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(WorkbenchView, props(api))
  await view.click('.session-actions .ghost')
  await view.click('.dialog-panel .danger')
  expect(fetcher.mock.calls[0]![0]).toBe('/api/v1/sessions/live/end')
  const message = view.find('[role="alert"]').textContent
  expect(message).toContain('本地场次已结束')
  expect(message).toContain('媒体停止请求失败')
  expect(message).toContain('OBS 或媒体服务手动停止')
  view.unmount()
})
