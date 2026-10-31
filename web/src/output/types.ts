export interface OutputConfig { width: number; height: number; fit: 'contain' | 'cover'; background: string }
export interface OutputStatus {
  session_id: string; enabled: boolean; generation: number; session_status: 'active' | 'paused' | 'ended'; epoch: number
  config: OutputConfig; state: 'disabled' | 'offline' | 'negotiating' | 'connected' | 'paused' | 'ended'
  online: boolean; peer_state: string; video_ready: boolean; audio_ready: boolean
  last_heartbeat_at: string | null; lease_expires_at: string | null; lease_owned: boolean; lease_id: string | null
  heartbeat_interval_ms: number; lease_ttl_ms: number
}
export interface OutputControlResult { output: OutputStatus; media_stop_status: 'sent' | 'not_connected' | 'failed' }
export interface OutputIssueResult extends OutputControlResult { token: string; output_path: string }
export interface OutputAnswer { sdp: string; type: 'answer'; sessionid: string; lease_id: string; output: OutputStatus }
