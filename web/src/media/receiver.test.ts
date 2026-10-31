import { afterEach, expect, it, vi } from 'vitest'
import { MediaReceiver } from './receiver'
class Track extends EventTarget { id = Math.random().toString(); muted = false; readyState = 'live'; stop = vi.fn(() => { this.readyState = 'ended' }); constructor(public kind: string) { super() } }
class Stream { tracks: Track[] = []; getTracks() { return this.tracks }; addTrack(track: Track) { this.tracks.push(track) } }
class Peer extends EventTarget {
  iceGatheringState = 'complete'; connectionState = 'new'; ontrack: ((event: { track: Track }) => void) | null = null; onconnectionstatechange: (() => void) | null = null
  localDescription = { type: 'offer', sdp: 'offer-sdp' }; addTransceiver = vi.fn(); createOffer = vi.fn().mockResolvedValue(this.localDescription); setLocalDescription = vi.fn().mockResolvedValue(undefined); setRemoteDescription = vi.fn().mockResolvedValue(undefined); close = vi.fn()
}
const receivers: MediaReceiver[] = []
afterEach(() => { receivers.splice(0).forEach(receiver => receiver.stop()); vi.unstubAllGlobals(); vi.restoreAllMocks() })
function setup(playBlocked = false) {
  const peer = new Peer(); vi.stubGlobal('RTCPeerConnection', vi.fn(function () { return peer })); vi.stubGlobal('MediaStream', Stream)
  const video = document.createElement('video'); Object.defineProperty(video, 'readyState', { value: 2 }); Object.defineProperty(video, 'paused', { value: false })
  const play = vi.spyOn(video, 'play'); if (playBlocked) play.mockRejectedValue(new Error('NotAllowed')); else play.mockResolvedValue(undefined)
  const receiver = new MediaReceiver(video, vi.fn()); receivers.push(receiver)
  return { peer, video, receiver, play }
}
it('真实 Peer 连接仍不足以就绪，必须有存活音视频轨道及有声播放', async () => {
  const { peer, receiver, video } = setup()
  await receiver.connect(async () => ({ type: 'answer', sdp: 'answer-sdp' }))
  peer.connectionState = 'connected'; peer.onconnectionstatechange?.()
  expect(receiver.current.connected).toBe(false)
  peer.ontrack?.({ track: new Track('audio') }); peer.ontrack?.({ track: new Track('video') }); await Promise.resolve(); await Promise.resolve()
  expect(receiver.current.connected).toBe(true)
  video.muted = true; video.dispatchEvent(new Event('volumechange'))
  expect(receiver.current.connected).toBe(false)
})
it('浏览器拒绝播放时不报告在线，点击后成功播放才恢复', async () => {
  const { peer, receiver, play } = setup(true)
  await receiver.connect(async () => ({ type: 'answer', sdp: 'answer-sdp' }))
  peer.connectionState = 'connected'; peer.onconnectionstatechange?.(); peer.ontrack?.({ track: new Track('audio') }); peer.ontrack?.({ track: new Track('video') }); await Promise.resolve(); await Promise.resolve()
  expect(receiver.current.playbackReady).toBe(false); expect(receiver.current.error).toContain('阻止')
  play.mockResolvedValue(undefined); await receiver.play()
  expect(receiver.current.connected).toBe(true)
  receiver.stop(); expect(peer.close).toHaveBeenCalled(); expect(receiver.current.connected).toBe(false)
})
