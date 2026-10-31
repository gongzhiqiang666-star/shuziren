import { waitForIceGathering } from '../rtc'

export interface ReceiverState {
  peerState: RTCPeerConnectionState | 'idle'
  audioReady: boolean
  videoReady: boolean
  playbackReady: boolean
  connected: boolean
  error: string
}
export type Negotiate = (offer: RTCSessionDescriptionInit, signal: AbortSignal) => Promise<RTCSessionDescriptionInit>

/** Owns one receive-only Peer. It never reads operator credentials or API routes. */
export class MediaReceiver {
  private peer: RTCPeerConnection | null = null
  private stream: MediaStream | null = null
  private abort: AbortController | null = null
  private generation = 0
  private playSucceeded = false
  private playError = ''
  private watchdog: number | undefined
  private removers: (() => void)[] = []
  private state: ReceiverState = { peerState: 'idle', audioReady: false, videoReady: false, playbackReady: false, connected: false, error: '' }

  constructor(private video: HTMLVideoElement, private onState: (state: ReceiverState) => void) {}

  get current() { return { ...this.state } }

  private report() {
    const tracks = this.stream?.getTracks() ?? []
    const audioReady = tracks.some(t => t.kind === 'audio' && t.readyState === 'live' && !t.muted)
    const videoReady = tracks.some(t => t.kind === 'video' && t.readyState === 'live' && !t.muted)
    const playbackReady = this.playSucceeded && !this.video.paused && !this.video.ended && !this.video.muted && this.video.volume > 0 && this.video.readyState >= 2
    const peerState = this.peer?.connectionState ?? 'idle'
    this.state = { peerState, audioReady, videoReady, playbackReady, connected: peerState === 'connected' && audioReady && videoReady && playbackReady, error: this.playError }
    this.onState({ ...this.state })
  }

  async play() {
    const generation = this.generation
    try {
      this.video.muted = false
      this.video.volume = 1
      await this.video.play()
      if (generation !== this.generation) return
      this.playSucceeded = true
      this.playError = ''
    } catch {
      if (generation !== this.generation) return
      this.playSucceeded = false
      this.playError = '浏览器阻止有声播放。请点击启用音视频；在播放成功前，输出不会被标记为在线。'
    }
    this.report()
  }

  async connect(negotiate: Negotiate) {
    this.stop()
    const generation = this.generation
    if (typeof RTCPeerConnection === 'undefined') throw new Error('当前浏览器不支持 WebRTC。')
    const peer = new RTCPeerConnection({ iceServers: [] })
    this.peer = peer
    this.abort = new AbortController()
    this.stream = new MediaStream()
    this.video.srcObject = this.stream
    this.video.muted = false
    this.video.volume = 1
    const listen = (target: EventTarget, name: string, callback: EventListener) => {
      target.addEventListener(name, callback)
      this.removers.push(() => target.removeEventListener(name, callback))
    }
    for (const name of ['playing', 'pause', 'ended', 'volumechange', 'loadeddata', 'timeupdate']) listen(this.video, name, () => this.report())
    listen(this.video, 'canplay', () => { if (!this.playSucceeded && !this.playError) void this.play() })
    peer.addTransceiver('audio', { direction: 'recvonly' })
    peer.addTransceiver('video', { direction: 'recvonly' })
    peer.ontrack = event => {
      if (generation !== this.generation || !this.stream) return
      if (!this.stream.getTracks().some(t => t.id === event.track.id)) this.stream.addTrack(event.track)
      for (const name of ['unmute', 'mute', 'ended']) listen(event.track, name, () => this.report())
      this.report()
      if (!this.playError) void this.play()
    }
    peer.onconnectionstatechange = () => {
      if (generation !== this.generation) return
      if (peer.connectionState === 'failed') this.playError = 'WebRTC 连接失败，请检查媒体服务与网络可达性。'
      if (peer.connectionState === 'disconnected') this.playError = '媒体连接已中断，正在等待重新连接。'
      if (peer.connectionState === 'connected' && !this.playError.includes('阻止')) this.playError = ''
      this.report()
    }
    try {
      await peer.setLocalDescription(await peer.createOffer())
      await waitForIceGathering(peer)
      if (generation !== this.generation) return
      if (!peer.localDescription?.sdp) throw new Error('浏览器没有生成有效的媒体协商信息。')
      const answer = await negotiate({ type: peer.localDescription.type, sdp: peer.localDescription.sdp }, this.abort.signal)
      if (generation !== this.generation) return
      if (answer.type !== 'answer' || !answer.sdp) throw new Error('媒体服务返回了无效的应答。')
      await peer.setRemoteDescription(answer)
      if (generation !== this.generation) return
      this.report()
      this.watchdog = window.setTimeout(() => {
        if (generation !== this.generation || this.state.connected) return
        if (!this.playError) this.playError = '协商完成，但尚未收到可播放的完整音视频，请检查媒体输出。'
        this.report()
      }, 25_000)
    } catch (error) {
      if (generation !== this.generation) return
      this.stop()
      throw error
    }
  }

  stop() {
    this.generation++
    this.abort?.abort(); this.abort = null
    if (this.watchdog !== undefined) window.clearTimeout(this.watchdog)
    this.watchdog = undefined
    this.removers.splice(0).forEach(remove => remove())
    if (this.peer) { this.peer.ontrack = null; this.peer.onconnectionstatechange = null; this.peer.close(); this.peer = null }
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null
    this.video.srcObject = null
    this.playSucceeded = false; this.playError = ''
    this.report()
  }
}
