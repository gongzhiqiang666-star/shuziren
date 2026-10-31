export function waitForIceGathering(peer: RTCPeerConnection, timeout = 10_000): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve, reject) => {
    const clear = () => { window.clearTimeout(timer); peer.removeEventListener('icegatheringstatechange', changed) }
    const changed = () => {
      if (peer.iceGatheringState === 'complete') { clear(); resolve() }
      else if (peer.signalingState === 'closed') { clear(); reject(new Error('预览连接已关闭。')) }
    }
    const timer = window.setTimeout(() => { clear(); reject(new Error('本地媒体网络协商超时，请检查 LiveTalking 与浏览器之间的网络连接。')) }, timeout)
    peer.addEventListener('icegatheringstatechange', changed)
  })
}
