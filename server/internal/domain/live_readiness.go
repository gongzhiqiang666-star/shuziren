package domain

import (
	"regexp"
	"strings"
	"time"
)

const (
	ReadinessPassed                      = "passed"
	ReadinessFailed                      = "failed"
	ReadinessBlocked                     = "blocked"
	ConclusionIncomplete                 = "incomplete"
	ConclusionFailed                     = "failed"
	ConclusionLocalPassedPlatformBlocked = "local_chain_passed_platform_blocked"
	ConclusionPlatformPassed             = "platform_chain_passed"
)

var readinessGateNames = []string{"install", "generation", "obs", "platform", "stability"}
var readinessHash = regexp.MustCompile(`^[a-f0-9]{64}$`)
var readinessSensitive = regexp.MustCompile(`(?i)(^|_)(password|passwd|secret|cookie|session|token|api_key|app_key|app_secret)($|_)`)

type LiveReadinessGate struct {
	Name      string         `json:"name"`
	Status    string         `json:"status"`
	Evidence  map[string]any `json:"evidence"`
	Note      string         `json:"note"`
	Version   int64          `json:"version"`
	UpdatedAt time.Time      `json:"updated_at"`
}

type LiveReadinessRun struct {
	ID         string              `json:"id"`
	ShopID     string              `json:"shop_id"`
	Title      string              `json:"title"`
	OutputMode string              `json:"output_mode"`
	Conclusion string              `json:"conclusion"`
	Version    int64               `json:"version"`
	CreatedAt  time.Time           `json:"created_at"`
	UpdatedAt  time.Time           `json:"updated_at"`
	Gates      []LiveReadinessGate `json:"gates"`
}

func DefaultLiveReadinessGates() []LiveReadinessGate {
	out := make([]LiveReadinessGate, 0, len(readinessGateNames))
	for _, name := range readinessGateNames {
		out = append(out, LiveReadinessGate{Name: name, Status: ReadinessBlocked, Evidence: map[string]any{"reason": "not_run"}, Version: 1})
	}
	return out
}

func cleanEvidence(e map[string]any) bool {
	if e == nil || len(e) > 20 {
		return false
	}
	for key, value := range e {
		if readinessSensitive.MatchString(key) || !TextWithin(key, 1, 64) {
			return false
		}
		switch v := value.(type) {
		case string:
			if !TextWithin(v, 1, 200) || strings.ContainsAny(v, `/\`) || strings.Contains(v, "://") {
				return false
			}
		case bool, float64, int, int64:
		default:
			return false
		}
	}
	return true
}

func truth(e map[string]any, key string) bool  { v, ok := e[key].(bool); return ok && v }
func text(e map[string]any, key string) string { v, _ := e[key].(string); return strings.TrimSpace(v) }

func ValidateLiveReadinessGate(g LiveReadinessGate) error {
	validName := false
	for _, name := range readinessGateNames {
		if g.Name == name {
			validName = true
		}
	}
	if !validName || (g.Status != ReadinessPassed && g.Status != ReadinessFailed && g.Status != ReadinessBlocked) || !TextWithin(g.Note, 0, 2000) || !cleanEvidence(g.Evidence) {
		return Invalid("验证关卡、状态、证据或备注无效。")
	}
	if g.Status != ReadinessPassed {
		return nil
	}
	switch g.Name {
	case "install":
		if text(g.Evidence, "preflight_report") == "" || !truth(g.Evidence, "nvidia") || !truth(g.Evidence, "assets") || !truth(g.Evidence, "operator_confirmed") {
			return Invalid("环境关通过需要预检、NVIDIA、资产和人工确认。")
		}
	case "generation":
		if !truth(g.Evidence, "new_text") || !readinessHash.MatchString(text(g.Evidence, "wav_sha256")) || !truth(g.Evidence, "listened") || !truth(g.Evidence, "same_wav") {
			return Invalid("语音关通过需要新句、WAV哈希、试听及同源确认。")
		}
	case "obs":
		mode := text(g.Evidence, "output_mode")
		if (mode != "virtual_camera" && mode != "srs") || text(g.Evidence, "video") == "" || text(g.Evidence, "audio") == "" || !truth(g.Evidence, "reviewed") {
			return Invalid("OBS关通过需要输出模式、画面、声音及回放确认。")
		}
	case "platform":
		if !truth(g.Evidence, "approved") || text(g.Evidence, "viewer_record") == "" {
			return Invalid("平台关通过需要授权和观看端证据。")
		}
	case "stability":
		if text(g.Evidence, "operator_record") == "" {
			return Invalid("稳定关通过需要人工记录。")
		}
	}
	return nil
}

func LiveReadinessConclusion(gates []LiveReadinessGate) string {
	byName := map[string]LiveReadinessGate{}
	for _, gate := range gates {
		byName[gate.Name] = gate
		if gate.Status == ReadinessFailed {
			return ConclusionFailed
		}
	}
	for _, name := range []string{"install", "generation", "obs"} {
		if byName[name].Status != ReadinessPassed {
			return ConclusionIncomplete
		}
	}
	if byName["platform"].Status == ReadinessPassed {
		return ConclusionPlatformPassed
	}
	if byName["platform"].Status == ReadinessBlocked {
		return ConclusionLocalPassedPlatformBlocked
	}
	return ConclusionIncomplete
}
