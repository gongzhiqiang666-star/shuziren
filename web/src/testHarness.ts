import { createApp, h, nextTick, shallowReactive, type Component } from 'vue'

/** Small DOM harness using Vue's own runtime; no additional test mounting library. */
export async function flushUI() {
  await nextTick()
  await new Promise<void>(resolve => window.setTimeout(resolve, 0))
  await nextTick()
}

export function render(component: Component, props: Record<string, unknown> = {}) {
  const root = document.createElement('div')
  document.body.append(root)
  const state = shallowReactive({ ...props })
  const app = createApp({ render: () => h(component, state) })
  app.mount(root)
  function find<T extends Element = HTMLElement>(selector: string): T {
    const element = root.querySelector(selector) ?? document.querySelector(selector)
    if (!element) throw new Error('测试元素不存在：' + selector)
    return element as T
  }
  return {
    root,
    find,
    async updateProps(next: Record<string, unknown>) { Object.assign(state, next); await flushUI() },
    async setValue(selector: string, value: string) {
      const input = find<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(selector)
      input.value = value
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
      await flushUI()
    },
    async click(selector: string) { find<HTMLElement>(selector).click(); await flushUI() },
    async submit(selector = 'form') {
      find(selector).dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      await flushUI()
    },
    unmount() { app.unmount(); root.remove() },
  }
}
