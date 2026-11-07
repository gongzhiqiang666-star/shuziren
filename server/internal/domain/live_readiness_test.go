package domain

import (
	"strings"
	"testing"
)

func TestLiveReadinessDefaultsAndConclusion(t *testing.T) {
	gates := DefaultLiveReadinessGates()
	if len(gates) != 5 {
		t.Fatalf("got %d gates", len(gates))
	}
	for _, gate := range gates {
		if gate.Status != ReadinessBlocked || gate.Evidence["reason"] != "not_run" {
			t.Fatalf("bad default gate: %#v", gate)
		}
	}
	gates[0] = LiveReadinessGate{Name: "install", Status: "passed", Evidence: map[string]any{"preflight_report": "preflight-01", "nvidia": true, "assets": true, "operator_confirmed": true}}
	gates[1] = LiveReadinessGate{Name: "generation", Status: "passed", Evidence: map[string]any{"new_text": true, "wav_sha256": strings.Repeat("a", 64), "listened": true, "same_wav": true}}
	gates[2] = LiveReadinessGate{Name: "obs", Status: "passed", Evidence: map[string]any{"output_mode": "virtual_camera", "video": "recording-01", "audio": "recording-01", "reviewed": true}}
	if got := LiveReadinessConclusion(gates); got != ConclusionLocalPassedPlatformBlocked {
		t.Fatalf("got %q", got)
	}
}

func TestLiveReadinessRejectsIncompleteAndSensitiveEvidence(t *testing.T) {
	cases := []LiveReadinessGate{
		{Name: "generation", Status: "passed", Evidence: map[string]any{"wav_sha256": "short"}},
		{Name: "obs", Status: "passed", Evidence: map[string]any{"video": "only-video"}},
		{Name: "platform", Status: "passed", Evidence: map[string]any{"approved": false, "viewer_record": "x"}},
		{Name: "install", Status: "blocked", Evidence: map[string]any{"api_token": "secret"}},
		{Name: "install", Status: "blocked", Evidence: map[string]any{"reason": `C:\private\report.json`}},
	}
	for _, gate := range cases {
		if err := ValidateLiveReadinessGate(gate); err == nil {
			t.Fatalf("accepted %#v", gate)
		}
	}
}
