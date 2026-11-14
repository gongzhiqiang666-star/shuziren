<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { AvatarRenderer } from './renderer'
import type { AvatarBackground, AvatarCapabilities, AvatarRenderMetrics } from './renderer'
import { AudioAnalyzer } from './analyze'
import { pcmToWav, prepareAudio, sha256 } from './audio'
import type { PreparedAudio } from './audio'
import { parseLipSyncTrack, sampleViseme } from './lipSync'
import type { LipSyncTrack, VisemeId } from './lipSync'

const stage = ref<HTMLDivElement | null>(null)
const audioElement = ref<HTMLAudioElement | null>(null)
const capabilities = ref<AvatarCapabilities | null>(null)
const metrics = ref<AvatarRenderMetrics | null>(null)
const modelBusy = ref(false)
const renderReady = ref(false)
const audioBusy = ref(false)
const modelError = ref('')
const audioError = ref('')
const notice = ref('')
const progress = ref(0)
const audioName = ref('')
const audioHash = ref('')
const audioURL = ref('')
const duration = ref(0)
const currentTime = ref(0)
const playing = ref(false)
const track = ref<LipSyncTrack | null>(null)
const trackMode = ref<'none' | 'acoustic' | 'imported'>('none')
const lipOffset = ref(0)
const lipStrength = ref(0.8)
const background = ref<AvatarBackground>('studio')
const idleMotion = ref(true)
const cleanView = ref(false)
const obsSourceMode = ref(false)
const microphoneRecording = ref(false)
const microphoneBusy = ref(false)
const recordingVideo = ref(false)
const videoBusy = ref(false)
const recordedVideoURL = ref('')
const recordedVideoName = ref('avatar3d-local-preview.webm')
const recordingError = ref('')
const followMainSession = ref(false)
const mainSessionStatus = ref<'detached' | 'idle' | 'preparing' | 'running' | 'stopped' | 'failed' | 'unavailable'>('detached')
const mainSessionId = ref('')
const mainSessionEpoch = ref<number | null>(null)
const mainSessionError = ref('')
const selectedViseme = ref<VisemeId | ''>('')
const visemeChoices: VisemeId[] = ['PP', 'FF', 'aa', 'E', 'ih', 'oh', 'ou', 'sil']
const mainSessionReady = computed(() => !followMainSession.value || mainSessionStatus.value === 'running')
const canPlay = computed(() => renderReady.value && !!capabilities.value?.hasUsableMouthRig && !!track.value && !!audioURL.value && !audioBusy.value && !modelBusy.value && !microphoneRecording.value && !microphoneBusy.value && mainSessionReady.value)
const trackLabel = computed(() => trackMode.value === 'acoustic' ? '自动口型 · 试验' : track.value?.binding === 'sha256-verified' ? '导入轨道 · 音频校验一致' : track.value ? '导入轨道 · 仅时长匹配' : '等待音频')
const timelinePercent = computed(() => duration.value ? currentTime.value / duration.value * 100 : 0)
let renderer: AvatarRenderer | null = null
const analyzer = new AudioAnalyzer()
let audioRevision = 0
let modelRevision = 0
let playRevision = 0
let trackRevision = 0
let videoRevision = 0
let microphoneRevision = 0
let playbackIntent = false
let modelFetch: AbortController | null = null
let disposed = false
let frame = 0
let rawTrack: unknown = null
let prepared: PreparedAudio | null = null
let audioContext: AudioContext | null = null
let audioSource: MediaElementAudioSourceNode | null = null
let audioDestination: MediaStreamAudioDestinationNode | null = null
let videoRecorder: MediaRecorder | null = null
let videoStream: MediaStream | null = null
let videoTimer: number | undefined
let microphoneRecorder: MediaRecorder | null = null
let microphoneStream: MediaStream | null = null
let microphoneTimer: number | undefined
let mainSessionTimer: number | undefined
let boundMainSession = ''

