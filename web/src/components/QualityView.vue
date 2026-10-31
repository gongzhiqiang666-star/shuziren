<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ApiClient, errorMessage } from '../api'
import { dateTime, defaultQualityChecks } from '../domain'
import type { NoticeSink, QualityProfile } from '../types'
import Icon from './Icon.vue'

const props = defineProps<{ api: ApiClient; shopId: string; quality: QualityProfile | null; reload: () => Promise<void>; notify: NoticeSink }>()
const form = reactive({ avatar_name: '', source_resolution: '', model_version: '', canvas_resolution: '', fps: 25, sync_target_ms: 80, notes: '', checks: defaultQualityChecks() })
const dirty = ref(false)
const busy = ref(false)
const error = ref('')
const count = computed(() => form.checks.filter(c => c.passed).length)
const lastSaved = computed(() => props.quality?.updated_at && !props.quality.updated_at.startsWith('0001-') ? dateTime(props.quality.updated_at) : '')
watch(() => props.quality, profile => {
  if (profile && !dirty.value) Object.assign(form, { ...profile, checks: (profile.checks?.length ? profile.checks : defaultQualityChecks()).map(c => ({ ...c })) })
}, { immediate: true })
async function save() {
  if (busy.value) return
  error.value = ''
  if (!Number.isInteger(Number(form.fps)) || Number(form.fps) < 1 || Number(form.fps) > 120) { error.value = '帧率请输入 1–120 的整数。'; return }
  if (!Number.isInteger(Number(form.sync_target_ms)) || Number(form.sync_target_ms) < 0 || Number(form.sync_target_ms) > 2000) { error.value = '同步目标请输入 0–2000 的整数毫秒。'; return }
  busy.value = true
  try {
    await props.api.request('/quality', { method: 'PUT', body: { shop_id: props.shopId, avatar_name: form.avatar_name.trim(), source_resolution: form.source_resolution.trim(), model_version: form.model_version.trim(), canvas_resolution: form.canvas_resolution.trim(), fps: Number(form.fps), sync_target_ms: Number(form.sync_target_ms), notes: form.notes.trim(), checks: form.checks } })
    dirty.value = false; await props.reload(); props.notify('质量档案已保存。这是人工记录，不代表系统自动测量通过。')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">AVATAR QUALITY</div><h1>画质核验</h1><p>记录真实素材、实际参数和逐项观察，为每个形象留下依据。</p></div><span class="badge neutral">人工核验档案</span></div>
  <div class="info-strip warning-strip"><Icon name="shield" :size="19" /><span>勾选仅保存人工记录，不会运行模型、测量帧率或确认淘宝接入。未测试的项目请保持未通过。</span></div>
  <form class="quality-layout" @submit.prevent="save" @input="dirty = true" @change="dirty = true">
    <div class="stack"><section class="panel padded"><div class="section-heading"><Icon name="person" /><h2>形象与渲染档案</h2></div><div class="form-stack"><label>形象名称<input v-model="form.avatar_name" maxlength="100" placeholder="本次测试所用的形象" /></label><div class="form-row"><label>源视频分辨率<input v-model="form.source_resolution" maxlength="100" placeholder="例如 1920×1080" /></label><label>实际输出画布<input v-model="form.canvas_resolution" maxlength="100" placeholder="例如 1280×720" /></label></div><label>实际模型 / 权重版本<input v-model="form.model_version" maxlength="200" placeholder="记录实际加载版本，未核实则留空" /></label><div class="form-row"><label>输出帧率目标<input v-model="form.fps" type="number" min="1" max="120" step="1" /></label><label>传输同步目标（ms）<input v-model="form.sync_target_ms" type="number" min="0" max="2000" step="1" /></label></div><label>环境与测试说明<textarea v-model="form.notes" rows="5" maxlength="6000" placeholder="记录硬件、素材授权、引擎版本、观看条件和证据位置" /></label></div></section><section class="panel padded tinted"><h3>画布清晰，不等于嘴部原生高清</h3><p>MuseTalk 的原生人脸生成区域为 256×256。请同时检查正常观看尺寸与嘴周局部；上采样不代表真实细节恢复。</p><p class="small-text">这些字段是测试档案，不会直接修改媒体服务配置。默认 25fps、80ms 是待验证目标。</p></section></div>
    <section class="panel padded"><div class="section-heading"><Icon name="shield" /><h2>核验清单</h2><span class="badge neutral">人工标记 {{ count }} / {{ form.checks.length }}</span></div><div class="quality-checks"><div v-for="check in form.checks" :key="check.key" class="quality-check"><label class="checkbox-row"><input v-model="check.passed" type="checkbox" /><span>{{ check.label }}</span></label><input v-model="check.notes" :aria-label="check.label + '的证据与备注'" placeholder="实测结果、失败片段或证据位置" maxlength="2000" /></div></div><div v-if="error" class="alert error" role="alert">{{ error }}</div><div class="form-actions"><span class="muted small-text">{{ dirty ? '有未保存的记录' : lastSaved ? '保存于 ' + lastSaved : '尚未保存档案' }}</span><button class="button primary" :disabled="busy">{{ busy ? '正在保存…' : '保存核验记录' }}</button></div></section>
  </form>
</template>
