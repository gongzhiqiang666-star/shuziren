package domain

import "time"

const GenerationReservationTokens int64 = 100000

type GenerationLimits struct {
	ShopID                   string    `json:"shop_id"`
	RequestsPerMinute        int       `json:"requests_per_minute"`
	DailyRequestLimit        int64     `json:"daily_request_limit"`
	DailyTokenLimit          int64     `json:"daily_token_limit"`
	Version                  int64     `json:"version"`
	UpdatedAt                time.Time `json:"updated_at"`
	GlobalMaxConcurrent      int       `json:"global_max_concurrent"`
	RequestReservationTokens int64     `json:"request_reservation_tokens"`
}

func DefaultGenerationLimits(shop string) GenerationLimits {
	return GenerationLimits{ShopID: shop, RequestsPerMinute: 10, GlobalMaxConcurrent: 1, RequestReservationTokens: GenerationReservationTokens}
}

type GenerationUsage struct {
	Limits               GenerationLimits `json:"limits"`
	DateUTC              string           `json:"date_utc"`
	RequestsToday        int64            `json:"requests_today"`
	ChargedTokensToday   int64            `json:"charged_tokens_today"`
	UnknownRequestsToday int64            `json:"unknown_requests_today"`
	PendingRequestsToday int64            `json:"pending_requests_today"`
	Enforcement          string           `json:"enforcement"`
}
type SpeechSchedule struct {
	ID        string    `json:"id"`
	ShopID    string    `json:"shop_id"`
	SessionID string    `json:"session_id"`
	JobID     string    `json:"job_id"`
	RunAt     time.Time `json:"run_at"`
	ExpiresAt time.Time `json:"expires_at"`
	Status    string    `json:"status"`
	Reason    string    `json:"reason"`
	ErrorCode string    `json:"error_code"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}
