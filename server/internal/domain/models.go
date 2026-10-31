package domain

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"
)

// These objects are the public v0.1 contract. Internal versions used to invalidate
// edited knowledge are deliberately kept out of the HTTP representation.
type Shop struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	CreatedAt time.Time `json:"created_at"`
}

type Product struct {
	ID          string     `json:"id"`
	ShopID      string     `json:"shop_id"`
	Title       string     `json:"title"`
	SKU         string     `json:"sku"`
	Description string     `json:"description"`
	Specs       string     `json:"specs"`
	PriceCents  int64      `json:"price_cents"`
	Stock       int64      `json:"stock"`
	Active      bool       `json:"active"`
	Version     int64      `json:"version"`
	ExpiresAt   *time.Time `json:"expires_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
}

type Persona struct {
	ShopID    string    `json:"shop_id"`
	Name      string    `json:"name"`
	Tone      string    `json:"tone"`
	Prompt    string    `json:"prompt"`
	Version   int64     `json:"version"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Knowledge struct {
	ID        string    `json:"id"`
	ShopID    string    `json:"shop_id"`
	Title     string    `json:"title"`
	Content   string    `json:"content"`
	Kind      string    `json:"kind"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Session struct {
	ID             string    `json:"id"`
	ShopID         string    `json:"shop_id"`
	Title          string    `json:"title"`
	Status         string    `json:"status"`
	Epoch          int64     `json:"epoch"`
	MediaSessionID *string   `json:"media_session_id"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

type Job struct {
	ID               string     `json:"id"`
	ShopID           string     `json:"shop_id"`
	SessionID        string     `json:"session_id"`
	ProductID        string     `json:"product_id"`
	ProductVersion   int64      `json:"product_version"`
	PersonaVersion   int64      `json:"persona_version"`
	Epoch            int64      `json:"epoch"`
	Source           string     `json:"source"`
	Question         string     `json:"question"`
	Text             string     `json:"text"`
	Status           string     `json:"status"`
	Reason           string     `json:"reason"`
	ErrorCode        string     `json:"error_code"`
	InputTokens      int64      `json:"input_tokens"`
	OutputTokens     int64      `json:"output_tokens"`
	CreatedAt        time.Time  `json:"created_at"`
	UpdatedAt        time.Time  `json:"updated_at"`
	KnowledgeVersion int64      `json:"-"`
	ApprovedAt       *time.Time `json:"-"`
	AudioReady       bool       `json:"-"`
}

type QualityCheck struct {
	Key    string `json:"key"`
	Label  string `json:"label"`
	Passed bool   `json:"passed"`
	Notes  string `json:"notes"`
}

type QualityProfile struct {
	ShopID           string         `json:"shop_id"`
	AvatarName       string         `json:"avatar_name"`
	SourceResolution string         `json:"source_resolution"`
	ModelVersion     string         `json:"model_version"`
	CanvasResolution string         `json:"canvas_resolution"`
	FPS              int            `json:"fps"`
	SyncTargetMS     int            `json:"sync_target_ms"`
	Notes            string         `json:"notes"`
	Checks           []QualityCheck `json:"checks"`
	UpdatedAt        time.Time      `json:"updated_at"`
}

type Snapshot struct {
	Shop             Shop        `json:"shop"`
	Session          Session     `json:"session"`
	Product          Product     `json:"product"`
	Persona          Persona     `json:"persona"`
	Knowledge        []Knowledge `json:"knowledge"`
	KnowledgeVersion int64       `json:"knowledge_version"`
}

func DefaultPersona(shopID string) Persona {
	return Persona{ShopID: shopID, Name: "品牌商品讲解员", Tone: "专业、简洁、友好", Prompt: "只使用已提供且有效的商品事实。未知问题交由人工确认。明确自己是AI讲解员，不编造个人经历或优惠。", Version: 1}
}

func DefaultQuality(shopID string, now time.Time) QualityProfile {
	labels := []struct{ key, label string }{
		{"source_authorized", "形象与声音素材授权已核对"},
		{"source_material", "源素材与逐头像裁剪已检查"},
		{"face_detail", "脸部与嘴周细节已人工审阅"},
		{"pronunciation", "商品读音与停顿已审阅"},
		{"transport_sync", "传输音画偏差已测量"},
		{"lip_sync", "实际口型语料已审阅"},
		{"sustained_run", "目标负载持续运行已测试"},
		{"takeover", "真人接管与旧批次隔离已验证"},
		{"taobao_receiver", "真实淘宝接收端已验证"},
	}
	p := QualityProfile{ShopID: shopID, CanvasResolution: "1280x720", FPS: 25, SyncTargetMS: 80, Notes: "人工质量档案；勾选不代表系统自动测量或已配置媒体引擎。", UpdatedAt: now.UTC(), Checks: make([]QualityCheck, 0, len(labels))}
	for _, x := range labels {
		p.Checks = append(p.Checks, QualityCheck{Key: x.key, Label: x.label})
	}
	return p
}

func NewID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic("secure random generator unavailable")
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	h := hex.EncodeToString(b[:])
	return h[:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

func ValidID(id string) bool {
	if len(id) != 36 || id[8] != '-' || id[13] != '-' || id[18] != '-' || id[23] != '-' {
		return false
	}
	b, err := hex.DecodeString(strings.ReplaceAll(id, "-", ""))
	return err == nil && len(b) == 16
}

func TextWithin(s string, min, max int) bool {
	n := utf8.RuneCountInString(strings.TrimSpace(s))
	return n >= min && n <= max && utf8.ValidString(s) && !strings.ContainsRune(s, '\x00')
}

func ValidateSnapshot(s Snapshot, now time.Time) error {
	if s.Session.ShopID != s.Shop.ID || s.Product.ShopID != s.Shop.ID || s.Persona.ShopID != s.Shop.ID {
		return NotFound()
	}
	if s.Session.Status != "active" {
		return Conflict("session_inactive", "场次已暂停或结束，请先确认场次状态。")
	}
	if !s.Product.Active {
		return Conflict("product_inactive", "商品已停用，不能生成或派发话术。")
	}
	if s.Product.ExpiresAt != nil && !now.Before(*s.Product.ExpiresAt) {
		return Conflict("product_expired", "商品资料已过期，请更新后重新生成。")
	}
	return nil
}

func ValidateJob(j Job, s Snapshot, now time.Time) error {
	if j.ShopID != s.Shop.ID || j.SessionID != s.Session.ID || j.ProductID != s.Product.ID {
		return NotFound()
	}
	if err := ValidateSnapshot(s, now); err != nil {
		return err
	}
	if j.Epoch != s.Session.Epoch {
		return Conflict("stale_epoch", "场次执行批次已改变，旧任务不能继续执行。")
	}
	if j.ProductVersion != s.Product.Version {
		return Conflict("stale_product", "商品版本已改变，请重新生成和审核话术。")
	}
	if j.PersonaVersion != s.Persona.Version {
		return Conflict("stale_persona", "人格版本已改变，请重新生成和审核话术。")
	}
	if j.KnowledgeVersion != s.KnowledgeVersion {
		return Conflict("stale_knowledge", "FAQ或记忆已修改，请重新生成和审核话术。")
	}
	return nil
}

type Error struct {
	Status  int
	Code    string
	Message string
}

func (e *Error) Error() string                { return fmt.Sprintf("%s: %s", e.Code, e.Message) }
func Invalid(message string) *Error           { return &Error{400, "invalid_input", message} }
func NotFound() *Error                        { return &Error{404, "not_found", "未找到该店铺下的资源。"} }
func Conflict(code, message string) *Error    { return &Error{409, code, message} }
func Unavailable(code, message string) *Error { return &Error{503, code, message} }
