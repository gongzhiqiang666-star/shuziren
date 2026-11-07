import { afterEach, expect, it, vi } from 'vitest'
import { flushUI, render } from './testHarness'
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

it('从左侧导航进入只记录证据的开播验证向导', async () => {
  const status = { version: '0.2.0', storage: 'postgresql', deepseek: { configured: false, model: 'deepseek-flash' }, media: { tts_configured: false, live_configured: false }, taobao: { status: 'not_connected' }, retrieval: { mode: 'keyword' } }
  const shop = { id: '11111111-1111-4111-8111-111111111111', name: '验证店', created_at: '' }
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    let data: unknown = []
    if (url.endsWith('/status')) data = status
    else if (url.endsWith('/shops')) data = [shop]
    else if (url.includes('/persona')) data = { shop_id: shop.id, name: '', tone: '', prompt: '', version: 1, updated_at: '' }
    else if (url.includes('/quality')) data = { shop_id: shop.id, avatar_name: '', source_resolution: '', model_version: '', canvas_resolution: '', fps: 25, sync_target_ms: 80, notes: '', checks: [], updated_at: '' }
    return Promise.resolve(new Response(JSON.stringify({ data })))
  }))
  const view = render(App)
  await view.setValue('input[name="workspace-token"]', 'this-is-an-in-memory-test-token')
  await view.submit(); await flushUI()
  const nav = [...view.root.querySelectorAll<HTMLButtonElement>('.main-nav button')].find(button => button.textContent?.includes('开播验证'))!
  nav.click(); await flushUI()
  expect(view.root.textContent).toContain('按顺序检查、操作并记录一条真实音画链路')
  expect(view.root.textContent).toContain('不会执行命令')
  view.unmount()
})
