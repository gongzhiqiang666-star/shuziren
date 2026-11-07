<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import type { NoticeSink } from '../types'
import { conclusionLabel, preflightCommand, validateGate } from './validation'
import { gateNames, gateOrder } from './types'
import type { GateName, GateStatus, ReadinessRun } from './types'

const props = defineProps<{ api: ApiClient; shopId: string; notify: NoticeSink }>()
const runs = ref<ReadinessRun[]>([]), current = ref<ReadinessRun | null>(null), loading = ref(false), busy = ref(false), error = ref('')
const title = ref('最小直播链路验证'), outputMode = ref<'virtual_camera' | 'srs'>('virtual_camera'), activeGate = ref<GateName>('install')
const draft = reactive<{ status: GateStatus; note: string; evidence: Record<string, unknown> }>({ status: 'blocked', note: '', evidence: {} })
const gate = computed(() => current.value?.gates.find(item => item.name === activeGate.value) ?? null)
const gateError = computed(() => validateGate({ name: activeGate.value, status: draft.status, note: draft.note, evidence: draft.evidence, version: gate.value?.version ?? 1, updated_at: '' }))
const statusClass = (status: GateStatus) => status === 'passed' ? 'success' : status === 'failed' ? 'danger' : 'neutral'
const statusText = (status: GateStatus) => status === 'passed' ? '已有证据' : status === 'failed' ? '验证失败' : '尚未验证 / 阻塞'

function resetDraft() {
  const value = gate.value
  draft.status = value?.status ?? 'blocked'; draft.note = value?.note ?? ''; draft.evidence = { ...(value?.evidence ?? { reason: 'not_run' }) }
}
watch([activeGate, gate], resetDraft, { immediate: true })
watch(() => props.shopId, load)

async function load() {
  if (!props.shopId || loading.value) return
  loading.value = true; error.value = ''
  try { runs.value = await props.api.request<ReadinessRun[]>('/live-readiness/runs', { query: { shop_id: props.shopId } }); current.value = runs.value[0] ?? null }
  catch (cause) { error.value = errorMessage(cause) } finally { loading.value = false }
}
onMounted(load)

