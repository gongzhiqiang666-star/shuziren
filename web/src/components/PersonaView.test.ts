import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { flushUI, render } from '../testHarness'
import PersonaView from './PersonaView.vue'
afterEach(() => vi.unstubAllGlobals())
it('人格保存与版本刷新期间禁止继续改表单，避免提交旧版本的第二次编辑', async () => {
  let finish: (response: Response) => void = () => {}
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve })))
  const api = new ApiClient(); api.setToken('operator')
  const persona = { shop_id: 's', name: '小禾', tone: '清晰', prompt: '', version: 1, updated_at: '' }
  const view = render(PersonaView, { api, shopId: 's', persona, notify: vi.fn(), reload: vi.fn().mockResolvedValue(undefined) })
  await view.submit()
  expect(view.find<HTMLInputElement>('input').disabled).toBe(true)
  expect(view.find<HTMLTextAreaElement>('textarea').disabled).toBe(true)
  finish(new Response(JSON.stringify({ data: { ...persona, version: 2 } }))); await flushUI()
  expect(view.find<HTMLInputElement>('input').disabled).toBe(false)
  view.unmount()
})
