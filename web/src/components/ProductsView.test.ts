import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../api'
import { render } from '../testHarness'
import ProductsView from './ProductsView.vue'

afterEach(() => vi.unstubAllGlobals())
it('提交失败后保留用户填写的商品资料，并提示真实业务错误', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'CONFLICT', message: '商品版本已变化，请核对后再保存。' } }), { status: 409 })))
  const api = new ApiClient(); api.setToken('test-token')
  const view = render(ProductsView, { api, shopId: 'shop', products: [], reload: vi.fn().mockResolvedValue(undefined), notify: vi.fn() })
  await view.click('.page-heading .primary')
  await view.setValue('input[name="title"]', '手工茶杯')
  await view.setValue('input[name="sku"]', 'CUP-01')
  await view.setValue('input[name="price"]', '19.90')
  await view.submit()
  expect(view.find('[role="alert"]').textContent).toContain('商品版本已变化')
  expect(view.find<HTMLInputElement>('input[name="title"]').value).toBe('手工茶杯')
  expect(view.find<HTMLInputElement>('input[name="price"]').value).toBe('19.90')
  view.unmount()
})

it('提交价格为整数分、库存为整数，保存成功后刷新列表', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { id: 'product' } })))
  vi.stubGlobal('fetch', fetcher)
  const api = new ApiClient(); api.setToken('test-token')
  const reload = vi.fn().mockResolvedValue(undefined)
  const view = render(ProductsView, { api, shopId: 'shop', products: [], reload, notify: vi.fn() })
  await view.click('.page-heading .primary')
  await view.setValue('input[name="title"]', '杯子')
  await view.setValue('input[name="sku"]', 'CUP')
  await view.setValue('input[name="price"]', '0.29')
  await view.setValue('input[name="stock"]', '3')
  await view.submit()
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toMatchObject({ shop_id: 'shop', price_cents: 29, stock: 3, expires_at: null })
  expect(reload).toHaveBeenCalledOnce()
  expect(document.querySelector('[role="dialog"]')).toBeNull()
  view.unmount()
})
