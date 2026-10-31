export interface Shop { id: string; name: string; created_at: string }
export interface Product {
  id: string; shop_id: string; title: string; sku: string; description: string
  specs: string; price_cents: number; stock: number; active: boolean
  version: number; expires_at: string | null; updated_at: string
}
export interface Persona {
  shop_id: string; name: string; tone: string; prompt: string; version: number; updated_at: string
}
export interface Knowledge {
  id: string; shop_id: string; title: string; content: string; kind: 'faq' | 'memory'; updated_at: string
}
export interface Session {
  id: string; shop_id: string; title: string; status: 'active' | 'paused' | 'ended'
  epoch: number; media_session_id: string | null; created_at: string; updated_at: string
}
export type JobStatus = 'draft' | 'blocked' | 'approved' | 'queued' | 'synthesizing' | 'ready' | 'sending' | 'sent' | 'cancelled' | 'failed' | 'delivery_unknown'
export interface Job {
  id: string; shop_id: string; session_id: string; product_id: string
  product_version: number; persona_version: number; epoch: number
  source: 'manual' | 'deepseek'; question: string; text: string; status: JobStatus
  reason: string; error_code: string; input_tokens: number; output_tokens: number
  created_at: string; updated_at: string
}
export interface QualityCheck { key: string; label: string; passed: boolean; notes: string }
export interface QualityProfile {
  shop_id: string; avatar_name: string; source_resolution: string; model_version: string
  canvas_resolution: string; fps: number; sync_target_ms: number; notes: string
  checks: QualityCheck[]; updated_at: string
}
export interface SystemStatus {
  version: string; storage: string
  deepseek: { configured: boolean; model: string }
  media: { tts_configured: boolean; live_configured: boolean }
  taobao: { status: string }; retrieval: { mode: string }
}
export interface MediaAnswer { sdp: string; type: string; sessionid: string }
export type NoticeSink = (message: string, kind?: 'success' | 'error' | 'info') => void
