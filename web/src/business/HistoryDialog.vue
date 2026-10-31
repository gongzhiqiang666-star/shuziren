<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime, money } from '../domain'
import DialogShell from '../components/DialogShell.vue'
import type { HistoryEntry } from './types'
const props = defineProps<{ api: ApiClient; shopId: string; kind: 'persona' | 'product' | 'knowledge' | 'promotion' | 'asset'; recordId?: string; currentVersion: number; title: string }>()
const emit = defineEmits<{ close: []; restored: [] }>()
const entries = ref<HistoryEntry[]>([])
const selected = ref<HistoryEntry | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const confirmed = ref(false)
const base = computed(() => props.kind === 'persona' ? '/persona' : '/' + ({ product: 'products', knowledge: 'knowledge-records', promotion: 'promotions', asset: 'assets' }[props.kind]) + '/' + props.recordId)
const canRestore = computed(() => ['persona', 'product', 'knowledge'].includes(props.kind) && selected.value && !selected.value.deleted && selected.value.version !== props.currentVersion)
const labels: Record<string, string> = { name: '名称', title: '标题', tone: '语气', prompt: '人格规则', description: '说明', specs: '规格', sku: 'SKU', price_cents: '价格', stock: '库存', content: '内容', kind: '类型', source: '资料来源', scope: '适用范围', scope_id: '范围对象', expires_at: '有效期', active: '启用', starts_at: '开始时间', ends_at: '结束时间', offer_price_cents: '活动价', identifier: '资产标签', sha256: 'SHA-256', model_version: '模型版本', authorized: '授权确认', deleted_at: '删除时间' }
const details = computed(() => selected.value ? Object.entries(selected.value.snapshot).filter(([key]) => labels[key]).map(([key, value]) => ({ label: labels[key], value: value == null ? '未设置' : key.endsWith('_cents') && typeof value === 'number' ? money(value) : typeof value === 'boolean' ? value ? '是' : '否' : String(value) })) : [])
onMounted(async () => {
  try { entries.value = await props.api.request<HistoryEntry[]>(base.value + '/history', { query: { shop_id: props.shopId } }); selected.value = entries.value[0] ?? null }
  catch (cause) { error.value = errorMessage(cause) } finally { loading.value = false }
})
async function restore() {
  if (!selected.value || !canRestore.value || !confirmed.value || busy.value) return
  busy.value = true; error.value = ''
  try { await props.api.request(base.value + '/restore', { method: 'POST', body: { shop_id: props.shopId, version: props.currentVersion, target_version: selected.value.version } }); emit('restored'); emit('close') }
  catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
</script>
<template>
  <DialogShell :title="title + ' · 版本历史'" wide @close="!busy && emit('close')">
    <div class="form-stack history-body"><div v-if="error" class="alert error" role="alert">{{ error }}</div><p class="hint">当前版本 v{{ currentVersion }}。恢复会以历史内容创建新版本，不回退版本编号；相关旧话术需要重新生成和审核。</p><p v-if="loading" class="muted">正在读取历史…</p><p v-else-if="!entries.length" class="muted">尚无历史记录。</p><div v-else class="history-grid"><div class="history-list"><button v-for="entry in entries" :key="entry.version" :class="{ active: selected?.version === entry.version }" @click="selected = entry; confirmed = false"><strong>v{{ entry.version }} {{ entry.deleted ? '· 已删除' : '' }}</strong><small>{{ dateTime(entry.recorded_at) }}</small></button></div><dl class="history-details"><div v-for="detail in details" :key="detail.label"><dt>{{ detail.label }}</dt><dd>{{ detail.value }}</dd></div></dl></div><label v-if="canRestore" class="checkbox-row"><input v-model="confirmed" type="checkbox" />我已核对历史内容，确认替换当前内容并生成新版本。</label><div class="form-actions"><button class="button secondary" :disabled="busy" @click="emit('close')">关闭</button><button v-if="canRestore" class="button primary" :disabled="busy || !confirmed" @click="restore">{{ busy ? '正在恢复…' : '恢复为新版本' }}</button></div></div>
  </DialogShell>
</template>
