export class ApiError extends Error {
  constructor(message: string, public code: string, public status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

type Options = { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown; query?: Record<string, string>; timeout?: number }

/** The token lives only in this page's memory; never in browser storage or URLs. */
export class ApiClient {
  private token = ''
  onUnauthorized?: () => void

  setToken(token: string) { this.token = token.trim() }
  clearToken() { this.token = '' }

  private async fetchResponse(path: string, options: Options = {}): Promise<Response> {
    if (!this.token) throw new ApiError('请输入工作台口令。', 'UNAUTHENTICATED', 401)
    if (!path.startsWith('/') || path.startsWith('//') || path.includes('?')) {
      throw new ApiError('请求地址无效。', 'INVALID_PATH', 0)
    }
    const query = new URLSearchParams(options.query)
    const url = '/api/v1' + path + (query.size ? '?' + query.toString() : '')
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), options.timeout ?? 30_000)
    let response: Response
    try {
      response = await fetch(url, {
        method: options.method ?? 'GET',
        headers: {
          Authorization: 'Bearer ' + this.token,
          ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError('请求超时，请刷新状态后再决定下一步，避免重复派发。', 'TIMEOUT', 0)
      }
      throw new ApiError('无法连接本地服务，请检查服务是否正在运行。', 'NETWORK_ERROR', 0)
    } finally {
      window.clearTimeout(timer)
    }
    if (!response.ok) {
      let message = response.status === 401 ? '口令无效或已失效，请重新登录。' : '操作未成功，请稍后重试。'
      let code = 'HTTP_' + response.status
      try {
        const body = await response.json() as { error?: { message?: unknown; code?: unknown } }
        if (typeof body.error?.message === 'string') message = body.error.message
        if (typeof body.error?.code === 'string') code = body.error.code
      } catch { /* Never expose a proxy's raw HTML or an upstream request body. */ }
      if (response.status === 401) this.onUnauthorized?.()
      throw new ApiError(message, code, response.status)
    }
    return response
  }

  async request<T>(path: string, options: Options = {}): Promise<T> {
    const response = await this.fetchResponse(path, options)
    let envelope: unknown
    try { envelope = await response.json() } catch {
      throw new ApiError('本地服务返回了无法识别的数据。', 'INVALID_RESPONSE', response.status)
    }
    if (!envelope || typeof envelope !== 'object' || !Object.prototype.hasOwnProperty.call(envelope, 'data')) {
      throw new ApiError('本地服务返回格式不符合接口约定。', 'INVALID_ENVELOPE', response.status)
    }
    return (envelope as { data: T }).data
  }

  async audio(jobId: string, shopId: string): Promise<Blob> {
    const response = await this.fetchResponse('/jobs/' + encodeURIComponent(jobId) + '/audio', { query: { shop_id: shopId } })
    const blob = await response.blob()
    if (!blob.size) throw new ApiError('音频文件为空，请核对合成任务。', 'EMPTY_AUDIO', 0)
    if (!/^audio\//i.test(blob.type) && blob.type !== 'application/octet-stream') {
      throw new ApiError('服务未返回有效的音频文件。', 'INVALID_AUDIO', 0)
    }
    return blob
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作未成功，请稍后重试。'
}
