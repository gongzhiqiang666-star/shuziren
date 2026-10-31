package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/config"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/taobao"
)

func TestTaobaoTakeoverCancelsInFlightActionAndWaitsForItsFence(t *testing.T) {
	s, shop, _, session := serviceFixture(t, &fakeMedia{})
	ctx := context.Background()
	if _, e := s.Store.BindTaobaoRoom(ctx, shop.ID, session.ID, "123"); e != nil {
		t.Fatal(e)
	}
	started := make(chan struct{})
	release := make(chan struct{})
	var calls atomic.Int32
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) == 1 {
			close(started)
		}
		// Cancelling an HTTP request cannot promise that a remote operation was
		// undone. Keep the server working and verify the client returns unknown.
		<-release
		w.Write([]byte(`{"live_virtualanchor_push_item_card_response":{"business_success":true}}`))
	}))
	defer upstream.Close()
	defer close(release)
	if e := s.ConfigureIntegrations(config.Integrations{Taobao: taobao.Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: upstream.URL}, TaobaoShopID: shop.ID}); e != nil {
		t.Fatal(e)
	}
	router := Router(s, testToken, "")
	body, _ := json.Marshal(map[string]any{"shop_id": shop.ID, "session_id": session.ID, "request_id": domain.NewID(), "item_id": "999"})
	done := make(chan *httptest.ResponseRecorder, 1)
	go func() { done <- request(router, "POST", "/api/v1/taobao/push-item", string(body), testToken) }()
	select {
	case <-started:
	case <-time.After(3 * time.Second):
		t.Fatal("platform request did not start")
	}
	takeover, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	if _, e := s.Takeover(takeover, shop.ID, session.ID, "takeover"); e != nil {
		t.Fatal(e)
	}
	select {
	case result := <-done:
		if result.Code != 200 || !strings.Contains(result.Body.String(), "delivery_unknown") {
			t.Fatal(result.Code, result.Body.String())
		}
	case <-time.After(time.Second):
		t.Fatal("takeover returned before action fence drained")
	}
	result := request(router, "POST", "/api/v1/taobao/push-item", string(body), testToken)
	if result.Code != 200 || !strings.Contains(result.Body.String(), "delivery_unknown") || calls.Load() != 1 {
		t.Fatal("same action was retried after takeover", result.Code, result.Body.String())
	}
}