async function createRun() {
  if (!title.value.trim() || busy.value) return
  busy.value = true; error.value = ''
  try {
    const value = await props.api.request<ReadinessRun>('/live-readiness/runs', { method: 'POST', body: { shop_id: props.shopId, title: title.value.trim(), output_mode: outputMode.value } })
    runs.value = [value, ...runs.value]; current.value = value; activeGate.value = 'install'; props.notify('验证记录已创建。页面只记录证据，不会启动任何外部程序。')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}

function setEvidence(key: string, value: unknown) { draft.evidence = { ...draft.evidence, [key]: value } }
async function saveGate() {
  if (!current.value || busy.value || gateError.value) return
  busy.value = true; error.value = ''
  try {
    const value = await props.api.request<ReadinessRun>(`/live-readiness/runs/${current.value.id}/gates/${activeGate.value}`, { method: 'PUT', body: { shop_id: props.shopId, version: current.value.version, status: draft.status, evidence: draft.evidence, note: draft.note.trim() } })
    current.value = value; runs.value = runs.value.map(item => item.id === value.id ? value : item); props.notify(`${gateNames[activeGate.value]}记录已保存。`)
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}

async function copyCommand() { try { await navigator.clipboard.writeText(preflightCommand); props.notify('已复制固定预检命令，请在 Windows 外部终端执行。') } catch { error.value = '浏览器无法复制，请手动选择命令。' } }
async function exportRecord() {
  if (!current.value) return
  try {
    const value = await props.api.request<ReadinessRun>(`/live-readiness/runs/${current.value.id}/export`, { query: { shop_id: props.shopId } })
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = `live-readiness-${value.id}.json`; link.click(); URL.revokeObjectURL(url)
  } catch (cause) { error.value = errorMessage(cause) }
}
</script>

<template>
  <div class="page-heading"><div><div class="eyebrow">MINIMUM LIVE PROOF</div><h1>开播验证</h1><p>按顺序检查、操作并记录一条真实音画链路。</p></div><span class="badge neutral">只检查与记录</span></div>
  <div class="info-strip warning-strip">本页面不会执行命令、安装驱动、运行语音或数字人服务、控制 OBS，也不会连接淘宝账号。请在外部终端执行已批准命令。</div>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>
  <form v-if="!current" class="panel padded form-stack readiness-create" @submit.prevent="createRun"><h2>创建验证记录</h2><label>记录名称<input v-model="title" name="readiness-title" maxlength="160" required /></label><label>输出方式<select v-model="outputMode"><option value="virtual_camera">虚拟摄像头</option><option value="srs">SRS</option></select></label><button type="submit" class="button primary" :disabled="busy || !title.trim()">{{ busy ? '正在创建…' : '开始记录' }}</button></form>
  <template v-else>
    <div class="readiness-summary panel padded"><div><strong>{{ current.title }}</strong><p>{{ conclusionLabel(current.conclusion) }}</p></div><div class="form-actions"><select v-model="current" aria-label="选择历史验证记录"><option v-for="item in runs" :key="item.id" :value="item">{{ item.title }}</option></select><button class="button secondary small" @click="exportRecord">导出脱敏 JSON</button><button class="button ghost small" @click="current = null">新建记录</button></div></div>
    <div class="readiness-layout">
      <nav class="panel readiness-steps" aria-label="验证步骤"><button v-for="(name, index) in gateOrder" :key="name" :class="{ active: activeGate === name }" @click="activeGate = name"><span>{{ index + 1 }}</span><div><strong>{{ gateNames[name] }}</strong><small :class="statusClass(current.gates.find(g => g.name === name)?.status ?? 'blocked')">{{ statusText(current.gates.find(g => g.name === name)?.status ?? 'blocked') }}</small></div></button></nav>
      <section class="panel padded readiness-stage">
        <div class="section-heading"><h2>{{ gateNames[activeGate] }}</h2><span class="badge" :class="statusClass(draft.status)">{{ statusText(draft.status) }}</span></div>
        <div v-if="activeGate === 'install'" class="form-stack"><p>复制固定命令，在目标 Windows/NVIDIA 电脑的外部 PowerShell 中执行。这里只记录报告标签。</p><pre>{{ preflightCommand }}</pre><button class="button secondary small" @click="copyCommand">复制预检命令</button><label>预检报告标签<input :value="draft.evidence.preflight_report" @input="setEvidence('preflight_report', ($event.target as HTMLInputElement).value)" placeholder="例如 preflight-20261107" /></label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.nvidia === true" @change="setEvidence('nvidia', ($event.target as HTMLInputElement).checked)" />NVIDIA 检查通过</label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.assets === true" @change="setEvidence('assets', ($event.target as HTMLInputElement).checked)" />必需资产检查通过</label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.operator_confirmed === true" @change="setEvidence('operator_confirmed', ($event.target as HTMLInputElement).checked)" />实施人员已核对报告</label></div>
        <div v-else-if="activeGate === 'generation'" class="form-stack"><p>在外部终端运行已批准的语音服务，用 5–10 条首次新句生成 WAV。页面不上传音频。</p><label>WAV SHA-256<input :value="draft.evidence.wav_sha256" maxlength="64" @input="setEvidence('wav_sha256', ($event.target as HTMLInputElement).value.trim().toLowerCase())" /></label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.new_text === true" @change="setEvidence('new_text', ($event.target as HTMLInputElement).checked)" />使用首次新句</label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.listened === true" @change="setEvidence('listened', ($event.target as HTMLInputElement).checked)" />已人工试听</label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.same_wav === true" @change="setEvidence('same_wav', ($event.target as HTMLInputElement).checked)" />确认同一份 WAV 用于口型</label></div>
        <div v-else-if="activeGate === 'obs'" class="form-stack"><p>在外部运行数字人和 OBS，录制后回放核对声音与画面。</p><label>输出模式<select :value="draft.evidence.output_mode" @change="setEvidence('output_mode', ($event.target as HTMLSelectElement).value)"><option value="virtual_camera">虚拟摄像头</option><option value="srs">SRS</option></select></label><label>画面证据标签<input :value="draft.evidence.video" @input="setEvidence('video', ($event.target as HTMLInputElement).value)" /></label><label>声音证据标签<input :value="draft.evidence.audio" @input="setEvidence('audio', ($event.target as HTMLInputElement).value)" /></label><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.reviewed === true" @change="setEvidence('reviewed', ($event.target as HTMLInputElement).checked)" />已回放核对声音和画面</label></div>
        <div v-else-if="activeGate === 'platform'" class="form-stack"><p>没有获准测试路径时保持“阻塞”，这不影响本地链路结论。</p><label class="checkbox-row"><input type="checkbox" :checked="draft.evidence.approved === true" @change="setEvidence('approved', ($event.target as HTMLInputElement).checked)" />平台测试已获授权</label><label>观看端证据标签<input :value="draft.evidence.viewer_record" @input="setEvidence('viewer_record', ($event.target as HTMLInputElement).value)" /></label></div>
        <div v-else class="form-stack"><p>第一轮允许保持阻塞。完成持续运行后只记录人工证据，不由页面自动判定。</p><label>人工记录标签<input :value="draft.evidence.operator_record" @input="setEvidence('operator_record', ($event.target as HTMLInputElement).value)" /></label></div>
        <div class="form-stack readiness-save"><label>关卡状态<select v-model="draft.status"><option value="blocked">尚未验证 / 阻塞</option><option value="failed">验证失败</option><option value="passed">已有证据，通过</option></select></label><label>备注<textarea v-model="draft.note" rows="3" maxlength="2000" placeholder="只写脱敏结论，不粘贴日志、路径或凭据" /></label><div v-if="gateError" class="alert warning">{{ gateError }}</div><button class="button primary" :disabled="busy || !!gateError" @click="saveGate">{{ busy ? '保存中…' : '保存本关记录' }}</button></div>
      </section>
    </div>
  </template>
</template>

<style scoped>
.readiness-create{max-width:640px}.readiness-summary{display:flex;justify-content:space-between;gap:24px;align-items:center;margin-bottom:18px}.readiness-summary p{margin:6px 0 0;color:var(--muted)}.readiness-layout{display:grid;grid-template-columns:270px minmax(0,1fr);gap:18px}.readiness-steps{overflow:hidden;align-self:start}.readiness-steps button{width:100%;border:0;border-bottom:1px solid var(--border);background:transparent;padding:15px;display:flex;gap:12px;text-align:left;cursor:pointer}.readiness-steps button.active{background:#f3f7ee}.readiness-steps button>span{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#edf3ed}.readiness-steps button div{display:grid;gap:4px}.readiness-steps small.success{color:#527962}.readiness-steps small.danger{color:#a84b42}.readiness-steps small.neutral{color:var(--muted)}.readiness-stage pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;border-radius:10px;background:#161b22;color:#e6edf3}.readiness-save{margin-top:24px;padding-top:20px;border-top:1px solid var(--border)}
@media(max-width:900px){.readiness-layout{grid-template-columns:1fr}.readiness-summary{align-items:stretch;flex-direction:column}}
</style>
