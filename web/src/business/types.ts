export interface HistoryEntry { version: number; snapshot: Record<string, unknown>; recorded_at: string; deleted: boolean }
export interface Promotion {
  id: string; shop_id: string; product_id: string | null; title: string; description: string
  offer_price_cents: number | null; starts_at: string; ends_at: string; active: boolean; version: number; updated_at: string
}
export interface KnowledgeRecord {
  id: string; shop_id: string; title: string; content: string; kind: 'faq' | 'memory'; source: string
  scope: 'shop' | 'product' | 'session'; scope_id: string | null; expires_at: string | null
  version: number; deleted_at: string | null; updated_at: string
}
export interface Asset {
  id: string; shop_id: string; kind: 'avatar' | 'voice' | 'model'; name: string; identifier: string
  sha256: string; model_version: string; authorized: boolean; active: boolean; version: number
  updated_at: string; binding_status: 'record_only'
}
export interface CostSettings {
  shop_id: string; input_cny_per_million: number | null; output_cny_per_million: number | null
  electricity_cny_per_kwh: number | null; device_watts: number | null; monthly_budget_cny: number | null
  notes: string; version: number; updated_at: string
}
export interface CostSummary {
  shop_id: string; session_id: string; input_tokens: number; output_tokens: number; generated_jobs: number
  usage_events: number; unknown_usage_events: number; estimated_ai_cny: number | null
  estimated_power_cny_per_hour: number | null; currency: 'CNY'; basis: 'operator_entered_rates'
  settings: CostSettings; note: string
}
