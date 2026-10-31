import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from './api'

afterEach(() => vi.unstubAllGlobals())
describe('API 身份与返回约定', () => {
  it('只通过 Bearer header 发送口令，并解包 data', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [{ id: 'shop' }] }), { headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetcher)
    const client = new ApiClient(); client.setToken('  secret-workspace-token-000000  ')
    expect(await client.request('/shops')).toEqual([{ id: 'shop' }])
    const [url, options] = fetcher.mock.calls[0]!
    expect(url).toBe('/api/v1/shops')
    expect(options.headers.Authorization).toBe('Bearer secret-workspace-token-000000')
    expect(url).not.toContain('secret')
  })
  it('清除口令后拒绝请求，而不是发送匿名请求', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    const client = new ApiClient(); client.setToken('token'); client.clearToken()
    await expect(client.request('/status')).rejects.toMatchObject({ code: 'UNAUTHENTICATED' })
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('拒绝把认证头发送到绝对地址', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    const client = new ApiClient(); client.setToken('token')
    await expect(client.request('//external.invalid')).rejects.toMatchObject({ code: 'INVALID_PATH' })
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('401 触发重新登录，同时保留中文业务错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'UNAUTHORIZED', message: '口令已失效' } }), { status: 401 })))
    const client = new ApiClient(); client.setToken('token'); client.onUnauthorized = vi.fn()
    await expect(client.request('/status')).rejects.toMatchObject({ code: 'UNAUTHORIZED', message: '口令已失效' })
    expect(client.onUnauthorized).toHaveBeenCalledOnce()
  })
  it('不会把代理的原始 HTML 错误泄露给界面', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>private upstream details</html>', { status: 502 })))
    const client = new ApiClient(); client.setToken('token')
    await expect(client.request('/jobs')).rejects.toThrow('操作未成功')
  })
  it('成功但缺少 data 的响应不能冒充正常资料', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [] }))))
    const client = new ApiClient(); client.setToken('token')
    await expect(client.request('/jobs')).rejects.toMatchObject({ code: 'INVALID_ENVELOPE' })
  })
  it('音频通过认证 fetch 获取，URL 只有店铺参数', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(new Uint8Array([82, 73, 70, 70]), { headers: { 'Content-Type': 'audio/wav' } }))
    vi.stubGlobal('fetch', fetcher)
    const client = new ApiClient(); client.setToken('private-token')
    const blob = await client.audio('job-1', 'shop-1')
    expect(blob.size).toBe(4)
    expect(fetcher.mock.calls[0]![0]).toBe('/api/v1/jobs/job-1/audio?shop_id=shop-1')
    expect(fetcher.mock.calls[0]![1].headers.Authorization).toBe('Bearer private-token')
  })
})
