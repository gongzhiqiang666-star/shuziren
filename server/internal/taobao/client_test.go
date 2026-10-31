package taobao

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestTOPSignsExactUTF8AndPreservesLargeIdentifiers(t *testing.T) {
	var calls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Method != "POST" || r.URL.RawQuery != "" {
			t.Error("credentials must be posted, not in URL")
		}
		_ = r.ParseForm()
		if r.Form.Get("timestamp") != "2026-10-31 08:00:00" || r.Form.Get("sign_method") != "hmac-sha256" || r.Form.Get("sign") != Sign(r.Form, "test-secret") {
			t.Error("TOP protocol/signature mismatch")
		}
		switch r.Form.Get("method") {
		case "taobao.tmc.messages.consume":
			if r.Form.Get("session") != "" {
				t.Error("session not needed for consume")
			}
			w.Write([]byte(`{"tmc_messages_consume_response":{"messages":{"tmc_message":[{"id":9007199254740993,"topic":"taobao_liveaigc_CommentSend","content":"{\"liveId\":\"123\",\"comment\":\"尺寸\"}"}]}}}`))
		case "taobao.tmc.messages.confirm":
			if r.Form.Get("s_message_ids") != "9007199254740993" {
				t.Error("message ID lost precision")
			}
			w.Write([]byte(`{"tmc_messages_confirm_response":{"is_success":true}}`))
		case "taobao.live.virtualanchor.push.item.card":
			var body map[string]json.Number
			_ = json.Unmarshal([]byte(r.Form.Get("live_push_item_card_req")), &body)
			if body["item_id"] != "9007199254740993" || r.Form.Get("session") != "test-session" {
				t.Error("item ID or session changed")
			}
			w.Write([]byte(`{"live_virtualanchor_push_item_card_response":{"business_success":true}}`))
		default:
			t.Error("unexpected method")
		}
	}))
	defer server.Close()
	c, e := New(Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: server.URL})
	if e != nil {
		t.Fatal(e)
	}
	c.now = func() time.Time { return time.Date(2026, 10, 31, 0, 0, 0, 0, time.UTC) }
	messages, e := c.Consume(context.Background())
	if e != nil || len(messages) != 1 || string(messages[0].ID) != "9007199254740993" {
		t.Fatalf("consume %v %v", messages, e)
	}
	if e = c.Confirm(context.Background(), []string{string(messages[0].ID)}); e != nil {
		t.Fatal(e)
	}
	if e = c.PushItem(context.Background(), "123", "9007199254740993"); e != nil {
		t.Fatal(e)
	}
	if calls != 3 {
		t.Fatal(calls)
	}
}
func TestRejectsMissingSuccessErrorsAndRedirectWithoutLeaking(t *testing.T) {
	for _, body := range []string{`{}`, `{"live_virtualanchor_push_item_card_response":{}}`, `{"live_virtualanchor_push_item_card_response":{"business_success":false}}`, `{"error_response":{"code":27,"msg":"private-secret"}}`, `{"live_virtualanchor_push_item_card_response":{"business_success":true}}{}`} {
		t.Run(body, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(body)) }))
			defer server.Close()
			c, _ := New(Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: server.URL})
			e := c.PushItem(context.Background(), "1", "2")
			if e == nil || strings.Contains(e.Error(), "private-secret") {
				t.Fatal("unsafe success/error", e)
			}
		})
	}
	hits := 0
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { hits++ }))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 307) }))
	defer redirect.Close()
	c, _ := New(Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: redirect.URL})
	if c.PushItem(context.Background(), "1", "2") == nil || hits != 0 {
		t.Fatal("redirect followed")
	}
}
func TestGatewayAndIDsAreConstrained(t *testing.T) {
	for _, gateway := range []string{"http://gw.api.taobao.com/router/rest", "https://evil.test/router/rest", "https://gw.api.taobao.com/router/rest?secret=x", "https://user:pass@gw.api.taobao.com/router/rest"} {
		if _, e := New(Config{Gateway: gateway}); e == nil {
			t.Fatal("unsafe gateway", gateway)
		}
	}
	for _, id := range []string{"9007199254740993", "123"} {
		if !ValidNumber(id) {
			t.Fatal(id)
		}
	}
	for _, id := range []string{"0", "-1", "1.5", "1e4", "01", "9223372036854775808"} {
		if ValidNumber(id) {
			t.Fatal(id)
		}
	}
	// Independent standard HMAC test vector for the sorted string "a1b2".
	if Sign(url.Values{"b": {"2"}, "a": {"1"}}, "secret") != "3A9F9E53162A24430830CCA87B7FB623401B81EB6616A6EA75B3614AEBDC7F4D" {
		t.Fatal("signature does not match independent Python hmac reference")
	}
}
