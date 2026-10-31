<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime, jobActions, jobGuard, jobLabels, jobTone, money, productAvailable, sessionLabels } from '../domain'
import type { Job, NoticeSink, Persona, Product, Session, SystemStatus } from '../types'
import DialogShell from './DialogShell.vue'
import Icon from './Icon.vue'
import MediaPreview from './MediaPreview.vue'

const props = defineProps<{ api: ApiClient; shopId: string; products: Product[]; persona: Persona | null; sessions: Session[]; jobs: Job[]; status: SystemStatus; reload: () => Promise<void>; notify: NoticeSink }>()
const emit = defineEmits<{ navigate: [page: 'products' | 'persona' | 'quality'] }>()
const sessionId = ref('')
const creatingSession = ref(false)
const sessionTitle = ref('')
const sessionBusy = ref(false)
const sessionError = ref('')
const takeoverResult = ref('')
const stopFailed = ref(false)
const confirmEnd = ref(false)
const source = ref<'manual' | 'deepseek'>('manual')
const productId = ref('')
const text = ref('')
const question = ref('')
const draftBusy = ref(false)
const draftError = ref('')
const filter = ref('all')
const selectedJobId = ref('')
const actionBusy = ref('')
const actionError = ref('')
const audioURL = ref('')
const audioBusy = ref(false)
const acknowledgement = ref(false)
const mediaConnected = ref(false)
const activeSession = computed(() => props.sessions.find(s => s.id === sessionId.value))
const chosenProduct = computed(() => props.products.find(p => p.id === productId.value))
const sessionJobs = computed(() => props.jobs.filter(j => !sessionId.value || j.session_id === sessionId.value))
const filteredJobs = computed(() => sessionJobs.value.filter(j => filter.value === 'all' || (filter.value === 'review' ? ['draft', 'blocked'].includes(j.status) : filter.value === 'audio' ? ['approved', 'queued', 'synthesizing', 'ready'].includes(j.status) : ['failed', 'delivery_unknown'].includes(j.status))))
const selectedJob = computed(() => props.jobs.find(j => j.id === selectedJobId.value))
const reviewProduct = computed(() => props.products.find(p => p.id === selectedJob.value?.product_id))
const reviewSession = computed(() => props.sessions.find(s => s.id === selectedJob.value?.session_id))
const guard = computed(() => selectedJob.value ? jobGuard(selectedJob.value, reviewProduct.value, props.persona, reviewSession.value) : '')
const actions = computed(() => selectedJob.value ? jobActions(selectedJob.value, guard.value) : null)
const counts = computed(() => ({ review: sessionJobs.value.filter(j => ['draft', 'blocked'].includes(j.status)).length, ready: sessionJobs.value.filter(j => j.status === 'ready').length, sent: sessionJobs.value.filter(j => j.status === 'sent').length }))
const draftDisabled = computed(() => draftBusy.value || activeSession.value?.status !== 'active' || !chosenProduct.value || !productAvailable(chosenProduct.value) || (source.value === 'deepseek' && !props.status.deepseek.configured))

watch(() => props.sessions, sessions => {
  if (!sessions.some(s => s.id === sessionId.value)) sessionId.value = sessions.find(s => s.status === 'active')?.id ?? sessions[0]?.id ?? ''
}, { immediate: true })
watch(() => props.products, products => { if (!products.some(p => p.id === productId.value)) productId.value = products.find(p => productAvailable(p))?.id ?? '' }, { immediate: true })
watch(sessionId, () => { takeoverResult.value = ''; stopFailed.value = false; mediaConnected.value = false; sessionError.value = ''; draftError.value = ''; selectedJobId.value = '' })
watch(selectedJobId, () => { actionError.value = ''; acknowledgement.value = false; releaseAudio() })
watch(() => selectedJob.value?.status, () => { acknowledgement.value = false })
function releaseAudio() { if (audioURL.value) URL.revokeObjectURL(audioURL.value); audioURL.value = '' }
onBeforeUnmount(releaseAudio)

