import { afterEach, expect, it, vi } from 'vitest'
import { render } from './testHarness'
import App from './App.vue'

afterEach(() => vi.unstubAllGlobals())
it('登录口令只用于本页请求，不写入浏览器存储；重新挂载需要重新登录', async () => {
  const localWrite = vi.spyOn(Storage.prototype, 'setItem')
  const status = { version: '0.1.0', storage: 'postgresql', deepseek: { configured: false, model: 'deepseek-flash' }, media: { tts_configured: false, live_configured: false }, taobao: { status: 'not_implemented' }, retrieval: { mode: 'keyword' } }
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify({ data: url.endsWith('/status') ? status : [] })))))
  const view = render(App)
  await view.setValue('input[name="workspace-token"]', 'this-is-an-in-memory-test-token')
  await view.submit()
  expect(view.root.querySelector('.welcome-empty')).not.toBeNull()
  expect(view.root.textContent).toContain('淘宝未接入')
  expect(view.root.textContent).toContain('关键词检索')
  expect(localWrite).not.toHaveBeenCalled()
  expect(window.location.href).not.toContain('test-token')
  view.unmount()
  const fresh = render(App)
  expect(fresh.root.querySelector('.login-shell')).not.toBeNull()
  expect(fresh.find<HTMLInputElement>('input[name="workspace-token"]').value).toBe('')
  fresh.unmount()
})