function message(error: unknown) { return error instanceof Error ? error.message : '操作失败，请重新尝试。' }
function time(value: number) { return `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, '0')}` }
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
function stopPlayback() {
  playRevision++; playbackIntent = false
  audioElement.value?.pause()
  if (audioElement.value) audioElement.value.currentTime = 0
  currentTime.value = 0; playing.value = false; selectedViseme.value = ''
  renderer?.setVisemes({})
}
function stopVideo() {
  videoRevision++
  if (videoTimer !== undefined) window.clearTimeout(videoTimer)
  videoTimer = undefined
  recordingVideo.value = false
  if (videoRecorder) {
    // A recorder becomes inactive before its final data/onstop events arrive.
    // Keep the next recording disabled until that session has released itself.
    videoBusy.value = true
    if (videoRecorder.state !== 'inactive') videoRecorder.stop()
  } else {
    videoStream?.getTracks().forEach(t => t.stop()); videoStream = null
    videoBusy.value = false
  }
}
function stopForMainSession(reason: string) {
  stopPlayback(); stopVideo(); cleanView.value = false
  mainSessionError.value = reason
}
async function pollMainSession() {
  if (disposed || !followMainSession.value) return
  try {
    const response = await fetch('/api/live/state', { credentials: 'same-origin', cache: 'no-store', redirect: 'error' })
    if (!response.ok) throw new Error('主场次状态不可用')
    const payload = await response.json() as { session?: Record<string, unknown> }
    const session = payload.session
    const status = session?.status
    if (!session || !['idle', 'preparing', 'running', 'stopped', 'failed'].includes(String(status))) throw new Error('主场次状态无效')
    const id = typeof session.id === 'string' ? session.id : ''
    const epoch = Number.isInteger(session.lifecycle_epoch) ? Number(session.lifecycle_epoch) : null
    const token = id && epoch !== null ? `${id}:${epoch}` : ''
    if (boundMainSession && token !== boundMainSession) stopForMainSession('主场次已切换，3D 播放和录制已停止。')
    if (status !== 'running' && boundMainSession) stopForMainSession('主场次已停止，3D 播放和录制已停止。')
    if (status === 'running' && token) {
      if (!boundMainSession || boundMainSession !== token) boundMainSession = token
      mainSessionError.value = ''
    }
    mainSessionStatus.value = status as typeof mainSessionStatus.value
    mainSessionId.value = id; mainSessionEpoch.value = epoch
  } catch (error) {
    mainSessionStatus.value = 'unavailable'; mainSessionError.value = message(error)
  } finally {
    if (!disposed && followMainSession.value) mainSessionTimer = window.setTimeout(pollMainSession, 500)
  }
}
function changeMainSessionBinding() {
  if (mainSessionTimer !== undefined) window.clearTimeout(mainSessionTimer)
  mainSessionTimer = undefined; boundMainSession = ''; mainSessionError.value = ''
  if (followMainSession.value) { mainSessionStatus.value = 'idle'; void pollMainSession() }
  else { mainSessionStatus.value = 'detached'; mainSessionId.value = ''; mainSessionEpoch.value = null }
}
function revokeAudio() {
  if (audioURL.value) URL.revokeObjectURL(audioURL.value)
  audioURL.value = ''
}
function beginModelLoad() {
  modelFetch?.abort(); modelFetch = null
  const revision = ++modelRevision
  stopPlayback(); stopVideo(); modelBusy.value = true; modelError.value = ''; capabilities.value = null; renderReady.value = false
  renderer?.clearModel()
  return revision
}
async function loadModel(file: File, revision = beginModelLoad()) {
  try {
    const result = await renderer!.loadGLB(file)
    if (!disposed && revision === modelRevision) { capabilities.value = result; renderReady.value = true }
  } catch (error) { if (!disposed && revision === modelRevision) modelError.value = message(error) }
  finally { if (!disposed && revision === modelRevision) modelBusy.value = false }
}
async function exampleModel() {
  if (!renderer || modelBusy.value) return
  const revision = beginModelLoad()
  const controller = new AbortController(); modelFetch = controller
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}avatar-assets/mpfb.glb`, { credentials: 'omit', redirect: 'error', signal: controller.signal })
    if (!response.ok) throw new Error('示例人物未准备。请运行 start-avatar3d 启动脚本，或选择你自己的单文件 GLB。')
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength !== 36815920 || await sha256(bytes) !== '63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c') {
      throw new Error('示例人物文件校验不符。请重新准备资源，或选择自己的 GLB。')
    }
    if (!disposed && revision === modelRevision) await loadModel(new File([bytes], 'CC0 写实人物示例.glb', { type: 'model/gltf-binary' }), revision)
  } catch (error) { if (!disposed && revision === modelRevision) modelError.value = message(error) }
  finally {
    if (modelFetch === controller) modelFetch = null
    if (!disposed && revision === modelRevision) modelBusy.value = false
  }
}
function chooseModel(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (file && renderer) void loadModel(file)
}
async function useAudio(file: File) {
  const revision = ++audioRevision
  trackRevision++
  analyzer.cancel(); stopPlayback(); stopVideo(); revokeAudio()
  track.value = null; rawTrack = null; prepared = null; trackMode.value = 'none'
  audioName.value = ''; audioHash.value = ''; duration.value = 0
  audioBusy.value = true; progress.value = 0; audioError.value = ''; notice.value = ''
  try {
    const next = await prepareAudio(file)
    if (disposed || revision !== audioRevision) return
    prepared = next; audioName.value = file.name; audioHash.value = next.sha256; duration.value = next.duration
    audioURL.value = URL.createObjectURL(file)
    const result = await analyzer.analyze(next, value => { if (revision === audioRevision) progress.value = value })
    if (disposed || revision !== audioRevision) return
    const validated = parseLipSyncTrack(result, { duration: next.duration, sha256: next.sha256 })
    rawTrack = result; track.value = validated; trackMode.value = 'acoustic'
    notice.value = '音频与口型已准备。自动口型用于首轮观察，中文精细发音需要实际检查。'
  } catch (error) { if (!disposed && revision === audioRevision) audioError.value = message(error) }
  finally { if (!disposed && revision === audioRevision) audioBusy.value = false }
}
function chooseAudio(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (file) void useAudio(file)
}
async function importTrack(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file || !prepared) return
  const audio = prepared
  const revision = audioRevision
  const request = ++trackRevision
  stopPlayback(); stopVideo(); audioError.value = ''
  audioBusy.value = true
  try {
    if (file.size > 2 * 1024 * 1024) throw new Error('嘴形轨道文件不能超过 2 MiB。')
    const data = await file.text()
    if (disposed || revision !== audioRevision || request !== trackRevision) return
    const validated = parseLipSyncTrack(data, { duration: audio.duration, sha256: audio.sha256 })
    rawTrack = JSON.parse(data); track.value = validated; trackMode.value = 'imported'
    notice.value = validated.binding === 'sha256-verified' ? '轨道已与这份音频的 SHA256 核对。仍需目测口型是否正确。' : 'Rhubarb 原生轨道没有音频指纹，只核对了时长。请确认它来自当前音频。'
  } catch (error) { if (!disposed && revision === audioRevision && request === trackRevision) audioError.value = message(error) }
  finally { if (!disposed && revision === audioRevision && request === trackRevision) audioBusy.value = false }
}
async function audioGraph() {
  if (!audioElement.value) throw new Error('音频播放器尚未就绪。')
  if (!audioContext) {
    audioContext = new AudioContext()
    audioSource = audioContext.createMediaElementSource(audioElement.value)
    audioDestination = audioContext.createMediaStreamDestination()
    audioSource.connect(audioContext.destination)
    audioSource.connect(audioDestination)
  }
  await audioContext.resume()
}
async function play() {
  if (!canPlay.value || !audioElement.value) return
  const revision = ++playRevision
  const audio = audioElement.value
  const sourceRevision = audioRevision
  playbackIntent = true
  audioError.value = ''; selectedViseme.value = ''
  try {
    await audioGraph()
    if (disposed || revision !== playRevision || sourceRevision !== audioRevision || !canPlay.value) return
    if (audio.ended) audio.currentTime = 0
    await audio.play()
    if (!disposed && revision === playRevision && sourceRevision === audioRevision) playing.value = !audio.paused
  } catch {
    if (!disposed && revision === playRevision && sourceRevision === audioRevision) {
      audioError.value = '浏览器未允许播放，请点击播放按钮重试，并检查输出设备。'; playing.value = false; playbackIntent = false
    }
  }
}
function pause() { playRevision++; playbackIntent = false; audioElement.value?.pause(); playing.value = false; renderer?.setVisemes({}) }
function seek(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  if (audioElement.value && Number.isFinite(value)) { audioElement.value.currentTime = Math.max(0, Math.min(duration.value, value)); currentTime.value = audioElement.value.currentTime }
}
function setPose(viseme: VisemeId) {
  pause(); selectedViseme.value = viseme
  renderer?.setVisemes(viseme === 'sil' ? {} : { [viseme]: Number(lipStrength.value) })
}
function setBackground() { renderer?.setBackground(background.value) }
function setMotion() { renderer?.setIdleMotion(idleMotion.value) }
function resetCamera() { renderer?.resetCamera() }
function saveAudio() { if (prepared) download(prepared.file, prepared.file.name) }
function audioPlayed() {
  if (disposed || !playbackIntent || !canPlay.value) { audioElement.value?.pause(); playing.value = false }
  else playing.value = true
}
function audioEnded() { playbackIntent = false; playing.value = false; stopVideo(); renderer?.setVisemes({}) }
function audioFailed() { audioError.value = '音频播放器无法读取当前文件，请重新导入。'; pause(); stopVideo() }
function key(event: KeyboardEvent) { if (event.key === 'Escape' && !obsSourceMode.value) cleanView.value = false }
function tick() {
  if (disposed) return
  const audio = audioElement.value
  if (audio) currentTime.value = audio.currentTime || 0
  if (audio && !audio.paused && !audio.ended && track.value) {
    const weights = sampleViseme(track.value, audio.currentTime + Number(lipOffset.value) / 1000)
    const strength = Number(lipStrength.value)
    renderer?.setVisemes(Object.fromEntries(Object.entries(weights).map(([k, value]) => [k, value * strength])))
  } else if (!selectedViseme.value) renderer?.setVisemes({})
  frame = requestAnimationFrame(tick)
}
function releaseMicrophone(stream = microphoneStream) {
  stream?.getTracks().forEach(t => t.stop())
  if (stream === microphoneStream) {
    microphoneStream = null
    if (microphoneTimer !== undefined) window.clearTimeout(microphoneTimer)
    microphoneTimer = undefined; microphoneRecording.value = false
  }
}
function stopMicrophone() {
  if (microphoneRecorder) {
    microphoneBusy.value = true
    if (microphoneRecorder.state !== 'inactive') microphoneRecorder.stop()
  }
  releaseMicrophone()
}
async function recordMicrophone() {
  if (microphoneRecording.value) { stopMicrophone(); return }
  if (disposed || microphoneBusy.value || audioBusy.value) return
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { audioError.value = '此浏览器不支持录音，请使用本地 WAV 文件。'; return }
  const revision = ++microphoneRevision
  const sourceRevision = audioRevision
  stopPlayback(); stopVideo(); microphoneBusy.value = true; audioError.value = ''
  let ownedStream: MediaStream | null = null
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    ownedStream = stream
    if (disposed || revision !== microphoneRevision || sourceRevision !== audioRevision) { releaseMicrophone(stream); return }
    microphoneStream = stream
    const recorder = new MediaRecorder(stream)
    microphoneRecorder = recorder
    const chunks: Blob[] = []; let size = 0; let failed = false
    recorder.ondataavailable = event => {
      size += event.data.size
      if (size <= 16 * 1024 * 1024) chunks.push(event.data)
      else { failed = true; if (!disposed && microphoneRecorder === recorder) { audioError.value = '录音达到大小限制，已停止。'; stopMicrophone() } }
    }
    recorder.onerror = () => {
      failed = true
      if (!disposed && microphoneRecorder === recorder) { audioError.value = '录音失败，请检查麦克风权限。'; stopMicrophone() }
      else releaseMicrophone(stream)
    }
    recorder.onstop = async () => {
      releaseMicrophone(stream)
      if (microphoneRecorder !== recorder) return
      microphoneRecorder = null
      if (disposed || revision !== microphoneRevision) return
      microphoneBusy.value = true
      try {
        if (failed || !chunks.length || size > 16 * 1024 * 1024 || sourceRevision !== audioRevision) return
        const decoder = new OfflineAudioContext(1, 1, 48000)
        const decoded = await decoder.decodeAudioData(await new Blob(chunks, { type: recorder.mimeType }).arrayBuffer())
        if (!disposed && revision === microphoneRevision && sourceRevision === audioRevision) await useAudio(pcmToWav(decoded))
      } catch { if (!disposed && revision === microphoneRevision) audioError.value = '无法解码这次录音。请录制一段较短的音频，或导入 WAV。' }
      finally { if (!disposed && revision === microphoneRevision) microphoneBusy.value = false }
    }
    recorder.start(1000); microphoneRecording.value = true; microphoneBusy.value = false
    microphoneTimer = window.setTimeout(stopMicrophone, 59_000)
  } catch {
    releaseMicrophone(ownedStream)
    if (!disposed && revision === microphoneRevision) { microphoneRecorder = null; audioError.value = '未能访问麦克风。请允许浏览器录音，或导入本地 WAV。' }
  }
  finally { if (!disposed && revision === microphoneRevision && !microphoneRecording.value) microphoneBusy.value = false }
}
async function recordVideo() {
  if (recordingVideo.value) { stopVideo(); return }
  if (disposed || videoBusy.value) return
  const canvas = stage.value?.querySelector('canvas')
  if (!canPlay.value || !canvas || !window.MediaRecorder || !canvas.captureStream) { recordingError.value = '此浏览器暂不支持成片录制。可以使用 OBS 窗口采集。'; return }
  const revision = ++videoRevision
  const sourceRevision = audioRevision
  const avatarRevision = modelRevision
  recordingError.value = ''; videoBusy.value = true
  let ownedStream: MediaStream | null = null
  try {
    await audioGraph()
    if (disposed || revision !== videoRevision || sourceRevision !== audioRevision || avatarRevision !== modelRevision || !canPlay.value) return
    const mime = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/mp4', 'video/webm'].find(value => MediaRecorder.isTypeSupported(value))
    if (!mime) throw new Error('浏览器不支持可用的录制编码，请使用 OBS 窗口采集。')
    const canvasStream = canvas.captureStream(30)
    ownedStream = canvasStream
    const stream = new MediaStream([...canvasStream.getVideoTracks(), ...audioDestination!.stream.getAudioTracks().map(t => t.clone())])
    ownedStream = stream; videoStream = stream
    const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 2_500_000, audioBitsPerSecond: 128_000 })
    videoRecorder = recorder
    const chunks: Blob[] = []; let size = 0; let failed = false
    recorder.ondataavailable = event => {
      size += event.data.size
      if (size <= 96 * 1024 * 1024) chunks.push(event.data)
      else { failed = true; if (!disposed && videoRecorder === recorder) { recordingError.value = '录制达到大小限制，已停止。'; stopVideo() } }
    }
    recorder.onerror = () => {
      failed = true
      if (!disposed && videoRecorder === recorder) { recordingError.value = '视频录制失败，请使用 OBS 采集或更换浏览器。'; stopVideo() }
      else stream.getTracks().forEach(t => t.stop())
    }
    recorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop())
      if (videoRecorder !== recorder) return
      videoStream = null; videoRecorder = null
      if (videoTimer !== undefined) window.clearTimeout(videoTimer)
      videoTimer = undefined; recordingVideo.value = false; videoBusy.value = false
      if (recordedVideoURL.value) URL.revokeObjectURL(recordedVideoURL.value)
      recordedVideoName.value = mime.startsWith('video/mp4') ? 'avatar3d-local-preview.mp4' : 'avatar3d-local-preview.webm'
      recordedVideoURL.value = !disposed && !failed && chunks.length && size <= 96 * 1024 * 1024 ? URL.createObjectURL(new Blob(chunks, { type: mime })) : ''
    }
    stopPlayback(); recorder.start(1000); recordingVideo.value = true; videoBusy.value = false
    videoTimer = window.setTimeout(stopVideo, 180_000)
    await play()
    if (videoRecorder === recorder && revision === videoRevision && !playing.value) stopVideo()
  } catch (error) {
    ownedStream?.getTracks().forEach(t => t.stop())
    if (!disposed && revision === videoRevision) {
      recordingError.value = message(error); videoStream = null; videoRecorder = null; recordingVideo.value = false
    }
  } finally { if (!disposed && revision === videoRevision && !recordingVideo.value) videoBusy.value = false }
}
function exportTrack() { if (rawTrack) download(new Blob([JSON.stringify(rawTrack, null, 2)], { type: 'application/json' }), 'avatar-lipsync.json') }
function exportReport() {
  const report = { version: '0.3.0-preview', generated_at: new Date().toISOString(), browser: navigator.userAgent,
    model: capabilities.value, rendering: metrics.value,
    audio: { name: audioName.value, duration: duration.value, sha256: audioHash.value },
    lip_sync: { mode: trackMode.value, binding: track.value?.binding ?? null, cues: track.value?.cues.length ?? 0, offset_ms: Number(lipOffset.value), strength: Number(lipStrength.value) },
    live_binding: { enabled: followMainSession.value, session_id: mainSessionId.value || null,
      lifecycle_epoch: mainSessionEpoch.value, status: mainSessionStatus.value },
    verification: { rendered_in_this_browser: renderReady.value && !!capabilities.value, audio_track_prepared: !!track.value, human_quality_review: 'not_recorded', obs: 'not_verified', taobao: 'not_verified', eight_hour_run: 'not_verified' } }
  download(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }), 'avatar3d-local-report.json')
}
onMounted(async () => {
  await nextTick()
  try {
    if (disposed) return
    const params = new URLSearchParams(window.location.search)
    obsSourceMode.value = params.get('obs') === '1'
    if (obsSourceMode.value) {
      cleanView.value = true
      const requestedBackground = params.get('background')
      if (requestedBackground === 'green' || requestedBackground === 'transparent' || requestedBackground === 'studio') {
        background.value = requestedBackground
      }
    }
    renderer = new AvatarRenderer(stage.value!, { onMetrics: value => { metrics.value = value }, onError: value => {
      modelRevision++; modelFetch?.abort(); modelFetch = null
      renderReady.value = false; capabilities.value = null; modelBusy.value = false; cleanView.value = false
      modelError.value = value; stopPlayback(); stopVideo()
    } })
    renderer.setBackground(background.value)
    window.addEventListener('keydown', key); tick(); void exampleModel()
  } catch (error) { modelError.value = message(error) }
})
onBeforeUnmount(() => {
  disposed = true; audioRevision++; modelRevision++; microphoneRevision++; trackRevision++; modelFetch?.abort(); modelFetch = null; analyzer.cancel(); cancelAnimationFrame(frame)
  if (mainSessionTimer !== undefined) window.clearTimeout(mainSessionTimer)
  window.removeEventListener('keydown', key); stopMicrophone(); stopVideo(); stopPlayback(); revokeAudio()
  if (recordedVideoURL.value) URL.revokeObjectURL(recordedVideoURL.value)
  audioSource?.disconnect(); audioDestination?.disconnect(); void audioContext?.close()
  renderer?.dispose()
})
</script>

<template>
  <main class="avatar-lab" :class="{ 'clean-view': cleanView, 'obs-source': obsSourceMode }" :data-output-mode="obsSourceMode ? 'obs-browser-source' : 'preview'">
    <header class="lab-header"><a class="lab-brand" href="/" aria-label="返回工作台"><span>声</span><div><strong>数字人 · 3D 验证室</strong><small>LOCAL AVATAR LAB</small></div></a><div class="lab-header-actions"><span class="lab-version">v0.3 预览版</span><button class="lab-button secondary" @click="exportReport">导出验证记录</button></div></header>
    <section class="lab-intro"><div><p class="lab-eyebrow">先看效果，再决定投入</p><h1>让三维人物，跟着你的声音开口。</h1><p>模型、音频与口型分析留在本机。先检查真人感、嘴形和运行流畅度。</p></div><span class="local-chip"><i />浏览器本地运行 · 无需 CUDA</span></section>
    <div class="lab-grid">
      <section class="preview-panel">
        <div class="preview-title"><span><i :class="{ ready: !!capabilities }" />{{ modelBusy ? '正在加载三维人物…' : capabilities ? '三维人物已载入' : '等待人物模型' }}</span><span class="fps" data-testid="render-fps">{{ metrics ? metrics.fps.toFixed(0) + ' FPS' : '— FPS' }}</span></div>
        <div ref="stage" class="avatar-stage" data-testid="avatar-stage"><div v-if="!capabilities" class="stage-placeholder"><span class="stage-orbit" /><strong>{{ modelBusy ? '准备人物与材质' : '从一个人物开始' }}</strong><p>{{ modelBusy ? '首次加载需要一点时间' : '加载示例人物，或选择本地 GLB' }}</p></div></div>
        <button v-if="cleanView && !obsSourceMode" class="leave-clean" @click="cleanView = false">退出纯画面 · Esc</button>
        <div class="preview-tools"><span>拖动旋转 · 滚轮缩放</span><div><button @click="resetCamera">重置视角</button><button :disabled="!capabilities" @click="cleanView = true">纯画面 / OBS</button></div></div>
        <div class="transport">
          <div class="transport-main"><button class="play-button" :disabled="!canPlay" :aria-label="playing ? '暂停播放' : '播放音频与口型'" @click="playing ? pause() : play()">{{ playing ? 'Ⅱ' : '▶' }}</button><div class="track-copy"><strong>{{ audioName || '导入 WAV，或录一段自己的声音' }}</strong><span>{{ trackLabel }}<template v-if="track"> · {{ track.cues.length }} 段嘴形</template></span></div><button class="stop-button" :disabled="!audioURL" @click="stopPlayback">停止</button></div>
          <div class="timeline"><span>{{ time(currentTime) }}</span><input aria-label="播放进度" type="range" min="0" :max="duration || 1" step="0.01" :value="currentTime" :disabled="!canPlay" :style="{ '--progress': timelinePercent + '%' }" @input="seek" /><span>{{ time(duration) }}</span></div>
        </div>
        <div v-if="modelError" class="lab-alert error" role="alert">{{ modelError }}</div>
        <div v-if="capabilities && !capabilities.hasUsableMouthRig" class="lab-alert warning">这个模型缺少可用的嘴形绑定。可以观察三维外观，暂时不能用于口型验证。</div>
        <div class="sample-boundary"><strong>本轮看什么</strong><span>正常观看时的真人感、闭唇与圆唇、停顿闭口，以及连续播放是否顺畅。</span></div>
      </section>
      <aside class="lab-controls">
        <section class="control-card"><div class="step-heading"><span>01</span><div><h2>人物形象</h2><p>真正的三维模型，可旋转检查</p></div></div><div class="button-pair"><button class="lab-button secondary" :disabled="modelBusy" @click="exampleModel">加载示例人物</button><label class="lab-button secondary file-button" :class="{ disabled: modelBusy }">选择 GLB<input type="file" accept=".glb,model/gltf-binary" :disabled="modelBusy" aria-label="选择三维模型" @change="chooseModel" /></label></div><p class="control-hint">示例为 CC0 人物资产，用于观察效果；你也可以加载自己的写实模型。</p><div v-if="capabilities" class="model-summary"><span>{{ capabilities.fileName }}</span><small>{{ capabilities.meshCount }} 个网格 · {{ (capabilities.triangleCount / 1000).toFixed(1) }}k 三角面 · {{ capabilities.mouthSupport === 'oculus' ? '多嘴形绑定' : capabilities.mouthSupport === 'arkit' ? '面部形变绑定' : '缺少嘴形' }}</small></div></section>
        <section class="control-card"><div class="step-heading"><span>02</span><div><h2>声音与口型</h2><p>使用实际播放的这份音频分析</p></div></div><div class="button-pair"><label class="lab-button primary file-button" :class="{ disabled: microphoneRecording || microphoneBusy }">导入 WAV<input type="file" accept=".wav,audio/wav" :disabled="microphoneRecording || microphoneBusy" aria-label="选择测试音频" @change="chooseAudio" /></label><button class="lab-button secondary" :class="{ recording: microphoneRecording }" :disabled="microphoneBusy || audioBusy" @click="recordMicrophone">{{ microphoneRecording ? '结束录音' : microphoneBusy ? '准备录音…' : '录一段声音' }}</button></div><p class="control-hint">可使用现有工作台导出的语音，或自己录音。录音最长 60 秒；WAV 最长 5 分钟。</p><div v-if="microphoneRecording" class="lab-alert warning" role="status">正在录音。说完后点击“结束录音”，随后会在本机分析口型。</div><div v-if="audioBusy" class="analysis-progress" role="status"><span>正在准备口型 {{ progress }}%</span><progress max="100" :value="progress" /></div><div v-if="audioError" class="lab-alert error" role="alert">{{ audioError }}</div><p v-else-if="notice" class="control-notice" role="status">{{ notice }}</p><div class="track-tools"><label class="text-button file-button" :class="{ disabled: !prepared || audioBusy }">导入嘴形轨道<input type="file" accept=".json,application/json" :disabled="!prepared || audioBusy" aria-label="导入口型轨道" @change="importTrack" /></label><button class="text-button" :disabled="!track" @click="exportTrack">导出轨道</button><button class="text-button" :disabled="!prepared" @click="saveAudio">保存 WAV</button></div><p class="quality-note">自动口型是声学分析试验，中文精细嘴形尚未验收。导入经过校对的轨道，可以单独验证人物绑定和同步。</p></section>
        <section class="control-card"><div class="step-heading"><span>03</span><div><h2>观察与校准</h2><p>调整一个变量，再比较效果</p></div></div><label class="range-label"><span>嘴部动作幅度 <b>{{ Number(lipStrength).toFixed(2) }}</b></span><input v-model="lipStrength" aria-label="嘴部动作幅度" type="range" min="0.2" max="1" step="0.05" /></label><label class="range-label"><span>嘴形时间调整 <b>{{ lipOffset > 0 ? '+' : '' }}{{ lipOffset }} ms</b></span><input v-model="lipOffset" aria-label="嘴形时间调整" type="range" min="-300" max="300" step="10" /></label><p class="control-hint">正值让嘴形提前。此调整用于比较，不会改变原始音频。</p><div class="viseme-buttons"><button v-for="viseme in visemeChoices" :key="viseme" :disabled="!capabilities?.hasUsableMouthRig" :class="{ active: selectedViseme === viseme }" @click="setPose(viseme)">{{ ({ PP: '闭唇', FF: '唇齿', aa: '张口', E: '中开', ih: '展唇', oh: '圆唇', ou: '收圆', sil: '静止' } as Record<string, string>)[viseme] }}</button></div><div class="display-options"><label>背景<select v-model="background" aria-label="画面背景" @change="setBackground"><option value="studio">摄影棚</option><option value="green">绿幕</option><option value="transparent">透明</option></select></label><label class="check-label"><input v-model="idleMotion" type="checkbox" @change="setMotion" />自然眨眼与轻微动作</label></div></section>
        <section class="control-card"><h2>主场次生命周期</h2><label class="check-label"><input v-model="followMainSession" type="checkbox" aria-label="跟随主直播场次" @change="changeMainSessionBinding" />跟随主直播场次</label><p class="control-hint">启用后只在绑定场次运行时允许播放或录制；场次停止、重开或 epoch 变化会立即停止当前 3D 输出。</p><p role="status">{{ followMainSession ? `状态：${mainSessionStatus}${mainSessionId ? ` · ${mainSessionId.slice(0, 8)} · epoch ${mainSessionEpoch ?? '缺失'}` : ''}` : '未绑定，保持独立预览模式' }}</p><div v-if="mainSessionError" class="lab-alert warning" role="alert">{{ mainSessionError }}</div></section>
        <section class="control-card export-card"><h2>留下第一段样片</h2><p>录制从音频开头开始，最长 3 分钟。也可以切到纯画面后用 OBS 窗口采集。</p><button class="lab-button primary full" :class="{ recording: recordingVideo }" :disabled="videoBusy || (!recordingVideo && !canPlay)" @click="recordVideo">{{ recordingVideo ? '结束并生成录像' : videoBusy ? '正在处理录像…' : '录制人物与声音' }}</button><a v-if="recordedVideoURL" class="video-download" :href="recordedVideoURL" :download="recordedVideoName">下载本次录像</a><div v-if="recordingError" class="lab-alert error" role="alert">{{ recordingError }}</div></section>
      </aside>
    </div>
    <details class="lab-details"><summary>查看本次验证信息与范围</summary><div class="detail-grid"><div><h3>本地运行信息</h3><p>{{ metrics ? `${metrics.width} × ${metrics.height} · DPR ${metrics.pixelRatio.toFixed(1)} · ${metrics.drawCalls} 次绘制` : '等待渲染' }}</p><p>音频 SHA256：<code>{{ audioHash || '尚未导入' }}</code></p><p v-for="warning in capabilities?.warnings || []" :key="warning">{{ warning }}</p></div><div><h3>验收范围</h3><p>这是低端 3D 质量验证版。人物观感、中文发音嘴形、目标电脑性能和 OBS 采集仍需你实际检查。当前页面不连接淘宝、不自动生成话术，也不替代已有工作台的审核流程。</p><p>上传按钮只读取本地文件；人物和音频不会上传到服务器。纯画面模式需保持本页面打开。关闭页面会停止播放。</p></div></div></details>
    <footer class="lab-footer"><span>本地验证 · 三维人物 · 同源音频</span><a href="/">打开原有工作台 →</a></footer>
    <audio ref="audioElement" :src="audioURL || undefined" preload="auto" @play="audioPlayed" @pause="playing = false" @ended="audioEnded" @error="audioFailed" />
  </main>
</template>
