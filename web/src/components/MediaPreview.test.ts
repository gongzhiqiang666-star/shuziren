import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import type { Session } from '../types'
import { flushUI, render } from '../testHarness'
import MediaPreview from './MediaPreview.vue'

afterEach(() => vi.unstubAllGlobals())
const session: Session = { id: 'session-1', shop_id: 'shop-1', title: '测试场次', status: 'active', epoch: 1, media_session_id: null, created_at: '', updated_at: '' }
function mockRTC() {
  const peer = {
    addTransceiver: vi.fn(), createOffer: vi.fn().mockResolvedValue({ type: 'offer', sdp: 'offer-sdp' }),
    setLocalDescription: vi.fn().mockResolvedValue(undefined), localDescription: { type: 'offer', sdp: 'offer-sdp' },
    setRemoteDescription: vi.fn().mockResolvedValue(undefined), iceGatheringState: 'complete', connectionState: 'new',
    onconnectionstatechange: null as (() => void) | null, ontrack: null, close: vi.fn(),
  }
  vi.stubGlobal('RTCPeerConnection', vi.fn(function () { return peer }))
  vi.stubGlobal('MediaStream', vi.fn(function () { return { getTracks: () => [], addTrack: vi.fn() } }))
  return peer
}
it('WebRTC 仅接收音视频，实际 connected 前不能标记连接成功', async () => {
  const peer = mockRTC()
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { type: 'answer', sdp: 'answer-sdp', sessionid: 'upstream-uuid' } })))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('private-token')
  const stateChanged = vi.fn()
  const view = render(MediaPreview, { api, shopId: 'shop-1', session, configured: true, onConnectionState: stateChanged })
  await view.click('.preview-controls .secondary')
  expect(peer.addTransceiver).toHaveBeenCalledWith('audio', { direction: 'recvonly' })
  expect(peer.addTransceiver).toHaveBeenCalledWith('video', { direction: 'recvonly' })
  expect(fetcher.mock.calls[0]![0]).toBe('/api/v1/sessions/session-1/media/offer')
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toEqual({ shop_id: 'shop-1', type: 'offer', sdp: 'offer-sdp' })
  expect(peer.setRemoteDescription).toHaveBeenCalledWith({ type: 'answer', sdp: 'answer-sdp' })
  expect(view.find('.badge').textContent).toBe('正在连接')
  expect(stateChanged).toHaveBeenLastCalledWith(false)
  peer.connectionState = 'connected'; peer.onconnectionstatechange?.(); await flushUI()
  expect(view.find('.badge').textContent).toBe('预览已连接')
  expect(stateChanged).toHaveBeenLastCalledWith(true)
  await view.updateProps({ session: { ...session, media_session_id: 'new-upstream-uuid' } })
  expect(peer.close).not.toHaveBeenCalled()
  expect(view.find('.badge').textContent).toBe('预览已连接')
  await view.click('.preview-controls .ghost')
  expect(stateChanged).toHaveBeenLastCalledWith(false)
  expect(peer.close).toHaveBeenCalled()
  view.unmount()
})
it('协商失败时关闭连接并展示错误，不显示假画面或连接成功', async () => {
  const peer = mockRTC()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'MEDIA_UNAVAILABLE', message: 'LiveTalking 服务不可用。' } }), { status: 503 })))
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(MediaPreview, { api, shopId: 'shop-1', session, configured: true })
  await view.click('.preview-controls .secondary')
  expect(view.find('[role="alert"]').textContent).toContain('LiveTalking 服务不可用')
  expect(view.find('.badge').textContent).toBe('连接失败')
  expect(peer.close).toHaveBeenCalled()
  expect(view.find('video').classList.contains('visible')).toBe(false)
  view.unmount()
})
