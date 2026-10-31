<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime } from '../domain'
import type { Knowledge, NoticeSink } from '../types'
import DialogShell from './DialogShell.vue'
import Icon from './Icon.vue'

const props = defineProps<{ api: ApiClient; shopId: string; knowledge: Knowledge[]; reload: () => Promise<void>; notify: NoticeSink }>()
const filter = ref<'all' | 'faq' | 'memory'>('all')
const search = ref('')
const open = ref(false)
const editing = ref<Knowledge | null>(null)
const deleting = ref<Knowledge | null>(null)
const busy = ref(false)
const error = ref('')
const form = reactive({ title: '', content: '', kind: 'faq' as Knowledge['kind'] })
const filtered = computed(() => props.knowledge.filter(k => (filter.value === 'all' || filter.value === k.kind) && (k.title + k.content).toLowerCase().includes(search.value.toLowerCase())))
function edit(item: Knowledge | null) {
  editing.value = item
  Object.assign(form, item ? { title: item.title, content: item.content, kind: item.kind } : { title: '', content: '', kind: filter.value === 'memory' ? 'memory' : 'faq' })
  error.value = ''; open.value = true
}
async function save() {
  if (busy.value) return
  error.value = ''
  if (!form.title.trim() || !form.content.trim()) { error.value = '请填写标题和内容。'; return }
  busy.value = true
  try {
    await props.api.request(editing.value ? '/knowledge/' + editing.value.id : '/knowledge', { method: editing.value ? 'PUT' : 'POST', body: { shop_id: props.shopId, title: form.title.trim(), content: form.content.trim(), kind: form.kind } })
    await props.reload(); open.value = false; props.notify('知识已保存，后续生成会使用当前资料。')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
async function remove() {
  if (!deleting.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    await props.api.request('/knowledge/' + deleting.value.id, { method: 'DELETE', query: { shop_id: props.shopId } })
    await props.reload(); deleting.value = null; props.notify('条目已删除。请同时核对尚未派发的旧草稿内容。')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">KNOWLEDGE & MEMORY</div><h1>知识与记忆</h1><p>把常见问题和品牌偏好，整理成可核对、可更正的资料。</p></div><button class="button primary" @click="edit(null)"><Icon name="plus" />新增条目</button></div>
  <div class="info-strip"><Icon name="book" :size="19" /><span>当前采用关键词检索。人工记忆由你维护，不会自动学习临时评论。</span></div>
  <section class="panel">
    <div class="panel-toolbar"><div class="segmented"><button v-for="option in [{ key: 'all', label: '全部' }, { key: 'faq', label: '常见问题' }, { key: 'memory', label: '人工记忆' }]" :key="option.key" :class="{ active: filter === option.key }" @click="filter = option.key as typeof filter">{{ option.label }}</button></div><div class="search-field compact-search"><Icon name="search" /><input v-model="search" aria-label="搜索知识" placeholder="搜索资料" /></div></div>
    <div v-if="!knowledge.length" class="empty-state"><div class="empty-icon"><Icon name="book" :size="32" /></div><h3>给数字人一份可靠的参考</h3><p>录入售后规则、产品问答或品牌表达偏好。</p><button class="button secondary" @click="edit(null)">新增第一条资料<Icon name="arrow" :size="17" /></button></div>
    <div v-else-if="!filtered.length" class="empty-state compact"><h3>没有匹配的条目</h3><p>调整分类或关键词后再试。</p></div>
    <div v-else class="knowledge-list"><article v-for="item in filtered" :key="item.id" class="knowledge-item"><div class="knowledge-copy"><span class="badge" :class="item.kind === 'faq' ? 'neutral' : 'purple'">{{ item.kind === 'faq' ? '常见问题' : '人工记忆' }}</span><h3>{{ item.title }}</h3><p>{{ item.content }}</p><div class="secondary-line">更新于 {{ dateTime(item.updated_at) }}</div></div><div class="row-actions"><button class="icon-button" :aria-label="'编辑 ' + item.title" @click="edit(item)"><Icon name="edit" :size="18" /></button><button class="icon-button danger-text" :aria-label="'删除 ' + item.title" @click="deleting = item; error = ''"><Icon name="trash" :size="18" /></button></div></article></div>
  </section>
  <DialogShell v-if="open" :title="editing ? '编辑资料' : '新增知识与记忆'" @close="!busy && (open = false)"><form class="form-stack" @submit.prevent="save"><div v-if="error" class="alert error" role="alert">{{ error }}</div><label>分类<select v-model="form.kind"><option value="faq">常见问题</option><option value="memory">人工记忆</option></select></label><label>标题 <span class="required">*</span><input v-model="form.title" required maxlength="120" placeholder="用简短标题说明这条资料" /></label><label>内容 <span class="required">*</span><textarea v-model="form.content" required rows="8" maxlength="4000" placeholder="填写可核对的规则、答案或品牌偏好；必要时说明来源和适用范围" /></label><p class="hint">相关内容可能作为必要参考发送给 DeepSeek。请勿录入平台密钥、订单个人信息或其他不应外发的数据。</p><div class="form-actions"><button type="button" class="button secondary" :disabled="busy" @click="open = false">取消</button><button class="button primary" :disabled="busy">{{ busy ? '正在保存…' : '保存条目' }}</button></div></form></DialogShell>
  <DialogShell v-if="deleting" title="删除这条资料？" @close="!busy && (deleting = null)"><div class="form-stack"><div v-if="error" class="alert error" role="alert">{{ error }}</div><p>将删除“{{ deleting.title }}”。之后生成时不再检索此条目，已经生成的话术请人工检查。</p><div class="form-actions"><button class="button secondary" :disabled="busy" @click="deleting = null">保留</button><button class="button danger" :disabled="busy" @click="remove">{{ busy ? '正在删除…' : '确认删除' }}</button></div></div></DialogShell>
</template>
