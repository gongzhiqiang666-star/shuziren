<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { parseMoneyToCents } from '../domain'
import type { NoticeSink, Product, Session } from '../types'
import DialogShell from '../components/DialogShell.vue'
import { clearAttempt, getAttempt, saveAttempt } from './actionLedger'
import type { ActionAttempt, TaobaoAction, TaobaoItem, TaobaoItems } from './types'
const props = defineProps<{ api: ApiClient; shopId: string; sessions: Session[]; products: Product[]; notify: NoticeSink; reload: () => Promise<void> }>()
const sessionId = ref(''), page = ref(1), items = ref<TaobaoItems | null>(null), liveDetail = ref<unknown>(null), readBusy = ref(''), readError = ref('')
const importing = ref<TaobaoItem | null>(null), importBusy = ref(false), importError = ref(''), importConfirmed = ref(false)
const importForm = reactive({ title: '', sku: '', price: '', stock: '0', description: '', specs: '', active: false })
const attempt = ref<ActionAttempt | null>(getAttempt(props.shopId) ?? null), actionBusy = ref(false), confirmation = ref(false), reviewed = ref(false), actionError = ref('')
const actionForm = reactive({ kind: 'push-item' as 'push-item' | 'report', itemId: '', status: 2, avatar: false, modelType: 1, isvName: '', humanReply: '' })
const duplicateSku = computed(() => props.products.some(p => p.sku === importForm.sku.trim()))
watch(() => props.sessions, values => { if (!values.some(s => s.id === sessionId.value)) sessionId.value = values.find(s => s.status === 'active')?.id ?? values[0]?.id ?? '' }, { immediate: true })
async function read(kind: 'items' | 'live-detail') {
  if (readBusy.value || kind === 'live-detail' && !sessionId.value) return
  readBusy.value = kind; readError.value = ''
  try {
    if (kind === 'items') items.value = await props.api.request<TaobaoItems>('/taobao/items', { method: 'POST', body: { shop_id: props.shopId, page_no: Number(page.value), page_size: 20 }, timeout: 30_000 })
    else liveDetail.value = await props.api.request('/taobao/live-detail', { method: 'POST', body: { shop_id: props.shopId, session_id: sessionId.value }, timeout: 30_000 })
  } catch (cause) { readError.value = errorMessage(cause) } finally { readBusy.value = '' }
}
function reviewItem(item: TaobaoItem) { importing.value = item; importError.value = ''; importConfirmed.value = false; Object.assign(importForm, { title: item.title, sku: item.outer_id || 'TB-' + item.num_iid, price: item.price, stock: String(item.num), description: '', specs: '', active: false }) }
async function saveProduct() {
  if (importBusy.value || !importing.value || !importConfirmed.value) return
  importError.value = ''
  try {
    const price = parseMoneyToCents(importForm.price)
    if (!importForm.title.trim() || !importForm.sku.trim()) throw new Error('商品名称与 SKU 必填。')
    if (!/^\d+$/.test(importForm.stock) || !Number.isSafeInteger(Number(importForm.stock)) || Number(importForm.stock) > 1e12 || price > 1e12) throw new Error('价格或库存超出允许范围。')
    if (duplicateSku.value) throw new Error('当前店铺已有相同 SKU，请修改新记录的 SKU，或到商品资料页人工更新原记录。')
    importBusy.value = true
    await props.api.request('/products', { method: 'POST', body: { shop_id: props.shopId, title: importForm.title.trim(), sku: importForm.sku.trim(), price_cents: price, stock: Number(importForm.stock), description: importForm.description.trim(), specs: importForm.specs.trim(), active: importForm.active, expires_at: null, version: 0 } })
    importing.value = null; await props.reload(); props.notify('已保存为新的本地商品资料，没有覆盖原记录。')
  } catch (cause) { importError.value = errorMessage(cause) } finally { importBusy.value = false }
}
function prepareAction() {
  actionError.value = ''
  if (attempt.value || !sessionId.value) return
  if (actionForm.kind === 'push-item' && !/^[1-9]\d*$/.test(actionForm.itemId.trim())) { actionError.value = '淘宝商品 ID 应为正整数字符串。'; return }
  if (actionForm.kind === 'report' && !actionForm.isvName.trim()) { actionError.value = '请填写开放平台注册的公司名称。'; return }
  confirmation.value = true
}
async function sendAction() {
  if (actionBusy.value) return
  if (!attempt.value) {
    if (!confirmation.value || !sessionId.value) return
    const requestId = window.crypto.randomUUID()
    const metrics = { status: Number(actionForm.status), avatar: actionForm.avatar, model_type: Number(actionForm.modelType), isv_name: actionForm.isvName.trim(), ...(actionForm.humanReply === '' ? {} : { open_human_reply: actionForm.humanReply === 'true' }) }
    attempt.value = { kind: actionForm.kind, requestId, body: { shop_id: props.shopId, session_id: sessionId.value, request_id: requestId, ...(actionForm.kind === 'push-item' ? { item_id: actionForm.itemId.trim() } : { metrics }) }, result: null, error: '', attempted: false }
  }
  actionBusy.value = true; confirmation.value = false; attempt.value.attempted = true; attempt.value.error = ''; saveAttempt(props.shopId, attempt.value)
  try { attempt.value.result = await props.api.request<TaobaoAction>('/taobao/' + attempt.value.kind, { method: 'POST', body: attempt.value.body, timeout: 30_000 }); props.notify(attempt.value.result.status === 'succeeded' ? '平台接口返回成功，请在实际平台核对结果。' : '请求结果需要核对，系统不会自动重发。', 'info') }
  catch (cause) { attempt.value.error = errorMessage(cause) }
  finally { actionBusy.value = false; if (attempt.value) saveAttempt(props.shopId, attempt.value) }
}
function finishReview() { if (!reviewed.value || actionBusy.value) return; clearAttempt(props.shopId); attempt.value = null; reviewed.value = false; actionError.value = '' }
const resultLabels = { succeeded: '接口返回成功，待实际平台核对', failed: '接口报告失败', delivery_unknown: '结果不明，禁止自动重发' }
</script>
<template>
  <section class="panel padded"><div class="section-heading"><h2>读取淘宝资料</h2><span class="badge neutral">真实接口 · 缺少授权会拒绝</span></div><div class="form-row"><label>本地绑定场次<select v-model="sessionId"><option value="">先创建并绑定场次</option><option v-for="session in sessions" :key="session.id" :value="session.id">{{ session.title }}</option></select></label><label>出售商品页码<input v-model="page" type="number" min="1" max="1000" step="1" /></label></div><div class="form-actions"><button class="button secondary" :disabled="!!readBusy || !sessionId" @click="read('live-detail')">{{ readBusy === 'live-detail' ? '查询中…' : '查询直播间详情' }}</button><button class="button primary" :disabled="!!readBusy" @click="read('items')">{{ readBusy === 'items' ? '读取中…' : '预览出售商品' }}</button></div><div v-if="readError" class="alert error" role="alert">{{ readError }}</div><details v-if="liveDetail" class="raw-details"><summary>本次直播间详情原始响应</summary><pre>{{ JSON.stringify(liveDetail, null, 2) }}</pre></details><p class="hint">只读取当前应用获准的资料。商品同步先预览，再选中并人工核对后保存；不会静默覆盖。</p></section>
  <section v-if="items" class="panel events-panel"><div class="panel-title"><h2>出售商品预览</h2><span class="muted small-text">平台返回 {{ items.total_results }} 件 · 当前页 {{ page }}</span></div><div v-if="!items.items.length" class="empty-state compact">平台本次没有返回商品。</div><div v-else class="table-scroll"><table><thead><tr><th>名称 / 淘宝 ID</th><th>价格 / 库存</th><th>平台状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in items.items" :key="item.num_iid"><td><strong>{{ item.title }}</strong><div class="secondary-line mono">{{ item.num_iid }}</div></td><td>¥{{ item.price }}<div class="secondary-line">库存 {{ item.num }}</div></td><td>{{ item.approve_status }}</td><td><button class="button secondary small" @click="reviewItem(item)">核对并保存为商品</button></td></tr></tbody></table></div></section>
  <section class="panel padded events-panel"><h2>显式平台操作</h2><p class="page-note">弹卡与上报会产生平台操作。只有你核对当前场次、商品与实际状态后才会发送；媒体连接不作为平台开播证据。</p><div v-if="attempt" class="action-result"><span class="badge" :class="attempt.result?.status === 'succeeded' ? 'success' : 'warning'">{{ attempt.result ? resultLabels[attempt.result.status] : '尚未取得明确结果' }}</span><p>操作：{{ attempt.kind === 'push-item' ? '弹出商品卡' : '上报实际状态' }}</p><p class="mono break-all">request_id：{{ attempt.requestId }}</p><div v-if="attempt.error" class="alert error" role="alert">{{ attempt.error }}</div><p class="hint">保留此 request_id。核对同一请求时不会换号重发；页面刷新会清除浏览器内的记录，请先复制编号以便排查。</p><details class="raw-details"><summary>已发送的固定参数</summary><pre>{{ JSON.stringify(attempt.body, null, 2) }}</pre></details><button class="button secondary" :disabled="actionBusy" @click="sendAction">{{ actionBusy ? '核对中…' : '核对同一请求结果' }}</button><label class="checkbox-row"><input v-model="reviewed" type="checkbox" />我已在实际平台或服务端核对结果，确认可以开始另一项操作</label><button class="button ghost" :disabled="!reviewed || actionBusy" @click="finishReview">结束本次核对，准备新操作</button></div>
  <form v-else class="form-stack platform-action-form" @submit.prevent="prepareAction"><label>操作类型<select v-model="actionForm.kind"><option value="push-item">弹出商品卡</option><option value="report">上报数字人实际状态</option></select></label><label v-if="actionForm.kind === 'push-item'">淘宝商品 item_id<input v-model="actionForm.itemId" inputmode="numeric" required maxlength="32" /></label><template v-else><div class="form-row"><label>实际运行状态<select v-model="actionForm.status"><option :value="1">开始 / start</option><option :value="2">执行中 / running</option><option :value="3">停止 / stop</option></select></label><label>模型类型<select v-model="actionForm.modelType"><option :value="1">公模（多个商家使用）</option><option :value="2">私模</option></select></label></div><label>开放平台注册公司名称<input v-model="actionForm.isvName" required maxlength="160" /></label><label class="checkbox-row"><input v-model="actionForm.avatar" type="checkbox" />当前为阿凡达模式（avatar）</label><label>授权口播（open_human_reply）<select v-model="actionForm.humanReply"><option value="">不提供此可选字段</option><option value="true">是</option><option value="false">否</option></select></label><p class="hint">平台约定每 5 分钟上报；此版本由操作者显式上报真实状态，尚未自动周期上报。</p></template><div v-if="actionError" class="alert error" role="alert">{{ actionError }}</div><button class="button primary" :disabled="!sessionId">核对本次操作</button></form></section>
  <DialogShell v-if="confirmation" title="确认本次平台操作" @close="confirmation = false"><div class="form-stack"><p>场次：{{ sessions.find(s => s.id === sessionId)?.title }}</p><p>{{ actionForm.kind === 'push-item' ? '向绑定直播间弹出商品卡：' + actionForm.itemId : '向绑定直播间上报你填写的实际运行状态。此操作不会替你在淘宝开播或停播。' }}</p><p class="hint">确认后会创建唯一 request_id。网络结果不明时保留同一编号核对，不自动换号重发。</p><div class="form-actions"><button class="button secondary" @click="confirmation = false">返回核对</button><button class="button primary" @click="sendAction">确认并发送到平台</button></div></div></DialogShell>
  <DialogShell v-if="importing" title="人工核对商品预览" @close="!importBusy && (importing = null)"><form class="form-stack" @submit.prevent="saveProduct"><p class="hint">淘宝商品 {{ importing.num_iid }}。保存为新资料，默认停用；不会覆盖已有商品。</p><label>商品名称<input v-model="importForm.title" required maxlength="200" /></label><label>SKU<input v-model="importForm.sku" required maxlength="100" /></label><div v-if="duplicateSku" class="alert warning">已有相同 SKU，请修改或到商品资料页人工更新现有商品。</div><div class="form-row"><label>价格（元）<input v-model="importForm.price" required inputmode="decimal" /></label><label>库存<input v-model="importForm.stock" required inputmode="numeric" /></label></div><label>规格<textarea v-model="importForm.specs" rows="2" maxlength="4000" /></label><label>商品说明<textarea v-model="importForm.description" rows="3" maxlength="4000" /></label><label class="checkbox-row"><input v-model="importForm.active" type="checkbox" />核对后允许用于话术</label><label class="checkbox-row"><input v-model="importConfirmed" type="checkbox" />已核对名称、价格、库存和规格</label><div v-if="importError" class="alert error" role="alert">{{ importError }}</div><div class="form-actions"><button class="button secondary" type="button" :disabled="importBusy" @click="importing = null">取消</button><button class="button primary" :disabled="importBusy || !importConfirmed || duplicateSku">{{ importBusy ? '保存中…' : '保存为新商品' }}</button></div></form></DialogShell>
</template>
