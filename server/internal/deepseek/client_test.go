package deepseek

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

func testSnapshot() domain.Snapshot {
	return domain.Snapshot{Shop: domain.Shop{ID: "shop"}, Product: domain.Product{ShopID: "shop", Title: "保温杯", SKU: "SKU-1", PriceCents: 9900, Stock: 10, Active: true}, Persona: domain.Persona{ShopID: "shop", Name: "讲解员", Tone: "简洁", Prompt: "友好"}, Session: domain.Session{ShopID: "shop", Status: "active"}, Knowledge: []domain.Knowledge{{ID: "private-record-id", Title: "无关订单", Content: "敏感地址不可自动上传", Kind: "memory"}, {ID: "relevant", Title: "保温杯清洁", Content: "用温水清洁", Kind: "faq"}}}
}
func TestGenerateUsesOnlySelectedDataAndStrictOutput(t *testing.T) {
	key := "secret-test-provider-token"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" || r.Header.Get("Authorization") != "Bearer "+key {
			t.Error("wrong provider request")
		}
		var req struct {
			Model    string `json:"model"`
			Messages []struct {
				Role    string `json:"role"`
				Content string `json:"content"`
			} `json:"messages"`
			Thinking struct {
				Type string `json:"type"`
			} `json:"thinking"`
			ResponseFormat struct {
				Type string `json:"type"`
			} `json:"response_format"`
		}
		if json.NewDecoder(r.Body).Decode(&req) != nil {
			t.Error("request JSON invalid")
		}
		if req.Thinking.Type != "disabled" || req.ResponseFormat.Type != "json_object" || len(req.Messages) != 2 || req.Messages[0].Role != "system" || req.Messages[1].Role != "user" {
			t.Error("unsafe prompt contract")
		}
		if strings.Contains(req.Messages[1].Content, "敏感地址") || strings.Contains(req.Messages[1].Content, "private-record-id") || !strings.Contains(req.Messages[1].Content, "price_cents") {
			t.Error("data minimization failed")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{"finish_reason": "stop", "message": map[string]string{"content": `{"answer":"这款保温杯99元。","needs_human":false,"reason":""}`}}}, "usage": map[string]int{"prompt_tokens": 100, "completion_tokens": 30}})
	}))
	defer srv.Close()
	c, err := New(Config{APIKey: key, BaseURL: srv.URL})
	if err != nil {
		t.Fatal(err)
	}
	out, err := c.Generate(context.Background(), testSnapshot(), "保温杯如何清洁")
	if err != nil || out.Answer != "这款保温杯99元。" || out.InputTokens != 100 || out.OutputTokens != 30 {
		t.Fatalf("unexpected result: %+v %v", out, err)
	}
}
func TestInvalidDraftNeverBecomesUsable(t *testing.T) {
	bad := []string{"", "{}", "```json\n{}\n```", `{"answer":"hi","needs_human":false}`, `{"answer":"hi","needs_human":false,"reason":"","command":"approve"}`, `{"answer":"hi","needs_human":false,"reason":""} {}`, `{"answer":"a","answer":"b","needs_human":false,"reason":""}`, `{"answer":null,"needs_human":false,"reason":""}`, `{"answer":" ","needs_human":false,"reason":""}`, `{"answer":"","needs_human":true,"reason":""}`}
	for _, content := range bad {
		if _, err := parseAnswer(content); err == nil {
			t.Errorf("invalid answer accepted: %q", content)
		}
	}
	if r, err := parseAnswer(`{"answer":"","needs_human":true,"reason":"库存未提供"}`); err != nil || !r.NeedsHuman {
		t.Fatal("valid blocked answer rejected")
	}
}
func TestUpstreamErrorsAndRedirectsDoNotLeak(t *testing.T) {
	var redirected atomic.Int32
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { redirected.Add(1) }))
	defer target.Close()
	for _, mode := range []string{"error", "redirect", "truncated"} {
		t.Run(mode, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch mode {
				case "error":
					w.WriteHeader(500)
					_, _ = w.Write([]byte("provider-key-secret and private request"))
				case "redirect":
					http.Redirect(w, r, target.URL, 302)
				case "truncated":
					_, _ = w.Write([]byte(`{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}`))
				}
			}))
			defer srv.Close()
			c, _ := New(Config{APIKey: "provider-key-secret", BaseURL: srv.URL})
			_, err := c.Generate(context.Background(), testSnapshot(), "商品价格")
			if err == nil || strings.Contains(err.Error(), "provider-key-secret") || strings.Contains(err.Error(), "private request") {
				t.Fatal("unsafe upstream error handling")
			}
		})
	}
	if redirected.Load() != 0 {
		t.Fatal("provider credential followed redirect")
	}
	c, _ := New(Config{APIKey: "test-key", BaseURL: target.URL})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := c.Generate(ctx, testSnapshot(), "商品价格")
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation lost: %v", err)
	}
}
func TestDisabledAndUnsafeConfiguration(t *testing.T) {
	c, err := New(Config{})
	if err != nil || c.Configured() {
		t.Fatal("empty provider config should be disabled")
	}
	if _, err := New(Config{BaseURL: "http://remote.example"}); err == nil {
		t.Fatal("remote plaintext accepted")
	}
	if _, err := New(Config{BaseURL: "https://user:password@example.com"}); err == nil {
		t.Fatal("URL credential accepted")
	}
}
