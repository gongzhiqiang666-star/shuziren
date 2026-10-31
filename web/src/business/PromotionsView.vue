<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime, localDateTime, money } from '../domain'
import type { NoticeSink, Product } from '../types'
import DialogShell from '../components/DialogShell.vue'
import Icon from '../components/Icon.vue'
import HistoryDialog from './HistoryDialog.vue'
import { dateRange, optionalAmount } from './forms'
import type { Promotion } from './types'
const props = defineProps<{ api: ApiClient; shopId: string; products: Product[]; notify: NoticeSink; reload: () => Promise<void> }>()
const records = ref<Promotion[]>([]), loading = ref(true), error = ref(''), formError = ref(''), open = ref(false), saving = ref(false)
const editing = ref<Promotion | null>(null), history = ref<Promotion | null>(null)
const form = reactive({ title: '', description: '', productId: '', price: '', start: '', end: '', active: false })
async function load() { loading.value = true; error.value = ''; try { records.value = await props.api.request<Promotion[]>('/promotions', { query: { shop_id: props.shopId } }) } catch (cause) { error.value = errorMessage(cause) } finally { loading.value = false } }
onMounted(load)
function edit(record: Promotion | null) {
  editing.value = record; formError.value = ''; open.value = true
  Object.assign(form, record ? { title: record.title, description: record.description, productId: record.product_id ?? '', price: record.offer_price_cents == null ? '' : (record.offer_price_cents / 100).toFixed(2), start: localDateTime(record.starts_at), end: localDateTime(record.ends_at), active: record.active } : { title: '', description: '', productId: '', price: '', start: '', end: '', active: false })
}
function state(record: Promotion) { if (!record.active) return '未启用'; if (Date.parse(record.ends_at) <= Date.now()) return '已结束'; if (Date.parse(record.starts_at) > Date.now()) return '未开始'; return '生效中' }
async function save() {
  if (saving.value) return
  formError.value = ''
  try {
    if (!form.title.trim()) throw new Error('请填写活动名称。')
    const body = { shop_id: props.shopId, title: form.title.trim(), description: form.description.trim(), product_id: form.productId || null, offer_price_cents: optionalAmount(form.price), ...dateRange(form.start, form.end), active: form.active, version: editing.value?.version ?? 0 }
    saving.value = true
    await props.api.request(editing.value ? '/promotions/' + editing.value.id : '/promotions', { method: editing.value ? 'PUT' : 'POST', body })
    open.value = false; await load(); await props.reload(); props.notify('活动已保存，服务端会在生成与派发前核验活动范围和时间。')
  } catch (cause) { formError.value = errorMessage(cause) } finally { saving.value = false }
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">PROMOTIONS</div><h1>活动管理</h1><p>明确优惠的范围与时间，避免数字人沿用过期承诺。</p></div><button class="button primary" @click="edit(null)"><Icon name="plus" />新增活动</button></div>
  <div v-if="error" class="alert error" role="alert">{{ error }}<button class="inline-button" @click="load">重试</button></div>
  <section class="panel"><div class="panel-title"><h2>店铺活动</h2><button class="button ghost small" :disabled="loading" @click="load">刷新</button></div><div v-if="loading" class="empty-state compact">正在读取活动…</div><div v-else-if="!records.length" class="empty-state"><Icon name="clock" :size="32" /><h3>还没有录入活动</h3><p>先确认优惠内容和有效时间，再显式启用。系统不会自行编造优惠。</p><button class="button secondary" @click="edit(null)">录入第一项活动</button></div><div v-else class="table-scroll"><table><thead><tr><th>活动 / 范围</th><th>活动价</th><th>有效时间</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="record in records" :key="record.id"><td><strong>{{ record.title }}</strong><div class="secondary-line">{{ record.product_id ? products.find(p => p.id === record.product_id)?.title || '指定商品' : '全店活动' }} · v{{ record.version }}</div></td><td>{{ record.offer_price_cents == null ? '未指定价格' : money(record.offer_price_cents) }}</td><td>{{ dateTime(record.starts_at) }}<div class="secondary-line">至 {{ dateTime(record.ends_at) }}</div></td><td><span class="badge" :class="state(record) === '生效中' ? 'success' : 'neutral'">{{ state(record) }}</span></td><td><div class="row-actions"><button class="button ghost small" @click="edit(record)">编辑</button><button class="button ghost small" @click="history = record">历史</button></div></td></tr></tbody></table></div></section><p class="page-note">活动开始或到期也会改变任务所依据的事实。旧草稿可能需要重新生成与审核；此处不会修改淘宝平台活动。</p>
  <DialogShell v-if="open" :title="editing ? '编辑活动' : '新增活动'" @close="!saving && (open = false)"><form class="form-stack" @submit.prevent="save"><label>活动名称<input v-model="form.title" name="title" required maxlength="160" /></label><label>适用范围<select v-model="form.productId"><option value="">全店</option><option v-for="product in products" :key="product.id" :value="product.id">{{ product.title }}</option></select></label><label>优惠内容<textarea v-model="form.description" rows="4" maxlength="4000" placeholder="填写已确认的条件、限制和赠品规则" /></label><label>活动价（元，可留空）<input v-model="form.price" inputmode="decimal" /><small>留空不代表免费；全店活动请谨慎填写统一价格。</small></label><div class="form-row"><label>开始时间<input v-model="form.start" type="datetime-local" required /></label><label>结束时间<input v-model="form.end" type="datetime-local" required /></label></div><label class="checkbox-row"><input v-model="form.active" type="checkbox" />确认资料真实，允许在有效期内用于回复</label><div v-if="formError" class="alert error" role="alert">{{ formError }}</div><div class="form-actions"><button type="button" class="button secondary" :disabled="saving" @click="open = false">取消</button><button class="button primary" :disabled="saving">{{ saving ? '保存中…' : '保存活动' }}</button></div></form></DialogShell>
  <HistoryDialog v-if="history" :api="api" :shop-id="shopId" kind="promotion" :record-id="history.id" :current-version="history.version" :title="history.title" @close="history = null" />
</template>
