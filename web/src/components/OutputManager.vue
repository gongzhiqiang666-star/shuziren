<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime } from '../domain'
import { outputLink } from '../output/scopedApi'
import type { OutputControlResult, OutputIssueResult, OutputStatus } from '../output/types'
import type { NoticeSink, Session } from '../types'
import DialogShell from './DialogShell.vue'
import Icon from './Icon.vue'

const props = defineProps<{ api: ApiClient; shopId: string; session: Session | undefined; reload: () => Promise<void>; notify: NoticeSink }>()
const emit = defineEmits<{ status: [value: OutputStatus | null] }>()
const output = ref<OutputStatus | null>(null)
const error = ref('')
const stopWarning = ref('')
const busy = ref(false)
const link = ref('')
const configOpen = ref(false)
const confirmAction = ref<'issue' | 'revoke' | ''>('')
const width = ref(1280)
const height = ref(720)
const fit = ref<'contain' | 'cover'>('contain')
const background = ref('#000000')
let disposed = false
let revision = 0
let polling = false
const labels: Record<OutputStatus['state'], string> = { disabled: '独立输出未启用', offline: '等待输出端连接', negotiating: '正在协商 / 等待播放', connected: '输出端在线', paused: '场次已暂停', ended: '本地场次已结束' }
const title = computed(() => output.value ? labels[output.value.state] : '正在确认输出方式')
function update(value: OutputStatus | null) { output.value = value; emit('status', value) }
async function load() {
  if (!props.session || polling || busy.value) return
  const id = props.session.id
  const serial = revision
  polling = true
  try {
    const value = await props.api.request<OutputStatus>('/sessions/' + id + '/output', { query: { shop_id: props.shopId } })
    if (disposed || serial !== revision || id !== props.session?.id) return
    update(value); error.value = ''
  } catch (cause) { if (!disposed && serial === revision) { error.value = errorMessage(cause); update(null) } } finally { polling = false }
}
watch([() => props.shopId, () => props.session?.id], () => { revision++; update(null); link.value = ''; error.value = ''; stopWarning.value = ''; configOpen.value = false; confirmAction.value = ''; void load() }, { immediate: true })
const timer = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load() }, 3000)
onBeforeUnmount(() => { disposed = true; revision++; window.clearInterval(timer) })
function editConfig() {
  const config = output.value?.config
  if (!config) return
  width.value = config.width; height.value = config.height; fit.value = config.fit; background.value = config.background; error.value = ''; configOpen.value = true
}
async function saveConfig() {
  if (!props.session || busy.value) return
  if (![width.value, height.value].every(value => Number.isInteger(Number(value)) && Number(value) >= 160 && Number(value) <= 3840) || !/^#[0-9a-f]{6}$/i.test(background.value)) { error.value = '宽高请输入 160–3840 的整数，背景色使用 #RRGGBB。'; return }
  revision++; busy.value = true; error.value = ''
  try {
    const value = await props.api.request<OutputStatus>('/sessions/' + props.session.id + '/output', { method: 'PUT', body: { shop_id: props.shopId, width: Number(width.value), height: Number(height.value), fit: fit.value, background: background.value } })
    update(value); configOpen.value = false; props.notify('输出画布配置已保存，不会改变模型原生生成分辨率。')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
async function control() {
  if (!props.session || !confirmAction.value || busy.value) return
  const action = confirmAction.value
  revision++; busy.value = true; error.value = ''; stopWarning.value = ''
  try {
    const result = await props.api.request<OutputIssueResult | OutputControlResult>('/sessions/' + props.session.id + '/output/' + action, { method: 'POST', body: { shop_id: props.shopId }, timeout: 65_000 })
    update(result.output)
    link.value = action === 'issue' && 'token' in result ? outputLink(result.token, result.output_path, window.location.origin) : ''
    if (result.media_stop_status === 'failed') stopWarning.value = '输出授权状态已更新，但停止旧媒体失败。请在 OBS 或媒体服务手动确认停止。'
    await props.reload(); confirmAction.value = ''
    props.notify(action === 'issue' ? '独立输出链接已签发。请将链接添加到 OBS，等待真实播放心跳。' : '独立输出已撤销，场次已暂停；旧链接不能继续使用。', 'info')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
async function copyLink() { try { await navigator.clipboard.writeText(link.value); props.notify('已复制场次专用输出链接，不包含工作台口令。') } catch { error.value = '浏览器无法自动复制，请手动选择下方链接复制。' } }
function openOutput() { if (link.value) window.open(link.value, '_blank', 'noopener,noreferrer') }
</script>
<template>
  <section class="panel output-manager"><div class="panel-title"><h2><Icon name="studio" :size="19" />独立 OBS 输出</h2><span class="badge" :class="output?.online ? 'success' : 'neutral'">{{ title }}</span></div><div class="output-manager-body"><p v-if="!session" class="hint">先创建或选择本地场次，再配置独立输出。</p><template v-else><div class="output-manager-summary"><div><strong>{{ output?.config.width ?? 1280 }} × {{ output?.config.height ?? 720 }}</strong><p>{{ output?.online ? '输出端已报告真实连接与音视频播放就绪。' : '签发链接后，等待 OBS 或独立页面建立音视频连接。' }}</p><small v-if="output?.last_heartbeat_at">最近心跳 {{ dateTime(output.last_heartbeat_at) }} · 心跳过期后禁止派发</small></div><div class="row-actions"><button class="button secondary small" :disabled="!output || busy" @click="editConfig">画布设置</button><button class="button primary small" :disabled="busy || session.status === 'ended'" @click="confirmAction = 'issue'">{{ output?.enabled ? '重新签发链接' : '启用独立输出' }}</button><button v-if="output?.enabled" class="button ghost small danger-text" :disabled="busy" @click="confirmAction = 'revoke'">撤销输出</button></div></div><div v-if="link" class="output-link"><label>场次专用链接 · 仅本次展示<input :value="link" readonly aria-label="独立输出链接" @focus="($event.target as HTMLInputElement).select()" /></label><div class="row-actions"><button class="button secondary small" @click="copyLink">复制链接</button><button class="button secondary small" :disabled="output?.online" @click="openOutput">打开独立页</button></div></div><p v-else-if="output?.enabled" class="hint">原链接不再回显。已配置的 OBS 可继续使用；需要新链接时重新签发，旧链接会立即失效。</p><p class="hint">将链接添加为 OBS 浏览器源，并使用上方画布宽高。一个场次只允许一个输出端；关闭运营台不影响独立输出页，关闭 OBS 源或独立页则会停止接收。在线只代表输出端自报就绪，不证明 OBS 采集或淘宝播出。</p></template><div v-if="error && !configOpen && !confirmAction" class="alert error" role="alert">{{ error }}<button class="inline-button" @click="load">重新检查</button></div><div v-if="stopWarning" class="alert error" role="alert">{{ stopWarning }}</div></div></section>
  <DialogShell v-if="configOpen" title="独立输出画布" @close="!busy && (configOpen = false)"><form class="form-stack" @submit.prevent="saveConfig"><p class="hint">只调整浏览器输出画布，不会提高模型原生嘴部细节。OBS 浏览器源的宽高请设为相同值。</p><div class="form-row"><label>宽度<input v-model="width" type="number" min="160" max="3840" step="1" required /></label><label>高度<input v-model="height" type="number" min="160" max="3840" step="1" required /></label></div><label>画面适配<select v-model="fit"><option value="contain">完整显示，保留空白边</option><option value="cover">填满画布，可能裁切</option></select></label><label>背景色<input v-model="background" type="text" maxlength="7" pattern="#[a-fA-F0-9]{6}" required /></label><div v-if="error" class="alert error" role="alert">{{ error }}</div><div class="form-actions"><button class="button primary" :disabled="busy">{{ busy ? '保存中…' : '保存画布' }}</button></div></form></DialogShell>
  <DialogShell v-if="confirmAction" :title="confirmAction === 'issue' ? '签发独立输出链接' : '撤销独立输出？'" @close="!busy && (confirmAction = '')"><div class="form-stack"><p>{{ confirmAction === 'issue' ? '新链接仅授予本场次音视频接收权限，不包含工作台口令。重新签发会使旧链接失效，并停止旧输出。签发不会自动恢复暂停的场次。' : '撤销会使链接失效、暂停场次并取消旧批次任务。重新使用管理预览时，需要恢复场次并重新连接。' }}</p><div v-if="error" class="alert error" role="alert">{{ error }}</div><div class="form-actions"><button class="button secondary" :disabled="busy" @click="confirmAction = ''">取消</button><button class="button" :class="confirmAction === 'issue' ? 'primary' : 'danger'" :disabled="busy" @click="control">{{ busy ? '正在处理…' : confirmAction === 'issue' ? '确认签发' : '确认撤销' }}</button></div></div></DialogShell>
</template>
