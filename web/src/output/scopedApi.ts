export class OutputError extends Error {
  constructor(message: string, public code: string, public status: number) { super(message); this.name = 'OutputError' }
}
type Endpoint = 'status' | 'offer' | 'heartbeat' | 'release'
type RequestOptions = { body?: unknown; receiverId?: string; signal?: AbortSignal; keepalive?: boolean }

/** A separate client with no operator-token access and only four permitted endpoints. */
export class OutputClient {
  constructor(private readonly token: string) {}
  async request<T>(endpoint: Endpoint, options: RequestOptions = {}): Promise<T> {
    if (!['status', 'offer', 'heartbeat', 'release'].includes(endpoint)) throw new OutputError('输出接口无效。', 'invalid_endpoint', 0)
    if (!this.token) throw new OutputError('输出链接缺少授权，请在运营台重新签发。', 'missing_token', 401)
    const controller = new AbortController()
    const abort = () => controller.abort()
    if (options.signal?.aborted) controller.abort()
    options.signal?.addEventListener('abort', abort, { once: true })
    const timer = window.setTimeout(abort, endpoint === 'offer' ? 100_000 : endpoint === 'release' ? 65_000 : 12_000)
    try {
      const suffix = endpoint === 'status' ? '?' + new URLSearchParams({ receiver_id: options.receiverId ?? '' }).toString() : ''
      const response = await fetch('/output-api/v1/' + endpoint + suffix, {
        method: endpoint === 'status' ? 'GET' : 'POST',
        headers: { Authorization: 'Bearer ' + this.token, ...(endpoint === 'status' ? {} : { 'Content-Type': 'application/json' }) },
        body: endpoint === 'status' ? undefined : JSON.stringify(options.body),
        credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', signal: controller.signal, keepalive: options.keepalive,
      })
      let result: { data?: T; error?: { code?: string; message?: string } }
      try { result = await response.json() } catch { throw new OutputError('输出服务返回了无法识别的数据。', 'invalid_response', response.status) }
      if (!response.ok) throw new OutputError(result.error?.message || '输出请求失败，请检查本地服务。', result.error?.code || 'output_error', response.status)
      if (!Object.prototype.hasOwnProperty.call(result, 'data')) throw new OutputError('输出服务返回格式不符合约定。', 'invalid_envelope', response.status)
      return result.data as T
    } catch (cause) {
      if (cause instanceof OutputError) throw cause
      throw new OutputError(controller.signal.aborted ? '输出请求超时或已取消。' : '无法连接本地输出服务。', controller.signal.aborted ? 'output_timeout' : 'output_network', 0)
    } finally { window.clearTimeout(timer); options.signal?.removeEventListener('abort', abort) }
  }
}

export function outputToken(hash: string): string { return new URLSearchParams(hash.replace(/^#/, '')).get('token')?.trim() ?? '' }
export function outputLink(token: string, path: string, origin: string): string {
  const supplied = new URL(path, origin)
  if (!token || !path.startsWith('/') || path.startsWith('//') || supplied.origin !== origin || !['/output', '/output/'].includes(supplied.pathname) || supplied.search || (supplied.hash && outputToken(supplied.hash) !== token)) throw new Error('服务返回的输出链接无效。')
  const url = new URL('/output', origin)
  url.hash = new URLSearchParams({ token }).toString()
  return url.toString()
}
