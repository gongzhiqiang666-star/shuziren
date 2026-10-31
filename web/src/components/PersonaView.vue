<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime } from '../domain'
import type { NoticeSink, Persona } from '../types'
import Icon from './Icon.vue'
import HistoryDialog from '../business/HistoryDialog.vue'

const props = defineProps<{ api: ApiClient; shopId: string; persona: Persona | null; reload: () => Promise<void>; notify: NoticeSink }>()
const form = reactive({ name: '', tone: '', prompt: '', version: 1 })
const dirty = ref(false)
const history = ref(false)
const saving = ref(false)
const error = ref('')
watch(() => props.persona, p => { if (p && !dirty.value) Object.assign(form, { name: p.name, tone: p.tone, prompt: p.prompt, version: p.version }) }, { immediate: true })
async function save() {
  if (saving.value) return
  error.value = ''
  if (!form.name.trim()) { error.value = '请填写数字人名称。'; return }
  if (!form.tone.trim()) { error.value = '请填写表达语气。'; return }
  saving.value = true
  try {
    await props.api.request('/persona', { method: 'PUT', body: { shop_id: props.shopId, name: form.name.trim(), tone: form.tone.trim(), prompt: form.prompt.trim(), version: form.version } })
    dirty.value = false
    await props.reload()
    props.notify('人格已保存，后续草稿使用新版本。')
  } catch (cause) { error.value = errorMessage(cause) } finally { saving.value = false }
}
function reloadSaved() { if (props.persona) { Object.assign(form, props.persona); dirty.value = false; error.value = '' } }
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">BRAND PERSONA</div><h1>品牌人格</h1><p>让表达有自己的性格，让商品事实保持一致。</p></div><div v-if="persona" class="row-actions"><span class="badge neutral">当前版本 v{{ persona.version }}</span><button class="button secondary small" @click="history = true">版本历史 / 恢复</button></div></div>
  <div class="settings-grid">
    <section class="panel padded"><form class="form-stack" @submit.prevent="save" @input="dirty = true">
      <div class="section-heading"><Icon name="person" /><h2>人物设定</h2></div>
      <div v-if="error" class="alert error" role="alert">{{ error }}</div>
      <label>数字人名称 <span class="required">*</span><input v-model="form.name" :disabled="saving" required maxlength="100" placeholder="例如：小禾" /></label>
      <label>表达语气<input v-model="form.tone" :disabled="saving" required maxlength="500" placeholder="描述语气、节奏与服务态度" /></label>
      <div class="suggestion-row"><button v-for="tone in ['专业清晰', '亲切耐心', '轻快克制']" :key="tone" type="button" class="suggestion" :disabled="saving" @click="form.tone = tone; dirty = true">{{ tone }}</button></div>
      <label>人格规则与表达示例<textarea v-model="form.prompt" :disabled="saving" rows="10" maxlength="4000" placeholder="可以写：先回答问题，再解释依据。每次最多两段。不了解的信息明确说明，不自行承诺赠品或优惠。" /><small>设定表达方式与服务边界；价格、库存和优惠以商品资料为准。</small></label>
      <div class="form-actions"><span class="muted small-text">{{ dirty ? '有未保存的修改' : '已保存的设定' }}</span><button type="button" class="button ghost" :disabled="saving || !dirty" @click="reloadSaved">放弃修改</button><button class="button primary" :disabled="saving || !persona">{{ saving ? '正在保存…' : '保存人格' }}</button></div>
    </form></section>
    <aside class="stack">
      <section class="panel padded tinted"><div class="eyebrow">CONSISTENT BY DESIGN</div><h2>性格影响表达，<br />不会改写事实。</h2><p>同一款商品可以讲得专业，也可以讲得亲切。商品价格、规格与已录入的知识仍是回复依据。</p><div class="fine-divider" /><p>人格更改会升级版本。旧版本的草稿与音频需要重新创建，防止新旧设定混用。</p></section>
      <section class="panel padded"><h3>记忆在哪里维护？</h3><p>到“知识与记忆”新增、修正或删除人工记忆。临时问题不会自动成为长期记忆。</p><div v-if="persona" class="meta-line"><Icon name="clock" :size="16" />最近保存 {{ dateTime(persona.updated_at) }}</div></section>
    </aside>
  </div>
  <HistoryDialog v-if="history && persona" :api="api" :shop-id="shopId" kind="persona" :current-version="persona.version" :title="persona.name" @close="history = false" @restored="dirty = false; reload()" />
</template>
