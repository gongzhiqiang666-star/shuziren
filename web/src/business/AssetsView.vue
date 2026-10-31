<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime } from '../domain'
import type { NoticeSink } from '../types'
import DialogShell from '../components/DialogShell.vue'
import Icon from '../components/Icon.vue'
import HistoryDialog from './HistoryDialog.vue'
import { validHash } from './forms'
import type { Asset } from './types'
const props = defineProps<{ api: ApiClient; shopId: string; notify: NoticeSink; reload: () => Promise<void> }>()
const records = ref<Asset[]>([]), loading = ref(true), error = ref(''), formError = ref(''), open = ref(false), busy = ref(false)
const editing = ref<Asset | null>(null), history = ref<Asset | null>(null)
const form = reactive({ kind: 'avatar' as Asset['kind'], name: '', identifier: '', sha256: '', modelVersion: '', authorized: false, active: false })
const kinds = { avatar: '数字人素材', voice: '音色', model: '模型' }
async function load() { loading.value = true; error.value = ''; try { records.value = await props.api.request<Asset[]>('/assets', { query: { shop_id: props.shopId } }) } catch (cause) { error.value = errorMessage(cause) } finally { loading.value = false } }
onMounted(load)
function edit(record: Asset | null) { editing.value = record; formError.value = ''; open.value = true; Object.assign(form, record ? { ...record, modelVersion: record.model_version } : { kind: 'avatar', name: '', identifier: '', sha256: '', modelVersion: '', authorized: false, active: false }) }
async function save() {
  if (busy.value) return; formError.value = ''
  try {
    if (!form.name.trim() || !form.identifier.trim()) throw new Error('请填写档案名称与本地资产标签。')
    if (!validHash(form.sha256.trim())) throw new Error('SHA-256 必须是 64 位小写十六进制字符，请从实际文件计算，不要填写占位值。')
    if (form.active && !form.authorized) throw new Error('启用前需要确认资产与音色授权。')
    busy.value = true
    await props.api.request(editing.value ? '/assets/' + editing.value.id : '/assets', { method: editing.value ? 'PUT' : 'POST', body: { shop_id: props.shopId, kind: form.kind, name: form.name.trim(), identifier: form.identifier.trim(), sha256: form.sha256.trim(), model_version: form.modelVersion.trim(), authorized: form.authorized, active: form.active, version: editing.value?.version ?? 0 } })
    open.value = false; await load(); await props.reload(); props.notify('资产档案已保存，待与本地引擎实际配置联调核对；没有远程切换模型或音色。', 'info')
  } catch (cause) { formError.value = errorMessage(cause) } finally { busy.value = false }
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">AVATAR · VOICE · MODEL</div><h1>资产与音色</h1><p>记录实际素材、权重与音色版本，为任务保留可核对的依据。</p></div><button class="button primary" @click="edit(null)"><Icon name="plus" />新增档案</button></div><div class="info-strip">档案记录，待联调核对。此页不会修改 CosyVoice / LiveTalking 进程配置；启用只指定本店任务快照采用的档案版本。</div><div v-if="error" class="alert error" role="alert">{{ error }}<button class="inline-button" @click="load">重试</button></div>
  <section class="panel"><div class="panel-title"><h2>资产档案</h2><button class="button ghost small" :disabled="loading" @click="load">刷新</button></div><div v-if="loading" class="empty-state compact">正在读取档案…</div><div v-else-if="!records.length" class="empty-state"><Icon name="person" :size="32" /><h3>先登记实际使用的资产</h3><p>准备本地资产标签、文件 SHA-256、模型版本和授权信息。档案不会自动下载模型。</p><button class="button secondary" @click="edit(null)">登记第一项资产</button></div><div v-else class="asset-grid"><article v-for="asset in records" :key="asset.id" class="asset-card"><div class="section-heading"><span class="badge neutral">{{ kinds[asset.kind] }}</span><span class="badge" :class="asset.active ? 'success' : 'neutral'">{{ asset.active ? '快照采用此档案' : '未启用' }}</span></div><h3>{{ asset.name }}</h3><p class="muted small-text">{{ asset.identifier }} · v{{ asset.version }}</p><dl class="asset-details"><div><dt>模型版本</dt><dd>{{ asset.model_version || '未填写' }}</dd></div><div><dt>授权</dt><dd>{{ asset.authorized ? '操作者已确认' : '尚未确认' }}</dd></div><div><dt>SHA-256</dt><dd class="mono break-all">{{ asset.sha256 }}</dd></div></dl><p class="hint">档案记录，待联调核对 · {{ dateTime(asset.updated_at) }}</p><div class="form-actions"><button class="button ghost small" @click="history = asset">历史</button><button class="button secondary small" @click="edit(asset)">编辑档案</button></div></article></div></section>
  <DialogShell v-if="open" :title="editing ? '编辑资产档案' : '新增资产档案'" @close="!busy && (open = false)"><form class="form-stack" @submit.prevent="save"><label>类型<select v-model="form.kind" :disabled="!!editing"><option value="avatar">数字人素材</option><option value="voice">音色</option><option value="model">模型</option></select></label><label>档案名称<input v-model="form.name" required maxlength="160" /></label><label>本地资产标签<input v-model="form.identifier" required maxlength="200" placeholder="运维使用的资产标识，不是上传文件路径" /></label><label>文件 SHA-256<input v-model="form.sha256" required maxlength="64" minlength="64" pattern="[0-9a-f]{64}" class="mono" /><small>请填写实际文件校验值；页面只记录，不验证文件内容。</small></label><label>模型 / 音色版本<input v-model="form.modelVersion" maxlength="200" /></label><label class="checkbox-row"><input v-model="form.authorized" type="checkbox" />已核对素材、肖像、声音和权重的使用授权</label><label class="checkbox-row"><input v-model="form.active" type="checkbox" />任务快照采用此档案（同类旧档案会停用）</label><p class="hint">引擎配置须在部署端独立修改并联调。本页不表示实际音色或模型已经切换。</p><div v-if="formError" class="alert error" role="alert">{{ formError }}</div><div class="form-actions"><button class="button secondary" type="button" :disabled="busy" @click="open = false">取消</button><button class="button primary" :disabled="busy">{{ busy ? '保存中…' : '保存档案' }}</button></div></form></DialogShell>
  <HistoryDialog v-if="history" :api="api" :shop-id="shopId" kind="asset" :record-id="history.id" :current-version="history.version" :title="history.name" @close="history = null" />
</template>
