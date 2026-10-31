import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render } from '../testHarness'
import type { ReceiverState } from '../media/receiver'
import type { OutputStatus } from './types'
const shared = vi.hoisted(() => ({ receivers: [] as { current: ReceiverState; closeCount: number; update: (state: Partial<ReceiverState>) => void }[] }))
vi.mock('../media/receiver', () => ({ MediaReceiver: class {
  current: ReceiverState = { peerState: 'new', audioReady: false, videoReady: false, playbackReady: false, connected: false, error: '' }; closeCount = 0
  constructor(_video: HTMLVideoElement, private onState: (state: ReceiverState) => void) { shared.receivers.push(this) }
  update(value: Partial<ReceiverState>) { Object.assign(this.current, value); this.onState({ ...this.current }) }
  async connect(negotiate: (offer: RTCSessionDescriptionInit, signal: AbortSignal) => Promise<RTCSessionDescriptionInit>) { await negotiate({ type: 'offer', sdp: 'test-offer' }, new AbortController().signal) }
  stop() { this.closeCount++; this.update({ peerState: 'idle', connected: false, audioReady: false, videoReady: false, playbackReady: false }) }
  async play() { this.update({ playbackReady: true }) }
} }))
import OutputApp from './OutputApp.vue'
const base: OutputStatus = { session_id: 's', enabled: true, generation: 1, session_status: 'active', epoch: 1, config: { width: 1280, height: 720, fit: 'contain', background: '#123456' }, state: 'offline', online: false, peer_state: 'new', video_ready: false, audio_ready: false, last_heartbeat_at: null, lease_expires_at: null, lease_owned: false, lease_id: null, heartbeat_interval_ms: 3000, lease_ttl_ms: 15000 }
const views: ReturnType<typeof render>[] = []
function data(value: unknown) { return new Response(JSON.stringify({ data: value })) }
async function settle() { await vi.advanceTimersByTimeAsync(0) }
beforeEach(() => { vi.useFakeTimers(); shared.receivers.length = 0; window.history.replaceState({}, '', '/output#token=out_scoped') })
afterEach(async () => { views.splice(0).forEach(view => view.unmount()); await settle(); vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/') })
function mount() { const view = render(OutputApp); views.push(view); return view }
it('独立页只发窄权限 API，心跳就绪来自接收器而不是 offer 返回', async () => {
  const fetcher = vi.fn().mockImplementation((url: string) => data(url.endsWith('/offer') ? { type: 'answer', sdp: 'answer', sessionid: 'uuid', lease_id: 'lease', output: { ...base, state: 'negotiating', lease_owned: true, lease_id: 'lease' } } : url.endsWith('/release') ? { output: base, media_stop_status: 'sent' } : base))
  vi.stubGlobal('fetch', fetcher); const view = mount(); await settle()
  Object.defineProperty(view.find('video'), 'readyState', { value: 2 })
  await vi.advanceTimersByTimeAsync(3000)
  let heartbeats = fetcher.mock.calls.filter(call => String(call[0]).endsWith('/heartbeat'))
  expect(JSON.parse(heartbeats[0]![1].body)).toMatchObject({ peer_state: 'new', audio_ready: false, video_ready: false })
  shared.receivers[0]!.update({ peerState: 'connected', audioReady: true, videoReady: true, playbackReady: true, connected: true })
  await vi.advanceTimersByTimeAsync(3000)
  heartbeats = fetcher.mock.calls.filter(call => String(call[0]).endsWith('/heartbeat'))
  expect(JSON.parse(heartbeats.at(-1)![1].body)).toMatchObject({ peer_state: 'connected', audio_ready: true, video_ready: true })
  expect(fetcher.mock.calls.every(call => String(call[0]).startsWith('/output-api/v1/'))).toBe(true)
  expect(fetcher.mock.calls.every(call => call[1].headers.Authorization === 'Bearer out_scoped')).toBe(true)
})
it('暂停关闭 Peer 并清空为黑色，恢复 active 后才重新协商', async () => {
  let paused = false
  const fetcher = vi.fn().mockImplementation((url: string) => data(url.endsWith('/offer') ? { type: 'answer', sdp: 'answer', sessionid: 'uuid', lease_id: 'lease', output: base } : url.endsWith('/release') ? { output: base, media_stop_status: 'sent' } : paused ? { ...base, session_status: 'paused', state: 'paused' } : base))
  vi.stubGlobal('fetch', fetcher); const view = mount(); await settle(); paused = true
  await vi.advanceTimersByTimeAsync(3000)
  expect(shared.receivers[0]!.closeCount).toBeGreaterThan(0)
  expect(view.find<HTMLElement>('.output-stage').style.background).toBe('rgb(0, 0, 0)')
  expect(view.root.querySelector('.output-notice')).toBeNull()
  const count = fetcher.mock.calls.filter(call => String(call[0]).endsWith('/offer')).length
  await vi.advanceTimersByTimeAsync(3000); expect(fetcher.mock.calls.filter(call => String(call[0]).endsWith('/offer')).length).toBe(count)
  paused = false; await vi.advanceTimersByTimeAsync(3000); expect(fetcher.mock.calls.filter(call => String(call[0]).endsWith('/offer')).length).toBe(count + 1)
})
it('其他接收端持有租约时不发 offer，401 授权失效后停止重连', async () => {
  let revoked = false
  const fetcher = vi.fn().mockImplementation(() => revoked ? new Response(JSON.stringify({ error: { code: 'output_unauthorized', message: '失效' } }), { status: 401 }) : data({ ...base, state: 'connected', online: true }))
  vi.stubGlobal('fetch', fetcher); const view = mount(); await settle()
  expect(fetcher.mock.calls.some(call => String(call[0]).endsWith('/offer'))).toBe(false)
  expect(view.root.textContent).toContain('不会自动抢占')
  revoked = true; await vi.advanceTimersByTimeAsync(3000)
  expect(view.root.textContent).toContain('授权已失效')
  const count = fetcher.mock.calls.length; await vi.advanceTimersByTimeAsync(12000); expect(fetcher.mock.calls.length).toBe(count)
})
it('丢失 offer 结果留下自己的租约时先释放，不创建并行上游', async () => {
  let released = false
  const fetcher = vi.fn().mockImplementation((url: string) => { if (url.endsWith('/release')) { released = true; return data({ output: base, media_stop_status: 'sent' }) }; return data({ ...base, state: 'negotiating', lease_owned: true, lease_id: 'orphan' }) })
  vi.stubGlobal('fetch', fetcher); mount(); await settle()
  expect(released).toBe(true); expect(fetcher.mock.calls.some(call => String(call[0]).endsWith('/offer'))).toBe(false)
  expect(JSON.parse(fetcher.mock.calls.find(call => String(call[0]).endsWith('/release'))![1].body).lease_id).toBe('orphan')
})
