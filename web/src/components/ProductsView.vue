<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime, expired, localDateTime, money, parseMoneyToCents } from '../domain'
import type { NoticeSink, Product } from '../types'
import DialogShell from './DialogShell.vue'
import Icon from './Icon.vue'
import HistoryDialog from '../business/HistoryDialog.vue'

const props = defineProps<{ api: ApiClient; shopId: string; products: Product[]; reload: () => Promise<void>; notify: NoticeSink }>()
const search = ref('')
const open = ref(false)
const editing = ref<Product | null>(null)
const history = ref<Product | null>(null)
const saving = ref(false)
const error = ref('')
const form = reactive({ title: '', sku: '', description: '', specs: '', price: '', stock: '0', active: true, expires: '' })
const filtered = computed(() => props.products.filter(p => (p.title + ' ' + p.sku).toLowerCase().includes(search.value.trim().toLowerCase())))
function edit(product: Product | null) {
  editing.value = product
  Object.assign(form, product ? { title: product.title, sku: product.sku, description: product.description, specs: product.specs, price: (product.price_cents / 100).toFixed(2), stock: String(product.stock), active: product.active, expires: localDateTime(product.expires_at) } : { title: '', sku: '', description: '', specs: '', price: '', stock: '0', active: true, expires: '' })
  error.value = ''
  open.value = true
}
async function save() {
  if (saving.value) return
  error.value = ''
  try {
    const title = form.title.trim()
    if (!title) throw new Error('请填写商品名称。')
    if (!form.sku.trim()) throw new Error('请填写 SKU / 商品编号。')
    const price = parseMoneyToCents(form.price)
    if (!/^\d+$/.test(form.stock) || !Number.isSafeInteger(Number(form.stock))) throw new Error('库存请输入非负整数。')
    if (price > 1_000_000_000_000 || Number(form.stock) > 1_000_000_000_000) throw new Error('价格或库存超出允许范围，请核对商品资料。')
    const expires = form.expires ? new Date(form.expires).toISOString() : null
    const body = { shop_id: props.shopId, title, sku: form.sku.trim(), description: form.description.trim(), specs: form.specs.trim(), price_cents: price, stock: Number(form.stock), active: form.active, expires_at: expires, ...(editing.value ? { version: editing.value.version } : {}) }
    saving.value = true
    await props.api.request(editing.value ? '/products/' + editing.value.id : '/products', { method: editing.value ? 'PUT' : 'POST', body })
    await props.reload()
    open.value = false
    props.notify(editing.value ? '商品资料已更新；旧版本任务不能继续审批或派发。' : '商品已添加，可以创建第一条话术。')
  } catch (cause) { error.value = errorMessage(cause) } finally { saving.value = false }
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">PRODUCT LIBRARY</div><h1>商品资料</h1><p>价格、规格与有效期，是每次回复的事实依据。</p></div><button class="button primary" @click="edit(null)"><Icon name="plus" />新增商品</button></div>
  <section class="panel">
    <div class="panel-toolbar"><div class="search-field"><Icon name="search" /><input v-model="search" aria-label="搜索商品" placeholder="搜索商品名称或 SKU" /></div><span class="muted">{{ products.length }} 件商品</span></div>
    <div v-if="!products.length" class="empty-state"><div class="empty-icon"><Icon name="box" :size="32" /></div><h3>先录入一件商品</h3><p>补充商品事实后，才能生成和审核讲解话术。</p><button class="button secondary" @click="edit(null)">添加第一件商品<Icon name="arrow" :size="17" /></button></div>
    <div v-else-if="!filtered.length" class="empty-state compact"><h3>没有匹配的商品</h3><p>试试其他名称或清空搜索条件。</p></div>
    <div v-else class="table-scroll"><table><thead><tr><th>商品 / SKU</th><th>价格</th><th>库存</th><th>资料状态</th><th>版本 / 更新</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="product in filtered" :key="product.id"><td><strong>{{ product.title }}</strong><div class="secondary-line">{{ product.sku || '未填写 SKU' }}</div></td><td class="price">{{ money(product.price_cents) }}</td><td>{{ product.stock }}</td><td><span class="badge" :class="!product.active ? 'neutral' : expired(product) ? 'danger' : 'success'">{{ !product.active ? '已停用' : expired(product) ? '已过期' : '可用于回复' }}</span><div v-if="product.expires_at" class="secondary-line">有效至 {{ dateTime(product.expires_at) }}</div></td><td><span class="mono">v{{ product.version }}</span><div class="secondary-line">{{ dateTime(product.updated_at) }}</div></td><td><button class="button ghost small" :aria-label="'编辑 ' + product.title" @click="edit(product)"><Icon name="edit" :size="16" />编辑</button><button class="button ghost small" @click="history = product">历史</button></td></tr>
    </tbody></table></div>
  </section>
  <p class="page-note">金额按整数分保存。商品变更后会产生新版本；过期或已停用的商品无法继续生成和派发话术。</p>
  <DialogShell v-if="open" :title="editing ? '编辑商品资料' : '新增商品'" @close="!saving && (open = false)">
    <form class="form-stack" @submit.prevent="save">
      <div v-if="error" class="alert error" role="alert">{{ error }}</div>
      <label>商品名称 <span class="required">*</span><input v-model="form.title" name="title" required maxlength="200" placeholder="填写真实商品名称" /></label>
      <label>SKU / 商品编号 <span class="required">*</span><input v-model="form.sku" name="sku" required maxlength="100" placeholder="便于运营区分规格" /></label>
      <div class="form-row"><label>价格（元） <span class="required">*</span><input v-model="form.price" name="price" inputmode="decimal" required placeholder="0.00" /><small>保存时精确转换为分</small></label><label>库存数量<input v-model="form.stock" name="stock" inputmode="numeric" required /></label></div>
      <label>规格信息<textarea v-model="form.specs" rows="2" maxlength="4000" placeholder="尺寸、材质、颜色、包装数量等" /></label>
      <label>商品说明<textarea v-model="form.description" rows="3" maxlength="4000" placeholder="填写可核对的商品事实，不填写未经批准的承诺" /></label>
      <label>资料有效期<input v-model="form.expires" type="datetime-local" /><small>采用当前设备时区；留空表示没有指定截止时间。</small></label>
      <label class="checkbox-row"><input v-model="form.active" type="checkbox" />允许用于新话术</label>
      <p v-if="editing" class="hint">正在编辑 v{{ editing.version }}。保存后，旧版本草稿和音频会失效。</p>
      <div class="form-actions"><button class="button secondary" type="button" :disabled="saving" @click="open = false">取消</button><button class="button primary" :disabled="saving">{{ saving ? '正在保存…' : '保存商品' }}</button></div>
    </form>
  </DialogShell>
  <HistoryDialog v-if="history" :api="api" :shop-id="shopId" kind="product" :record-id="history.id" :current-version="history.version" :title="history.title" @close="history = null" @restored="reload" />
</template>
