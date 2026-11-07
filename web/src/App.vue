<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ApiClient, errorMessage } from './api'
import type { Job, Persona, Product, QualityProfile, Session, Shop, SystemStatus } from './types'
import DialogShell from './components/DialogShell.vue'
import Icon from './components/Icon.vue'
import KnowledgeRecordsView from './business/KnowledgeRecordsView.vue'
import PromotionsView from './business/PromotionsView.vue'
import AssetsView from './business/AssetsView.vue'
import CostView from './business/CostView.vue'
import SchedulerView from './business/SchedulerView.vue'
import TemplatesView from './business/TemplatesView.vue'
import IntegrationsView from './integrations/IntegrationsView.vue'
import { clearActionLedger } from './integrations/actionLedger'
import PersonaView from './components/PersonaView.vue'
import ProductsView from './components/ProductsView.vue'
import QualityView from './components/QualityView.vue'
import WorkbenchView from './components/WorkbenchView.vue'
import LiveReadinessView from './readiness/LiveReadinessView.vue'

type Page = 'studio' | 'products' | 'persona' | 'knowledge' | 'quality' | 'promotions' | 'assets' | 'cost' | 'integrations' | 'scheduler' | 'templates' | 'readiness'
const api = new ApiClient()
const authenticated = ref(false)
const tokenInput = ref('')
const loginBusy = ref(false)
const loginError = ref('')
const status = ref<SystemStatus | null>(null)
const shops = ref<Shop[]>([])
const shopId = ref('')
const page = ref<Page>('studio')
const products = ref<Product[]>([])
const persona = ref<Persona | null>(null)
const sessions = ref<Session[]>([])
const jobs = ref<Job[]>([])
const quality = ref<QualityProfile | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const globalError = ref('')
const shopDialog = ref(false)
const shopName = ref('')
const shopBusy = ref(false)
const shopError = ref('')
const toast = ref<{ message: string; kind: string } | null>(null)
const showDiagnostics = ref(false)
let toastTimer: number | undefined
let dataRevision = 0
let pollBusy = false
const selectedShop = computed(() => shops.value.find(s => s.id === shopId.value))
const nav = [
  { key: 'studio' as const, label: '直播工作台', icon: 'studio' },
  { key: 'products' as const, label: '商品资料', icon: 'box' },
  { key: 'promotions' as const, label: '活动管理', icon: 'clock' },
  { key: 'templates' as const, label: '话术模板', icon: 'book' },
  { key: 'persona' as const, label: '品牌人格', icon: 'person' },
  { key: 'knowledge' as const, label: '知识与记忆', icon: 'book' },
  { key: 'assets' as const, label: '资产与音色', icon: 'person' },
  { key: 'quality' as const, label: '画质核验', icon: 'shield' },
  { key: 'scheduler' as const, label: '调度与额度', icon: 'clock' },
  { key: 'cost' as const, label: '用量与成本', icon: 'box' },
  { key: 'integrations' as const, label: '联调与淘宝', icon: 'refresh' },
  { key: 'readiness' as const, label: '开播验证', icon: 'shield' },
]
const taobaoLabel = computed(() => {
  const value = status.value?.taobao.status
  if (!value || ['not_connected', 'not_configured', 'not_implemented', 'unconfigured', 'pending', 'unavailable', 'not_integrated'].includes(value)) return '淘宝未接入'
  return ({ configured_unverified: '淘宝已配置 · 待核验', last_poll_succeeded: '淘宝消息最近拉取成功', poll_failed: '淘宝消息拉取失败' } as Record<string, string>)[value] ?? '淘宝状态：' + value
})
const retrievalLabel = computed(() => ['keyword', 'keyword_search', 'keywords'].includes(status.value?.retrieval.mode ?? '') ? '关键词检索' : '检索：' + (status.value?.retrieval.mode || '未知'))
function notify(message: string, kind: 'success' | 'error' | 'info' = 'success') {
  if (toastTimer !== undefined) window.clearTimeout(toastTimer)
  toast.value = { message, kind }
  toastTimer = window.setTimeout(() => { toast.value = null }, 7000)
}
function clearShopData() { products.value = []; persona.value = null; sessions.value = []; jobs.value = []; quality.value = null }
function logout(message = '') {
  dataRevision++; clearActionLedger(); api.clearToken(); authenticated.value = false; tokenInput.value = ''; shops.value = []; shopId.value = ''; status.value = null; clearShopData(); globalError.value = ''; toast.value = null; shopDialog.value = false; showDiagnostics.value = false; loginError.value = message
}
api.onUnauthorized = () => { if (authenticated.value) logout('口令已失效，请重新输入工作台口令。') }
async function login() {
  if (loginBusy.value || !tokenInput.value.trim()) return
  loginBusy.value = true; loginError.value = ''
  api.setToken(tokenInput.value)
  try {
    const [serverStatus, shopList] = await Promise.all([api.request<SystemStatus>('/status'), api.request<Shop[]>('/shops')])
    status.value = serverStatus; shops.value = shopList; authenticated.value = true; tokenInput.value = ''
    shopId.value = shopList[0]?.id ?? ''
  } catch (cause) { api.clearToken(); loginError.value = errorMessage(cause) } finally { loginBusy.value = false }
}
async function reloadShop() {
  if (!shopId.value || !authenticated.value) return
  const id = shopId.value
  const revision = ++dataRevision
  const query = { shop_id: id }
  try {
    const [nextProducts, nextPersona, nextSessions, nextJobs, nextQuality] = await Promise.all([
      api.request<Product[]>('/products', { query }), api.request<Persona>('/persona', { query }),
      api.request<Session[]>('/sessions', { query }),
      api.request<Job[]>('/jobs', { query }), api.request<QualityProfile>('/quality', { query }),
    ])
    if (revision !== dataRevision || id !== shopId.value || !authenticated.value) return
    products.value = nextProducts ?? []; persona.value = nextPersona; sessions.value = nextSessions ?? []; jobs.value = nextJobs ?? []; quality.value = nextQuality
    globalError.value = ''
  } catch (cause) { if (revision === dataRevision && authenticated.value) globalError.value = errorMessage(cause) }
}
watch(shopId, async () => { clearShopData(); globalError.value = ''; loading.value = true; await reloadShop(); loading.value = false })
async function refresh() {
  if (refreshing.value || !authenticated.value) return
  refreshing.value = true
  try {
    const [serverStatus, shopList] = await Promise.all([api.request<SystemStatus>('/status'), api.request<Shop[]>('/shops')])
    if (!authenticated.value) return
    status.value = serverStatus; shops.value = shopList
    if (!shopList.some(s => s.id === shopId.value)) shopId.value = shopList[0]?.id ?? ''
    await reloadShop()
  } catch (cause) { if (authenticated.value) globalError.value = errorMessage(cause) } finally { refreshing.value = false }
}
async function createShop() {
  if (!shopName.value.trim() || shopBusy.value) return
  shopBusy.value = true; shopError.value = ''
  try {
    const shop = await api.request<Shop>('/shops', { method: 'POST', body: { name: shopName.value.trim() } })
    shops.value = [...shops.value, shop]; shopId.value = shop.id; page.value = 'products'; shopName.value = ''; shopDialog.value = false
    notify('店铺已创建。先添加商品，再配置人格与知识。')
  } catch (cause) { shopError.value = errorMessage(cause) } finally { shopBusy.value = false }
}
const timer = window.setInterval(async () => {
  if (!authenticated.value || !shopId.value || document.visibilityState === 'hidden' || pollBusy || loading.value) return
  const id = shopId.value
  const revision = dataRevision
  pollBusy = true
  try {
    const [nextJobs, nextSessions] = await Promise.all([api.request<Job[]>('/jobs', { query: { shop_id: id } }), api.request<Session[]>('/sessions', { query: { shop_id: id } })])
    if (authenticated.value && id === shopId.value && revision === dataRevision) { jobs.value = nextJobs ?? []; sessions.value = nextSessions ?? [] }
  } catch (cause) { if (authenticated.value && id === shopId.value) globalError.value = '任务状态刷新失败：' + errorMessage(cause) } finally { pollBusy = false }
}, 5000)
onBeforeUnmount(() => { window.clearInterval(timer); if (toastTimer !== undefined) window.clearTimeout(toastTimer); api.clearToken() })
</script>

