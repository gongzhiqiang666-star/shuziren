package domain

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"math"
	"sort"
	"time"
)

type Promotion struct {
	ID              string    `json:"id"`
	ShopID          string    `json:"shop_id"`
	ProductID       *string   `json:"product_id"`
	Title           string    `json:"title"`
	Description     string    `json:"description"`
	OfferPriceCents *int64    `json:"offer_price_cents"`
	StartsAt        time.Time `json:"starts_at"`
	EndsAt          time.Time `json:"ends_at"`
	Active          bool      `json:"active"`
	Version         int64     `json:"version"`
	UpdatedAt       time.Time `json:"updated_at"`
}
type KnowledgeRecord struct {
	Knowledge
	Source    string     `json:"source"`
	Scope     string     `json:"scope"`
	ScopeID   *string    `json:"scope_id"`
	ExpiresAt *time.Time `json:"expires_at"`
	Version   int64      `json:"version"`
	DeletedAt *time.Time `json:"deleted_at"`
}
type Asset struct {
	ID            string    `json:"id"`
	ShopID        string    `json:"shop_id"`
	Kind          string    `json:"kind"`
	Name          string    `json:"name"`
	Identifier    string    `json:"identifier"`
	SHA256        string    `json:"sha256"`
	ModelVersion  string    `json:"model_version"`
	Authorized    bool      `json:"authorized"`
	Active        bool      `json:"active"`
	Version       int64     `json:"version"`
	UpdatedAt     time.Time `json:"updated_at"`
	BindingStatus string    `json:"binding_status"`
}
type HistoryEntry struct {
	Version    int64           `json:"version"`
	Snapshot   json.RawMessage `json:"snapshot"`
	RecordedAt time.Time       `json:"recorded_at"`
	Deleted    bool            `json:"deleted"`
}
type KnowledgeRef struct {
	ID        string     `json:"id"`
	Version   int64      `json:"version"`
	ExpiresAt *time.Time `json:"expires_at"`
}
type BusinessSnapshot struct {
	Fingerprint   string         `json:"fingerprint"`
	Promotions    []Promotion    `json:"promotions"`
	Assets        []Asset        `json:"assets"`
	KnowledgeRefs []KnowledgeRef `json:"knowledge_refs"`
	ValidUntil    *time.Time     `json:"valid_until"`
}

// Fingerprints depend on effective business facts and their next time boundary,
// not on polling or creation timestamps. Keep sort order stable across queries.
func (b *BusinessSnapshot) Seal() {
	if b.Promotions == nil {
		b.Promotions = []Promotion{}
	}
	if b.Assets == nil {
		b.Assets = []Asset{}
	}
	if b.KnowledgeRefs == nil {
		b.KnowledgeRefs = []KnowledgeRef{}
	}
	sort.Slice(b.Promotions, func(i, j int) bool { return b.Promotions[i].ID < b.Promotions[j].ID })
	sort.Slice(b.Assets, func(i, j int) bool { return b.Assets[i].ID < b.Assets[j].ID })
	sort.Slice(b.KnowledgeRefs, func(i, j int) bool { return b.KnowledgeRefs[i].ID < b.KnowledgeRefs[j].ID })
	b.Fingerprint = ""
	raw, _ := json.Marshal(b)
	sum := sha256.Sum256(raw)
	b.Fingerprint = hex.EncodeToString(sum[:])
}
func (b *BusinessSnapshot) Boundary(t *time.Time, now time.Time) {
	if t != nil && now.Before(*t) && (b.ValidUntil == nil || t.Before(*b.ValidUntil)) {
		v := t.UTC()
		b.ValidUntil = &v
	}
}
func ValidateBusinessSnapshot(b BusinessSnapshot, now time.Time) error {
	if b.ValidUntil != nil && !now.Before(*b.ValidUntil) {
		return Conflict("stale_business", "活动或记忆已到生效时间边界，请重新生成和审核话术。")
	}
	for _, p := range b.Promotions {
		if !p.Active || now.Before(p.StartsAt) || !now.Before(p.EndsAt) {
			return Conflict("stale_business", "活动已失效，请重新生成和审核话术。")
		}
	}
	for _, a := range b.Assets {
		if !a.Active || !a.Authorized {
			return Conflict("asset_unavailable", "素材未启用或授权未确认。")
		}
	}
	return nil
}
func ValidateBusinessJob(j Job, s Snapshot, now time.Time) error {
	if err := ValidateBusinessSnapshot(s.Business, now); err != nil {
		return err
	}
	if j.BusinessFingerprint != s.Business.Fingerprint {
		return Conflict("stale_business", "活动、素材或有效记忆已改变，请重新生成和审核话术。")
	}
	return nil
}

type CostSettings struct {
	ShopID               string    `json:"shop_id"`
	InputCNYPerMillion   *float64  `json:"input_cny_per_million"`
	OutputCNYPerMillion  *float64  `json:"output_cny_per_million"`
	ElectricityCNYPerKWH *float64  `json:"electricity_cny_per_kwh"`
	DeviceWatts          *float64  `json:"device_watts"`
	MonthlyBudgetCNY     *float64  `json:"monthly_budget_cny"`
	Notes                string    `json:"notes"`
	Version              int64     `json:"version"`
	UpdatedAt            time.Time `json:"updated_at"`
}

func ValidCostSettings(c CostSettings) bool {
	for _, v := range []*float64{c.InputCNYPerMillion, c.OutputCNYPerMillion, c.ElectricityCNYPerKWH, c.DeviceWatts, c.MonthlyBudgetCNY} {
		if v != nil && (math.IsNaN(*v) || math.IsInf(*v, 0) || *v < 0 || *v > 10000000) {
			return false
		}
	}
	return c.Version >= 0 && TextWithin(c.Notes, 0, 2000)
}

type CostSummary struct {
	ShopID                   string       `json:"shop_id"`
	SessionID                string       `json:"session_id"`
	InputTokens              int64        `json:"input_tokens"`
	OutputTokens             int64        `json:"output_tokens"`
	GeneratedJobs            int64        `json:"generated_jobs"`
	UsageEvents              int64        `json:"usage_events"`
	UnknownUsageEvents       int64        `json:"unknown_usage_events"`
	EstimatedAICNY           *float64     `json:"estimated_ai_cny"`
	EstimatedPowerCNYPerHour *float64     `json:"estimated_power_cny_per_hour"`
	Currency                 string       `json:"currency"`
	Basis                    string       `json:"basis"`
	Settings                 CostSettings `json:"settings"`
	Note                     string       `json:"note"`
}
type UsageEvent struct {
	ID           string    `json:"id"`
	ShopID       string    `json:"shop_id"`
	SessionID    string    `json:"session_id"`
	JobID        *string   `json:"job_id"`
	Model        string    `json:"model"`
	Status       string    `json:"status"`
	InputTokens  int64     `json:"input_tokens"`
	OutputTokens int64     `json:"output_tokens"`
	ErrorCode    string    `json:"error_code"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}
