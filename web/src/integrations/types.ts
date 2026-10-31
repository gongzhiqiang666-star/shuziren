export interface Diagnostic { checked_at: string; checks: { name: string; status: 'ok' | 'unconfigured' | 'failed'; detail: string }[]; note: string }
export interface IntegrationStatus {
  taobao: { configured: boolean; shop_id: string; transport: 'top_http_poll'; polling: boolean; last_poll_at: string | null; last_success_at: string | null; last_error_code: string; status?: string }
  retrieval: { mode: 'keyword' | 'bge'; configured: boolean; model: string }
}
export interface Room { shop_id: string; session_id: string; live_id: string; updated_at: string }
export interface TaobaoEvent { id: string; shop_id: string; session_id: string; message_id: string; live_id: string; comment: string; source: 'taobao' | 'replay'; dedup_key: string; status: 'pending' | 'generating' | 'drafted' | 'failed' | 'ignored'; job_id: string | null; error_code: string; received_at: string }
export interface SearchResult { mode: 'keyword' | 'bge'; matches: { id: string; title: string; content: string; kind: string }[]; note: string }
export interface TaobaoItem { num_iid: string; title: string; price: string; num: number; outer_id: string; approve_status: string }
export interface TaobaoItems { items: TaobaoItem[]; total_results: number }
export interface TaobaoAction { request_id: string; status: 'succeeded' | 'delivery_unknown' | 'failed' }
export interface ActionAttempt { kind: 'push-item' | 'report'; requestId: string; body: Record<string, unknown>; result: TaobaoAction | null; error: string; attempted: boolean }