<template>
  <main v-if="!authenticated" class="login-shell">
    <div class="login-story"><div class="brand"><span class="brand-mark">声</span><div><strong>数字人工作台</strong><span>LOCAL OPERATIONS</span></div></div><div class="login-intro"><div class="eyebrow">YOUR VOICE. YOUR WORKSPACE.</div><h1>让每一次开口，<br />都有据可依。</h1><p>商品、人格与知识留在自己的工作台。<br />每条话术经你确认，再交给数字人表达。</p><div class="login-workflow"><span>准备事实</span><i /><span>审核话术</span><i /><span>控制播报</span></div></div><div class="login-footer">本地运营 · 单操作者 · v0.2</div></div>
    <section class="login-form-wrap"><div class="login-card"><div class="login-lock"><Icon name="lock" :size="24" /></div><div class="eyebrow">WELCOME BACK</div><h2>进入本地工作台</h2><p>使用服务启动时设置的工作台口令。</p><form class="form-stack" @submit.prevent="login"><label>工作台口令<input v-model="tokenInput" type="password" name="workspace-token" autocomplete="current-password" autofocus required placeholder="输入工作台口令" /></label><div v-if="loginError" class="alert error" role="alert">{{ loginError }}</div><button class="button primary login-submit" :disabled="loginBusy || !tokenInput.trim()">{{ loginBusy ? '正在验证…' : '进入工作台' }}<Icon name="arrow" :size="18" /></button></form><div class="login-security"><Icon name="shield" :size="17" /><span>口令只保存在当前页面内存，刷新后需要重新输入。</span></div><p class="login-boundary">这是本地管理入口。登录不会连接淘宝账户，也不会开始直播。</p></div></section>
  </main>
  <div v-else-if="status" class="app-shell">
    <aside class="sidebar"><a class="brand" href="#" @click.prevent="page = 'studio'"><span class="brand-mark">声</span><div><strong>数字人工作台</strong><span>LOCAL OPERATIONS</span></div></a><div class="shop-switcher"><label for="shop-select">当前店铺</label><select id="shop-select" v-model="shopId" aria-label="切换店铺" :disabled="!shops.length"><option v-if="!shops.length" value="">尚未创建店铺</option><option v-for="shop in shops" :key="shop.id" :value="shop.id">{{ shop.name }}</option></select><button class="add-shop" @click="shopDialog = true; shopError = ''"><Icon name="plus" :size="15" />新建店铺</button></div><div class="nav-label">运营空间</div><nav class="main-nav" aria-label="工作台导航"><button v-for="item in nav" :key="item.key" :class="{ active: page === item.key }" :aria-current="page === item.key ? 'page' : undefined" @click="page = item.key"><Icon :name="item.icon" :size="20" /><span>{{ item.label }}</span><span v-if="page === item.key" class="nav-indicator" /></button></nav><div class="sidebar-bottom"><div class="local-badge"><span class="status-dot" />本地服务已连接</div><p>单操作者 · 多店资料管理</p><button class="sidebar-logout" @click="logout()"><Icon name="logout" :size="17" />退出工作台</button></div></aside>
    <div class="main-shell"><header class="topbar"><div class="breadcrumb">运营空间<span>/</span><strong>{{ selectedShop?.name || '初始化工作台' }}</strong></div><div class="topbar-actions"><span class="version-label">v{{ status.version.replace(/^v/, '') }}</span><button class="icon-button" :class="{ spinning: refreshing }" :disabled="refreshing" aria-label="刷新服务状态与资料" @click="refresh"><Icon name="refresh" :size="18" /></button><a class="button ghost small" href="/avatar3d" target="_blank" rel="noopener">3D 验证室</a><button class="button ghost small" @click="showDiagnostics = true">服务状态</button><span class="operator-avatar" title="本地操作者">本</span></div></header>
      <div class="capability-bar"><span class="capability" :class="status.deepseek.configured ? 'available' : 'unavailable'"><span class="status-dot" />DeepSeek {{ status.deepseek.configured ? '已配置' : '未配置' }}</span><span class="capability" :class="status.media.tts_configured ? 'available' : 'unavailable'"><span class="status-dot" />本地语音 {{ status.media.tts_configured ? '已配置' : '未配置' }}</span><span class="capability" :class="status.media.live_configured ? 'available' : 'unavailable'"><span class="status-dot" />媒体 {{ status.media.live_configured ? '已配置' : '未配置' }}</span><span class="capability neutral"><span class="status-dot" />{{ taobaoLabel }}</span><span class="capability neutral retrieval">{{ retrievalLabel }}</span></div>
      <main class="page-content"><div v-if="globalError" class="alert error global-alert" role="alert"><span>{{ globalError }}</span><button class="inline-button" @click="refresh">重新刷新</button><button class="icon-button" aria-label="关闭提示" @click="globalError = ''"><Icon name="close" :size="16" /></button></div><div v-if="!shops.length" class="welcome-empty panel"><div class="empty-icon large"><Icon name="studio" :size="38" /></div><div class="eyebrow">START WITH YOUR FIRST SHOP</div><h1>建立你的第一个运营空间</h1><p>每家店独立保存商品、人格、知识与场次。<br />创建店铺后，从一件商品和一条人工话术开始。</p><button class="button primary" @click="shopDialog = true; shopError = ''"><Icon name="plus" :size="18" />创建第一家店铺</button><div class="onboarding-steps"><span><b>01</b>录入商品</span><span><b>02</b>配置人格</span><span><b>03</b>创建场次</span></div></div><div v-else-if="loading" class="loading-state" role="status"><span class="spinner" /><p>正在读取店铺资料…</p></div><template v-else-if="shopId"><WorkbenchView v-if="page === 'studio'" :key="'studio-' + shopId" :api="api" :shop-id="shopId" :products="products" :persona="persona" :sessions="sessions" :jobs="jobs" :status="status" :reload="reloadShop" :notify="notify" @navigate="page = $event" /><ProductsView v-else-if="page === 'products'" :key="'products-' + shopId" :api="api" :shop-id="shopId" :products="products" :reload="reloadShop" :notify="notify" /><PersonaView v-else-if="page === 'persona'" :key="'persona-' + shopId" :api="api" :shop-id="shopId" :persona="persona" :reload="reloadShop" :notify="notify" /><KnowledgeRecordsView v-else-if="page === 'knowledge'" :key="'knowledge-' + shopId" :api="api" :shop-id="shopId" :products="products" :sessions="sessions" :reload="reloadShop" :notify="notify" /><PromotionsView v-else-if="page === 'promotions'" :key="'promotions-' + shopId" :api="api" :shop-id="shopId" :products="products" :reload="reloadShop" :notify="notify" /><AssetsView v-else-if="page === 'assets'" :key="'assets-' + shopId" :api="api" :shop-id="shopId" :reload="reloadShop" :notify="notify" /><CostView v-else-if="page === 'cost'" :key="'cost-' + shopId" :api="api" :shop-id="shopId" :sessions="sessions" :notify="notify" /><TemplatesView v-else-if="page === 'templates'" :key="'templates-' + shopId" :api="api" :shop-id="shopId" :products="products" :sessions="sessions" :reload="reloadShop" :notify="notify" /><SchedulerView v-else-if="page === 'scheduler'" :key="'scheduler-' + shopId" :api="api" :shop-id="shopId" :jobs="jobs" :sessions="sessions" :reload="reloadShop" :notify="notify" /><IntegrationsView v-else-if="page === 'integrations'" :key="'integrations-' + shopId" :api="api" :shop-id="shopId" :products="products" :sessions="sessions" :reload="reloadShop" :notify="notify" /><LiveReadinessView v-else-if="page === 'readiness'" :key="'readiness-' + shopId" :api="api" :shop-id="shopId" :notify="notify" /><QualityView v-else :key="'quality-' + shopId" :api="api" :shop-id="shopId" :quality="quality" :reload="reloadShop" :notify="notify" /></template></main><footer class="workspace-footer"><span>LOCAL FIRST · HUMAN APPROVED</span><span>淘宝正式接入与目标硬件验收，以实际验证记录为准。</span></footer>
    </div>
    <DialogShell v-if="shopDialog" title="创建店铺空间" @close="!shopBusy && (shopDialog = false)"><form class="form-stack" @submit.prevent="createShop"><p class="hint">独立保存这家店的商品、人格、知识和播报任务。这里只创建本地配置，不会授权淘宝账户。</p><label>店铺名称<input v-model="shopName" required maxlength="100" placeholder="填写便于识别的店铺名称" /></label><div v-if="shopError" class="alert error" role="alert">{{ shopError }}</div><div class="form-actions"><button type="button" class="button secondary" :disabled="shopBusy" @click="shopDialog = false">取消</button><button class="button primary" :disabled="shopBusy || !shopName.trim()">{{ shopBusy ? '正在创建…' : '创建店铺' }}</button></div></form></DialogShell>
    <DialogShell v-if="showDiagnostics" title="服务状态" @close="showDiagnostics = false"><div class="form-stack"><p class="hint">“已配置”表示后端存在对应配置，不代表模型已加载、GPU 已验证或媒体已连通。实际连接结果请在工作台查看。</p><dl class="diagnostics"><div><dt>业务服务</dt><dd>{{ status.version }}</dd></div><div><dt>数据存储</dt><dd>{{ status.storage }}</dd></div><div><dt>DeepSeek</dt><dd>{{ status.deepseek.configured ? '已配置 · ' + status.deepseek.model : '未配置' }}</dd></div><div><dt>本地语音</dt><dd>{{ status.media.tts_configured ? '已配置，需实测' : '未配置 TTS 服务' }}</dd></div><div><dt>LiveTalking</dt><dd>{{ status.media.live_configured ? '已配置，需连接预览' : '未配置媒体服务' }}</dd></div><div><dt>淘宝</dt><dd>{{ taobaoLabel }}</dd></div><div><dt>检索</dt><dd>{{ retrievalLabel }} · 可在联调页验证实际检索结果</dd></div></dl><div class="info-strip">本地语音不可用时不会自动切换到其他付费服务。</div><div class="form-actions"><button class="button primary" :disabled="refreshing" @click="refresh">{{ refreshing ? '正在刷新…' : '重新检查配置' }}</button></div></div></DialogShell>
    <Transition name="toast"><div v-if="toast" class="toast-message" :class="toast.kind" role="status"><Icon :name="toast.kind === 'success' ? 'check' : 'shield'" :size="19" /><span>{{ toast.message }}</span><button class="icon-button" aria-label="关闭通知" @click="toast = null"><Icon name="close" :size="16" /></button></div></Transition>
  </div>
</template>
