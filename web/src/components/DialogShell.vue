<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import Icon from './Icon.vue'
withDefaults(defineProps<{ title: string; wide?: boolean }>(), { wide: false })
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement>()
let previous: HTMLElement | null = null
function handleKey(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
  if (event.key !== 'Tab' || !panel.value) return
  const items = [...panel.value.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')]
  if (!items.length) return
  if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus() }
  if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus() }
}
onMounted(() => {
  previous = document.activeElement as HTMLElement | null
  panel.value?.querySelector<HTMLElement>('input, textarea, select, button')?.focus()
  document.addEventListener('keydown', handleKey)
})
onBeforeUnmount(() => { document.removeEventListener('keydown', handleKey); previous?.focus() })
</script>
<template>
  <Teleport to="body">
    <div class="dialog-overlay" @click.self="emit('close')">
      <section ref="panel" class="dialog-panel" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
        <header class="dialog-header"><h2>{{ title }}</h2><button class="icon-button" type="button" aria-label="关闭弹窗" @click="emit('close')"><Icon name="close" /></button></header>
        <slot />
      </section>
    </div>
  </Teleport>
</template>