async function createSession() {
  if (!sessionTitle.value.trim() || sessionBusy.value) return
  sessionBusy.value = true; sessionError.value = ''
  try {
    const session = await props.api.request<Session>('/sessions', { method: 'POST', body: { shop_id: props.shopId, title: sessionTitle.value.trim() } })
    await props.reload(); sessionId.value = session.id; creatingSession.value = false; sessionTitle.value = ''
    props.notify('本地场次已创建。淘宝直播仍需在获准平台路径中单独操作。')
  } catch (cause) { sessionError.value = errorMessage(cause) } finally { sessionBusy.value = false }
}
async function sessionAction(action: 'takeover' | 'resume' | 'end') {
  if (!activeSession.value || sessionBusy.value) return
  sessionBusy.value = true; sessionError.value = ''
  try {
    const result = await props.api.request<Session | { session: Session; media_stop_status: 'sent' | 'not_connected' | 'failed' }>('/sessions/' + activeSession.value.id + '/' + action, { method: 'POST', body: { shop_id: props.shopId }, timeout: action === 'resume' ? 30_000 : 65_000 })
    if ((action === 'takeover' || action === 'end') && 'media_stop_status' in result) {
      const prefix = action === 'end' ? '本地场次已结束' : '场次已暂停'
      stopFailed.value = result.media_stop_status === 'failed'
      takeoverResult.value = result.media_stop_status === 'sent' ? prefix + '，停止指令已发送到媒体服务。请在实际接收端确认声音与画面；已被平台缓存的内容无法撤回。' : result.media_stop_status === 'not_connected' ? prefix + '，旧批次任务已取消。本地场次尚未关联媒体连接，请按实际 OBS / 平台链路确认停止。' : prefix + '，但媒体停止请求失败。请立即在 OBS 或媒体服务手动停止输出，并检查实际接收端。'
      if (action === 'end') takeoverResult.value += ' 淘宝直播仍需在平台单独结束。'
    } else { takeoverResult.value = ''; stopFailed.value = false }
    await props.reload(); confirmEnd.value = false
    props.notify(action === 'resume' ? '场次已恢复，请创建新批次的话术。' : action === 'end' ? '本地场次已结束。此操作没有结束淘宝直播。' : '已执行本地暂停与接管。', action === 'takeover' ? 'info' : 'success')
  } catch (cause) { sessionError.value = errorMessage(cause); await props.reload().catch(() => {}) } finally { sessionBusy.value = false }
}
async function createDraft() {
  if (draftDisabled.value) return
  draftError.value = ''
  const value = (source.value === 'manual' ? text.value : question.value).trim()
  if (!value) { draftError.value = source.value === 'manual' ? '请填写人工话术。' : '请填写需要回答的问题。'; return }
  if ([...value].length > 2000) { draftError.value = '内容不能超过 2000 个字符，请缩短后再提交。'; return }
  draftBusy.value = true
  try {
    const body = { shop_id: props.shopId, session_id: sessionId.value, product_id: productId.value, ...(source.value === 'manual' ? { text: value } : { question: value }) }
    const job = await props.api.request<Job>(source.value === 'manual' ? '/jobs/manual' : '/jobs/generate', { method: 'POST', body, timeout: 100_000 })
    await props.reload(); selectedJobId.value = job.id
    if (source.value === 'manual') text.value = ''; else question.value = ''
    props.notify(job.status === 'blocked' ? '生成结果需要人工处理，请查看原因。' : '草稿已保存，核对后才能批准合成。', job.status === 'blocked' ? 'info' : 'success')
  } catch (cause) { draftError.value = errorMessage(cause) } finally { draftBusy.value = false }
}
async function jobAction(action: 'approve' | 'synthesize' | 'send' | 'cancel') {
  if (!selectedJob.value || actionBusy.value) return
  if (action === 'approve' && !acknowledgement.value) return
  if (action === 'send' && (!mediaConnected.value || reviewSession.value?.id !== activeSession.value?.id)) { actionError.value = '当前场次没有已连通的媒体预览，请重新连接后再派发。'; return }
  actionBusy.value = action; actionError.value = ''
  try {
    const job = await props.api.request<Job>('/jobs/' + selectedJob.value.id + '/' + action, { method: 'POST', body: { shop_id: props.shopId }, timeout: action === 'send' ? 65_000 : 30_000 })
    await props.reload()
    if (job.status === 'delivery_unknown') actionError.value = '派发结果不明，请先在媒体端核对，必要时接管。系统不会自动重播。'
    props.notify(action === 'approve' ? '已批准，可排队合成本地语音。' : action === 'synthesize' ? '任务已进入持久化合成队列。' : action === 'cancel' ? '任务已取消。' : job.status === 'sent' ? '媒体上游已接收。请在实际接收端确认是否播出。' : '任务状态已更新。', action === 'send' ? 'info' : 'success')
  } catch (cause) { actionError.value = errorMessage(cause); await props.reload().catch(() => {}) } finally { actionBusy.value = '' }
}
async function previewAudio() {
  if (!selectedJob.value || audioBusy.value) return
  const id = selectedJob.value.id
  audioBusy.value = true; actionError.value = ''
  try {
    const blob = await props.api.audio(id, props.shopId)
    if (selectedJobId.value !== id) return
    releaseAudio(); audioURL.value = URL.createObjectURL(blob)
  } catch (cause) { actionError.value = errorMessage(cause) } finally { audioBusy.value = false }
}
function copyToDraft() {
  if (!selectedJob.value) return
  text.value = selectedJob.value.text; productId.value = selectedJob.value.product_id; source.value = 'manual'; selectedJobId.value = ''
  props.notify('内容已带入人工话术。核对当前商品与场次后，保存为新草稿。', 'info')
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">LIVE OPERATIONS</div><h1>直播工作台</h1><p>从一条可靠的话术，到一次可控的播报。</p></div><button class="button secondary" @click="creatingSession = true; sessionError = ''"><Icon name="plus" :size="18" />新建场次</button></div>
  <section class="session-bar panel"><div class="session-selector"><label for="session-select">当前本地场次</label><select id="session-select" v-model="sessionId" :disabled="!sessions.length"><option v-if="!sessions.length" value="">尚未创建场次</option><option v-for="session in sessions" :key="session.id" :value="session.id">{{ session.title }} · {{ sessionLabels[session.status] }}</option></select></div><div v-if="activeSession" class="session-state"><span class="badge" :class="activeSession.status === 'active' ? 'success' : 'neutral'"><span class="status-dot" />{{ sessionLabels[activeSession.status] }}</span><span class="muted small-text">执行批次 {{ activeSession.epoch }}</span></div><div class="session-actions"><button v-if="activeSession?.status === 'active'" class="button takeover" :disabled="sessionBusy" @click="sessionAction('takeover')"><Icon name="pause" :size="17" />暂停并接管</button><button v-else-if="activeSession?.status === 'paused'" class="button primary" :disabled="sessionBusy" @click="sessionAction('resume')"><Icon name="play" :size="16" />恢复场次</button><button v-if="activeSession && activeSession.status !== 'ended'" class="button ghost small" :disabled="sessionBusy" @click="confirmEnd = true">结束本地场次</button></div></section>
  <div v-if="sessionError && !creatingSession" class="alert error" role="alert">{{ sessionError }}</div>
  <div v-if="takeoverResult" class="alert" :class="stopFailed ? 'error' : 'warning'" :role="stopFailed ? 'alert' : 'status'">{{ takeoverResult }}</div>
  <div v-if="!sessions.length" class="info-strip"><Icon name="plus" :size="18" /><span>开始前先创建一个本地场次，再选择商品、准备草稿。</span><button class="inline-button" @click="creatingSession = true">创建场次 →</button></div>
  <div class="studio-grid">
    <MediaPreview :api="api" :shop-id="shopId" :session="activeSession" :configured="status.media.live_configured" @connected="reload" @connection-state="mediaConnected = $event" />
    <section class="panel composer"><div class="panel-title"><h2><Icon name="edit" :size="19" />准备下一条话术</h2><span class="badge neutral">先审核，再播报</span></div><form class="form-stack" @submit.prevent="createDraft"><div class="segmented full"><button type="button" :class="{ active: source === 'manual' }" @click="source = 'manual'">人工话术</button><button type="button" :class="{ active: source === 'deepseek' }" @click="source = 'deepseek'"><Icon name="bolt" :size="15" />DeepSeek 草稿</button></div><label>关联商品<select v-model="productId"><option value="" disabled>{{ products.length ? '请选择商品' : '先添加商品资料' }}</option><option v-for="product in products" :key="product.id" :value="product.id" :disabled="!productAvailable(product)">{{ product.title }} · {{ money(product.price_cents) }}{{ productAvailable(product) ? '' : '（不可用）' }}</option></select></label><div v-if="chosenProduct" class="fact-strip"><span>{{ money(chosenProduct.price_cents) }}</span><span>库存 {{ chosenProduct.stock }}</span><span>商品 v{{ chosenProduct.version }}</span><span>人格 v{{ persona?.version ?? '—' }}</span></div><div v-else class="small-text muted">没有可用商品？<button type="button" class="inline-button" @click="emit('navigate', 'products')">前往添加</button></div><label v-if="source === 'manual'">话术内容<textarea v-model="text" rows="4" maxlength="2000" placeholder="填写经过核对的讲解或插播内容，保存后仍需人工批准。" /></label><label v-else>需要回答的问题<textarea v-model="question" rows="4" maxlength="2000" placeholder="填写现场问题。这里只接收人工输入，尚未自动接入淘宝评论。" /></label><div v-if="source === 'deepseek' && !status.deepseek.configured" class="alert warning">DeepSeek 尚未配置。可先使用人工话术，或配置后刷新状态。</div><div v-if="draftError" class="alert error" role="alert">{{ draftError }}</div><div class="composer-bottom"><span class="muted small-text">{{ [...(source === 'manual' ? text : question)].length }} / 2000 字符</span><button class="button primary" :disabled="draftDisabled"><Icon :name="source === 'manual' ? 'plus' : 'bolt'" :size="16" />{{ draftBusy ? '正在创建草稿…' : source === 'manual' ? '保存待审核草稿' : '生成待审核草稿' }}</button></div></form></section>
  </div>
  <section class="panel jobs-panel"><div class="panel-title"><div><h2><Icon name="book" :size="19" />播报任务</h2><p class="section-caption">持久保存 · 当前场次 · 店铺最近 100 条范围</p></div><div class="queue-counts"><span><b>{{ counts.review }}</b> 待处理</span><span><b>{{ counts.ready }}</b> 音频就绪</span><span><b>{{ counts.sent }}</b> 上游接收</span></div></div><div class="panel-toolbar"><div class="segmented"><button v-for="option in [{ key: 'all', label: '全部' }, { key: 'review', label: '待审核 / 人工处理' }, { key: 'audio', label: '合成与音频' }, { key: 'errors', label: '异常' }]" :key="option.key" :class="{ active: filter === option.key }" @click="filter = option.key">{{ option.label }}</button></div></div><div v-if="!filteredJobs.length" class="empty-state compact"><div class="empty-icon"><Icon name="wave" :size="28" /></div><h3>{{ sessionJobs.length ? '当前分类没有任务' : '还没有播报任务' }}</h3><p>{{ sessionJobs.length ? '切换分类查看已保存的其他任务。' : '在上方准备话术，保存后在这里审核、合成与派发。' }}</p></div><div v-else class="table-scroll"><table class="job-table"><thead><tr><th>话术与关联商品</th><th>状态</th><th>来源 / 时间</th><th>操作</th></tr></thead><tbody><tr v-for="job in filteredJobs" :key="job.id"><td><button class="job-text-button" @click="selectedJobId = job.id">{{ job.text || job.reason || '无可用草稿内容' }}</button><div class="secondary-line">{{ products.find(p => p.id === job.product_id)?.title || '关联商品不可用' }} · 商品 v{{ job.product_version }} · 批次 {{ job.epoch }}</div></td><td><span class="badge" :class="jobTone(job.status)">{{ jobLabels[job.status] || job.status }}</span></td><td><span class="small-text">{{ job.source === 'deepseek' ? 'DeepSeek' : '人工话术' }}</span><div class="secondary-line">{{ dateTime(job.created_at) }}</div></td><td><button class="button ghost small" @click="selectedJobId = job.id">{{ job.status === 'draft' ? '审核' : '查看' }}<Icon name="arrow" :size="16" /></button></td></tr></tbody></table></div><div class="panel-footer">“上游已接收”只表示媒体服务接受了音频。请在淘宝实际接收端确认声音和画面。</div></section>
  <DialogShell v-if="creatingSession" title="新建本地场次" @close="!sessionBusy && (creatingSession = false)"><form class="form-stack" @submit.prevent="createSession"><p class="hint">用于管理话术、版本和媒体连接。此操作不会在淘宝开播。</p><div v-if="sessionError" class="alert error" role="alert">{{ sessionError }}</div><label>场次名称<input v-model="sessionTitle" required maxlength="160" placeholder="例如：周末产品讲解" /></label><div class="form-actions"><button type="button" class="button secondary" :disabled="sessionBusy" @click="creatingSession = false">取消</button><button class="button primary" :disabled="sessionBusy || !sessionTitle.trim()">{{ sessionBusy ? '正在创建…' : '创建场次' }}</button></div></form></DialogShell>
  <DialogShell v-if="confirmEnd" title="结束当前本地场次？" @close="!sessionBusy && (confirmEnd = false)"><div class="form-stack"><p>结束后不能恢复此场次，未派发任务不能继续执行。此操作不会结束淘宝直播，请在淘宝客户端单独操作。</p><div v-if="sessionError" class="alert error" role="alert">{{ sessionError }}</div><div class="form-actions"><button class="button secondary" :disabled="sessionBusy" @click="confirmEnd = false">继续运营</button><button class="button danger" :disabled="sessionBusy" @click="sessionAction('end')">{{ sessionBusy ? '正在结束…' : '结束本地场次' }}</button></div></div></DialogShell>
  <DialogShell v-if="selectedJob" title="审核与播报" wide @close="!actionBusy && (selectedJobId = '')"><div class="review-content"><div class="review-meta"><span class="badge" :class="jobTone(selectedJob.status)">{{ jobLabels[selectedJob.status] }}</span><span>{{ selectedJob.source === 'deepseek' ? 'DeepSeek 生成' : '人工创建' }}</span><span>{{ dateTime(selectedJob.created_at) }}</span></div><div v-if="selectedJob.question" class="review-question"><span class="field-caption">原始问题</span><p>{{ selectedJob.question }}</p></div><div class="speech-copy">{{ selectedJob.text || '此任务没有可供审批的话术。' }}</div><div v-if="selectedJob.reason" class="alert warning">{{ selectedJob.reason }}</div><div v-if="selectedJob.status === 'delivery_unknown'" class="alert error">派发结果不明。请先核对媒体服务与实际接收端；此任务不能直接重新派发，以免重复播报。</div><div v-if="guard && !['sent', 'cancelled'].includes(selectedJob.status)" class="alert warning">{{ guard }}</div><section class="review-facts"><div class="section-heading"><Icon name="box" :size="18" /><h3>当前商品事实 · 人工核对</h3><span v-if="reviewProduct" class="badge neutral">v{{ reviewProduct.version }}</span></div><template v-if="reviewProduct"><h3>{{ reviewProduct.title }}</h3><div class="fact-strip"><span>{{ money(reviewProduct.price_cents) }}</span><span>库存 {{ reviewProduct.stock }}</span><span>SKU {{ reviewProduct.sku }}</span></div><p v-if="reviewProduct.specs">{{ reviewProduct.specs }}</p><p v-if="reviewProduct.description">{{ reviewProduct.description }}</p><p class="small-text muted">{{ reviewProduct.expires_at ? '有效至 ' + dateTime(reviewProduct.expires_at) : '未指定有效期' }} · 任务使用商品 v{{ selectedJob.product_version }} / 人格 v{{ selectedJob.persona_version }}</p></template><p v-else>关联商品当前不可用，无法继续审批。</p></section><p class="hint">草稿未被自动证明事实无误。请核对价格、规格、优惠及承诺；需要修改时，复制为新草稿重新审核。</p><label v-if="actions?.approve" class="checkbox-row approval-check"><input v-model="acknowledgement" type="checkbox" />我已核对话术与当前商品事实，确认允许合成。</label><div v-if="!status.media.tts_configured && actions?.synthesize" class="alert warning">本地语音服务尚未配置，暂时无法合成。</div><div v-if="actions?.send && (!status.media.live_configured || !reviewSession?.media_session_id || !mediaConnected || reviewSession?.id !== activeSession?.id)" class="alert warning">先在当前场次连接媒体预览，确认连接成功后再发送。保留的媒体会话编号不代表连接仍然有效。</div><div v-if="actionError" class="alert error" role="alert">{{ actionError }}</div><div v-if="audioURL" class="audio-review"><span class="field-caption">本机音频试听 · 不会发送到媒体服务</span><audio :src="audioURL" controls preload="metadata" /></div><div class="review-actions"><button v-if="actions?.approve" class="button primary" :disabled="!!actionBusy || !acknowledgement" @click="jobAction('approve')">{{ actionBusy === 'approve' ? '正在批准…' : '批准话术' }}</button><button v-if="actions?.synthesize" class="button primary" :disabled="!!actionBusy || !status.media.tts_configured" @click="jobAction('synthesize')">{{ actionBusy === 'synthesize' ? '正在入队…' : '合成本地语音' }}</button><button v-if="actions?.audio" class="button secondary" :disabled="audioBusy" @click="previewAudio"><Icon name="sound" :size="17" />{{ audioBusy ? '加载音频…' : '试听音频' }}</button><button v-if="actions?.send" class="button primary" :disabled="!!actionBusy || !status.media.live_configured || !reviewSession?.media_session_id || !mediaConnected || reviewSession?.id !== activeSession?.id" @click="jobAction('send')">{{ actionBusy === 'send' ? '正在派发…' : '发送到媒体' }}</button><button v-if="selectedJob.text" class="button ghost" :disabled="!!actionBusy" @click="copyToDraft">复制为新草稿</button><button v-if="actions?.cancel" class="button ghost danger-text" :disabled="!!actionBusy" @click="jobAction('cancel')">{{ actionBusy === 'cancel' ? '正在取消…' : '取消任务' }}</button></div><div class="review-footnote"><span>任务 {{ selectedJob.id }}</span><span v-if="selectedJob.source === 'deepseek'">输入 {{ selectedJob.input_tokens }} / 输出 {{ selectedJob.output_tokens }} tokens</span><span v-if="selectedJob.error_code">错误代码 {{ selectedJob.error_code }}</span></div></div></DialogShell>
</template>
