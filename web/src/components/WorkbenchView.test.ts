import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { render } from '../testHarness'
import WorkbenchView from './WorkbenchView.vue'
import type { Job, Persona, Product, Session, SystemStatus } from '../types'
import { flushUI } from '../testHarness'
import type { OutputStatus } from '../output/types'

afterEach(() => vi.unstubAllGlobals())
const product: Product = { id: 'p', shop_id: 's', title: '茶杯', sku: 'CUP', description: '', specs: '', price_cents: 1990, stock: 5, active: true, version: 2, expires_at: null, updated_at: '' }
const persona: Persona = { shop_id: 's', name: '小禾', tone: '亲切', prompt: '', version: 3, updated_at: '' }
const session: Session = { id: 'live', shop_id: 's', title: '试播', status: 'active', epoch: 4, media_session_id: 'previous-peer-uuid', created_at: '', updated_at: '' }
const job: Job = { id: 'j', shop_id: 's', session_id: 'live', product_id: 'p', product_version: 2, persona_version: 3, epoch: 4, source: 'manual', question: '', text: '杯子十九元九角。', status: 'ready', reason: '', error_code: '', input_tokens: 0, output_tokens: 0, created_at: '', updated_at: '' }
const status: SystemStatus = { version: '0.1.0', storage: 'postgresql', deepseek: { configured: true, model: 'deepseek-flash' }, media: { tts_configured: true, live_configured: true }, taobao: { status: 'not_connected' }, retrieval: { mode: 'keyword' } }
function props(api: ApiClient) { return { api, shopId: 's', products: [product], persona, sessions: [session], jobs: [job], status, reload: vi.fn().mockResolvedValue(undefined), notify: vi.fn() } }
const output: OutputStatus = { session_id: 'live', enabled: false, generation: 0, session_status: 'active', epoch: 4, config: { width: 1280, height: 720, fit: 'contain', background: '#000000' }, state: 'disabled', online: false, peer_state: '', video_ready: false, audio_ready: false, last_heartbeat_at: null, lease_expires_at: null, lease_owned: false, lease_id: null, heartbeat_interval_ms: 3000, lease_ttl_ms: 15000 }
function response(data: unknown) { return new Response(JSON.stringify({ data })) }

it('旧媒体会话编号存在但 Peer 未连接时，禁止派发音频', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => response(output)))
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(WorkbenchView, props(api))
  await view.click('.job-table .button')
  const send = [...document.querySelectorAll<HTMLButtonElement>('.review-actions button')].find(button => button.textContent?.includes('发送到媒体'))
  expect(send?.disabled).toBe(true)
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('保留的媒体会话编号不代表连接仍然有效')
  view.unmount()
})

it('结束本地场次后仍明确展示媒体停止失败，要求手动停止输出', async () => {
  const fetcher = vi.fn().mockImplementation((url: string) => response(url.includes('/output') ? output : { session: { ...session, status: 'ended', epoch: 5 }, media_stop_status: 'failed' }))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(WorkbenchView, props(api))
  await view.click('.session-actions .ghost')
  await view.click('.dialog-panel .danger')
  expect(fetcher.mock.calls.some(call => call[0] === '/api/v1/sessions/live/end')).toBe(true)
  const message = view.find('[role="alert"]').textContent
  expect(message).toContain('本地场次已结束')
  expect(message).toContain('媒体停止请求失败')
  expect(message).toContain('OBS 或媒体服务手动停止')
  view.unmount()
})

it('独立输出启用时不创建管理预览，只有服务端在线状态允许人工派发', async () => {
  const fetcher = vi.fn().mockImplementation(() => response({ ...output, enabled: true, state: 'connected', online: true, audio_ready: true, video_ready: true }))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(WorkbenchView, props(api)); await flushUI()
  expect(view.root.querySelector('.preview-controls')).toBeNull()
  expect(view.root.textContent).toContain('画面由独立输出端承载')
  await view.click('.job-table .button')
  const send = [...document.querySelectorAll<HTMLButtonElement>('.review-actions button')].find(button => button.textContent?.includes('发送到媒体'))
  expect(send?.disabled).toBe(false)
  expect(fetcher.mock.calls.every(call => !String(call[0]).includes('/media/offer'))).toBe(true)
  view.unmount()
  expect(fetcher.mock.calls.every(call => !String(call[0]).includes('/revoke') && !String(call[0]).includes('/release'))).toBe(true)
})
