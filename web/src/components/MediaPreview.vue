<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { waitForIceGathering } from '../rtc'
import type { MediaAnswer, Session } from '../types'
import Icon from './Icon.vue'

const props = defineProps<{ api: ApiClient; shopId: string; session: Session | undefined; configured: boolean }>()
const emit = defineEmits<{ connected: []; error: [message: string]; 'connection-state': [connected: boolean] }>()
const video = ref<HTMLVideoElement>()
const state = ref<'idle' | 'connecting' | 'connected' | 'disconnected' | 'failed'>('idle')
const muted = ref(true)
const error = ref('')
let peer: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let generation = 0
let watchdog: number | undefined
const canConnect = computed(() => props.configured && props.session?.status === 'active' && state.value !== 'connecting')
const stateText = computed(() => ({ idle: '尚未连接', connecting: '正在连接', connected: '预览已连接', disconnected: '连接已中断', failed: '连接失败' })[state.value])

function teardown() {
  generation++
  emit('connection-state', false)
  if (watchdog !== undefined) window.clearTimeout(watchdog)
  watchdog = undefined
  if (peer) { peer.ontrack = null; peer.onconnectionstatechange = null; peer.close(); peer = null }
  stream?.getTracks().forEach(track => track.stop())
  stream = null
  if (video.value) video.value.srcObject = null
}
function disconnect() { teardown(); state.value = 'idle'; error.value = '' }
function fail(message: string) { teardown(); state.value = 'failed'; error.value = message; emit('error', message) }
async function connect() {
  const session = props.session
  if (!session || !canConnect.value) return
  teardown(); error.value = ''; state.value = 'connecting'; muted.value = true
  const attempt = generation
  if (typeof RTCPeerConnection === 'undefined') { fail('当前浏览器不支持 WebRTC，请使用支持的桌面浏览器。'); return }
  try {
    const connection = new RTCPeerConnection({ iceServers: [] })
    peer = connection
    stream = new MediaStream()
    connection.addTransceiver('audio', { direction: 'recvonly' })
    connection.addTransceiver('video', { direction: 'recvonly' })
    connection.ontrack = event => {
      if (attempt !== generation || !stream) return
      if (!stream.getTracks().some(track => track.id === event.track.id)) stream.addTrack(event.track)
      if (video.value) {
        video.value.srcObject = stream
        void video.value.play().catch(() => { /* The controls allow an explicit user gesture. */ })
      }
    }
    connection.onconnectionstatechange = () => {
      if (attempt !== generation) return
      if (connection.connectionState === 'connected') {
        if (watchdog !== undefined) window.clearTimeout(watchdog)
        state.value = 'connected'; error.value = ''; emit('connection-state', true)
      } else if (connection.connectionState === 'failed') fail('媒体连接失败，请检查 LiveTalking 地址、端口与本机网络，再重新连接。')
      else if (connection.connectionState === 'disconnected') { state.value = 'disconnected'; emit('connection-state', false); error.value = '媒体连接中断。检查服务和网络后重新连接。' }
    }
    await connection.setLocalDescription(await connection.createOffer())
    await waitForIceGathering(connection)
    if (attempt !== generation) return
    const offer = connection.localDescription
    if (!offer?.sdp) throw new Error('浏览器未生成有效的媒体协商信息。')
    const answer = await props.api.request<MediaAnswer>('/sessions/' + session.id + '/media/offer', { method: 'POST', body: { shop_id: props.shopId, sdp: offer.sdp, type: offer.type }, timeout: 100_000 })
    if (attempt !== generation) return
    if (!answer.sdp || answer.type !== 'answer' || typeof answer.sessionid !== 'string' || !answer.sessionid) throw new Error('媒体服务返回了无效的会话信息。')
    await connection.setRemoteDescription({ sdp: answer.sdp, type: 'answer' })
    emit('connected')
    if (connection.connectionState !== 'connected') watchdog = window.setTimeout(() => { if (attempt === generation && state.value !== 'connected') fail('协商完成，但未能建立媒体连接。请检查 LiveTalking 的 ICE 地址与浏览器可达性。') }, 20_000)
  } catch (cause) { if (attempt === generation) fail(errorMessage(cause)) }
}
async function enableSound() {
  muted.value = !muted.value
  if (video.value) { video.value.muted = muted.value; try { await video.value.play() } catch { error.value = '浏览器阻止自动播放，请使用视频控件点击播放。' } }
}
watch([() => props.shopId, () => props.session?.id], disconnect)
onBeforeUnmount(teardown)
</script>
<template>
  <section class="panel preview-panel">
    <div class="panel-title"><h2><Icon name="studio" :size="19" />媒体预览</h2><span class="badge" :class="state === 'connected' ? 'success' : state === 'failed' ? 'danger' : 'neutral'"><span class="status-dot" />{{ stateText }}</span></div>
    <div class="preview-stage">
      <video ref="video" autoplay playsinline controls :muted="muted" :class="{ visible: state === 'connected' || state === 'disconnected' }" aria-label="LiveTalking 实时音视频预览" />
      <div v-if="state !== 'connected' && state !== 'disconnected'" class="preview-placeholder"><div class="preview-symbol"><Icon name="wave" :size="38" /></div><h3>{{ state === 'connecting' ? '正在协商音视频连接' : '真实媒体，从这里接入' }}</h3><p>{{ !configured ? '尚未配置 LiveTalking。配置本地媒体服务后，再连接预览。' : !session ? '先创建或选择一个场次。' : session.status !== 'active' ? '请在运行中的场次连接媒体。' : '点击连接，接收 LiveTalking 的真实画面与声音。' }}</p></div>
      <span class="preview-corner">LOCAL PREVIEW</span>
    </div>
    <div v-if="error" class="preview-error" role="alert">{{ error }}</div>
    <div class="preview-controls"><button class="button secondary small" :disabled="!canConnect" @click="connect"><Icon name="studio" :size="16" />{{ state === 'connecting' ? '连接中…' : state === 'idle' ? '连接媒体' : '重新连接' }}</button><button v-if="state !== 'idle'" class="button ghost small" @click="disconnect">断开预览</button><button v-if="state === 'connected'" class="button ghost small sound-toggle" @click="enableSound"><Icon name="sound" :size="16" />{{ muted ? '开启声音' : '静音' }}</button></div>
    <p class="preview-note">默认静音。本版预览依赖当前页面，离开工作台或断开会关闭媒体连接；重新连接后才能派发。此操作不会结束淘宝直播。</p>
  </section>
</template>
