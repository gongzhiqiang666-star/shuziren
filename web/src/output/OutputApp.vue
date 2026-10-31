<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { MediaReceiver, type ReceiverState } from '../media/receiver'
import { OutputClient, OutputError, outputToken } from './scopedApi'
import type { OutputAnswer, OutputControlResult, OutputStatus } from './types'

const video = ref<HTMLVideoElement>()
const status = ref<OutputStatus | null>(null)
const media = ref<ReceiverState>({ peerState: 'idle', audioReady: false, videoReady: false, playbackReady: false, connected: false, error: '' })
const message = ref('正在核验输出授权…')
const terminal = ref(false)
const connecting = ref(false)
const exhausted = ref(false)
const viewport = ref({ width: window.innerWidth, height: window.innerHeight })
const token = outputToken(window.location.hash)
const client = new OutputClient(token)
const receiverId = window.crypto.randomUUID()
const debug = new URLSearchParams(window.location.hash.slice(1)).get('debug') === '1'
let receiver: MediaReceiver | null = null
let leaseId: string | null = null
let interval: number | undefined
let busy = false
let disposed = false
let attempts = 0
let retryAt = 0
const paused = computed(() => status.value?.session_status === 'paused')
const config = computed(() => status.value?.config ?? { width: 1280, height: 720, fit: 'contain' as const, background: '#000000' })
const stageStyle = computed(() => {
  const scale = Math.min(viewport.value.width / config.value.width, viewport.value.height / config.value.height)
  return { width: config.value.width + 'px', height: config.value.height + 'px', transform: 'translate(-50%, -50%) scale(' + scale + ')', background: paused.value || terminal.value ? '#000000' : /^#[0-9a-f]{6}$/i.test(config.value.background) ? config.value.background : '#000000' }
})
function stopLocal() { receiver?.stop(); leaseId = null; connecting.value = false }
function stopTerminal(text: string) { terminal.value = true; message.value = text; stopLocal(); if (interval !== undefined) window.clearInterval(interval) }
function backoff(text: string) { message.value = text; attempts++; retryAt = Date.now() + Math.min(30_000, 2000 * 2 ** Math.min(attempts - 1, 4)); exhausted.value = attempts >= 6 }
function applyStatus(next: OutputStatus) {
  status.value = next
  if (next.session_status === 'ended') { stopTerminal('本地场次已结束，输出已停止。'); return }
  if (!next.enabled) { stopTerminal('输出授权已撤销，请在运营台重新签发。'); return }
  if (next.session_status === 'paused') { stopLocal(); message.value = '场次已暂停。请在运营台恢复后继续输出。'; attempts = 0; exhausted.value = false }
}
async function releaseCurrent(keepalive = false) {
  const oldLease = leaseId
  stopLocal()
  if (!oldLease) return
  const result = await client.request<OutputControlResult>('release', { body: { receiver_id: receiverId, lease_id: oldLease }, keepalive })
  if (!disposed) { applyStatus(result.output); if (result.media_stop_status === 'failed') message.value = '接收连接已关闭，但上游停止失败，请在媒体服务检查残留输出。' }
}
function handleFailure(cause: unknown) {
  if (disposed) return
  if (cause instanceof OutputError && cause.status === 401) { stopTerminal('输出授权已失效或本地场次已结束。请在运营台核对并重新签发。'); return }
  receiver?.stop(); leaseId = null; connecting.value = false
  backoff(cause instanceof Error ? cause.message : '输出连接失败。')
}
async function tick() {
  if (busy || disposed || terminal.value) return
  busy = true
  try {
    if (leaseId && receiver) {
      const actual = receiver.current
      const next = await client.request<OutputStatus>('heartbeat', { body: { receiver_id: receiverId, lease_id: leaseId, peer_state: actual.peerState === 'idle' ? 'closed' : actual.peerState, video_ready: actual.videoReady && !!video.value && video.value.readyState >= 2, audio_ready: actual.audioReady && actual.playbackReady } })
      if (disposed) return
      applyStatus(next)
      if (paused.value || terminal.value) return
      if (actual.connected) { attempts = 0; exhausted.value = false; message.value = '' }
      if (['failed', 'disconnected', 'closed', 'idle'].includes(actual.peerState)) { await releaseCurrent(); backoff(actual.error || '媒体已断开，正在退避重连。') }
      return
    }
    const next = await client.request<OutputStatus>('status', { receiverId })
    if (disposed) return
    applyStatus(next)
    if (paused.value || terminal.value) return
    if (next.lease_owned && next.lease_id) {
      leaseId = next.lease_id
      await releaseCurrent()
      retryAt = Date.now() + 2000
      return
    }
    if (next.state === 'negotiating' || next.state === 'connected') { message.value = '已有另一个输出页面占用此场次。请关闭该页面或 OBS 源后再试，不会自动抢占。'; return }
    if (exhausted.value || Date.now() < retryAt) return
    connecting.value = true; message.value = '正在建立真实音视频输出…'
    await receiver?.connect(async (offer, signal) => {
      const answer = await client.request<OutputAnswer>('offer', { body: { receiver_id: receiverId, sdp: offer.sdp, type: 'offer' }, signal })
      if (!answer.lease_id || !answer.sessionid) throw new Error('输出服务没有返回有效租约。')
      leaseId = answer.lease_id
      if (!disposed) applyStatus(answer.output)
      return { sdp: answer.sdp, type: answer.type }
    })
    connecting.value = false
  } catch (cause) { handleFailure(cause) } finally { busy = false }
}
async function retry() { if (terminal.value) return; exhausted.value = false; attempts = 0; retryAt = 0; try { await releaseCurrent() } catch (cause) { handleFailure(cause) } await tick() }
async function playReceiver() { await receiver?.play() }
function resize() { viewport.value = { width: window.innerWidth, height: window.innerHeight } }
function hashChanged() { if (outputToken(window.location.hash) !== token) window.location.reload() }
function leave() { disposed = true; if (interval !== undefined) window.clearInterval(interval); void releaseCurrent(true).catch(() => {}) }
onMounted(() => {
  if (!token) { stopTerminal('缺少输出授权。请在运营台生成独立输出链接，再添加到 OBS 浏览器源。'); return }
  if (!video.value) return
  receiver = new MediaReceiver(video.value, value => { media.value = value })
  interval = window.setInterval(() => void tick(), 3000)
  window.addEventListener('resize', resize)
  window.addEventListener('pagehide', leave)
  window.addEventListener('hashchange', hashChanged)
  void tick()
})
onBeforeUnmount(() => { leave(); window.removeEventListener('resize', resize); window.removeEventListener('pagehide', leave); window.removeEventListener('hashchange', hashChanged) })
</script>
<template>
  <main class="output-root" :style="{ background: stageStyle.background }">
    <div class="output-stage" :style="stageStyle"><video ref="video" autoplay playsinline :style="{ objectFit: config.fit }" aria-label="独立数字人音视频输出" /></div>
    <div class="output-sr" role="status">{{ paused ? '场次已暂停，画面已清空。' : message }}</div>
    <section v-if="!paused && (!media.connected || terminal)" class="output-notice" role="status"><div class="output-label">独立媒体输出</div><h1>{{ terminal ? '输出已停止' : connecting ? '正在连接' : exhausted ? '需要检查连接' : '等待媒体就绪' }}</h1><p>{{ media.error || message }}</p><button v-if="media.error.includes('阻止') && !terminal" @click="playReceiver">启用音视频播放</button><button v-else-if="!terminal && !connecting" @click="retry">重新连接</button><small>此页面仅接收媒体；不会登录淘宝或开始平台直播。</small></section>
    <div v-if="debug" class="output-debug">{{ paused ? 'paused' : media.peerState }} · 视频 {{ media.videoReady ? '就绪' : '等待' }} · 音频 {{ media.audioReady && media.playbackReady ? '就绪' : '等待' }} · 后端在线 {{ status?.online ? '是' : '否' }}</div>
  </main>
</template>
