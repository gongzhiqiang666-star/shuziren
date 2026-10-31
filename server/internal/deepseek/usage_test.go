package deepseek

import (
	"context"
	"encoding/json"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestKnownUsageSurvivesRejectedDraftAndMissingUsageIsUnknown(t *testing.T) {
	for _, tc := range []struct {
		name, answer, finish string
		usage                any
		known, wantError     bool
	}{
		{"invalid_answer", "{}", "stop", map[string]int{"prompt_tokens": 123, "completion_tokens": 41}, true, true},
		{"truncated", "{}", "length", map[string]int{"prompt_tokens": 123, "completion_tokens": 4096}, true, true},
		{"missing_usage", `{"answer":"测试草稿","needs_human":false,"reason":""}`, "stop", nil, false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				body := map[string]any{"choices": []any{map[string]any{"finish_reason": tc.finish, "message": map[string]string{"content": tc.answer}}}}
				if tc.usage != nil {
					body["usage"] = tc.usage
				}
				json.NewEncoder(w).Encode(body)
			}))
			defer upstream.Close()
			c, _ := New(Config{BaseURL: upstream.URL, APIKey: "test-only"})
			r, e := c.Generate(context.Background(), testSnapshot(), "商品价格？")
			if r.UsageKnown != tc.known || (e != nil) != tc.wantError {
				t.Fatalf("usage=%+v error=%v", r, e)
			}
			if tc.known && r.InputTokens != 123 {
				t.Fatal("known billable usage lost")
			}
		})
	}
}
func TestReservationUsesSameBoundedSelectedKnowledge(t *testing.T) {
	s := testSnapshot()
	selected := []domain.Knowledge{{Title: "语义命中", Content: "无需关键词重复的完整上下文", Kind: "faq"}}
	ctx := WithKnowledge(context.Background(), selected)
	b, e := generationPayload(ctx, s, "商品问题", "deepseek-flash")
	if e != nil || !strings.Contains(string(b), "无需关键词重复") || strings.Contains(string(b), "敏感地址") {
		t.Fatal("retrieval context not used")
	}
	if n, e := GenerationReservation(ctx, s, "商品问题"); e != nil || n < 100000 {
		t.Fatal(n, e)
	}
	s.Business.Promotions = []domain.Promotion{{Title: "过大活动", Description: strings.Repeat("很长", 40000)}}
	if _, e = GenerationReservation(ctx, s, "商品问题"); e == nil {
		t.Fatal("unbounded prompt accepted before quota reservation")
	}
}

func TestCancelledBeforeHTTPIsKnownZeroUsage(t *testing.T) {
	calls := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++ }))
	defer upstream.Close()
	c, _ := New(Config{BaseURL: upstream.URL, APIKey: "test-only"})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result, err := c.Generate(ctx, testSnapshot(), "价格？")
	if err == nil || calls != 0 || !result.UsageKnown || result.InputTokens != 0 || result.OutputTokens != 0 {
		t.Fatal("preflight cancellation counted as unknown remote usage")
	}
}
