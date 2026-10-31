package api

import (
	"context"
	"encoding/json"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/config"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/taobao"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTaobaoDurableInboxPrecedesAcknowledgementAndDeduplicates(t *testing.T) {
	s, shop, _, session := serviceFixture(t, &fakeMedia{})
	ctx := context.Background()
	if _, e := s.Store.BindTaobaoRoom(ctx, shop.ID, session.ID, "123"); e != nil {
		t.Fatal(e)
	}
	confirms := 0
	failConfirm := true
	fixture := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		switch r.Form.Get("method") {
		case "taobao.tmc.messages.consume":
			json.NewEncoder(w).Encode(map[string]any{"tmc_messages_consume_response": map[string]any{"messages": map[string]any{"tmc_message": []any{map[string]any{"id": json.Number("9007199254740993"), "topic": taobao.CommentTopic, "content": `{"liveId":"123","uniqueCode":"abc","comment":"能装热水吗","userId":"PRIVATE-USER","userNick":"PRIVATE-NICK"}`}}}}})
		case "taobao.tmc.messages.confirm":
			confirms++
			rows, e := s.Store.ListTaobaoEvents(ctx, shop.ID, session.ID)
			if e != nil || len(rows) != 1 {
				t.Error("confirmed before durable insert")
			}
			if failConfirm {
				w.WriteHeader(503)
			} else {
				w.Write([]byte(`{"tmc_messages_confirm_response":{"is_success":true}}`))
			}
		default:
			t.Error("unexpected API")
		}
	}))
	defer fixture.Close()
	if e := s.ConfigureIntegrations(config.Integrations{Taobao: taobao.Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: fixture.URL}, TaobaoShopID: shop.ID}); e != nil {
		t.Fatal(e)
	}
	if _, e := s.pollTaobao(ctx, shop.ID); e == nil {
		t.Fatal("confirm failure hidden")
	}
	failConfirm = false
	r, e := s.pollTaobao(ctx, shop.ID)
	if e != nil || r.Duplicates != 1 || r.Confirmed != 1 || confirms != 2 {
		t.Fatalf("retry not idempotent: %+v %v", r, e)
	}
	rows, _ := s.Store.ListTaobaoEvents(ctx, shop.ID, session.ID)
	b, _ := json.Marshal(rows)
	if strings.Contains(string(b), "PRIVATE") {
		t.Fatal("unneeded user identifiers retained")
	}
	if _, e := s.pollTaobao(ctx, domain.NewID()); e == nil {
		t.Fatal("cross-shop credentials used")
	}
}
func TestReplayCannotMasqueradeAsTaobaoAndRequiresRoomBinding(t *testing.T) {
	s, shop, _, session := serviceFixture(t, &fakeMedia{})
	ctx := context.Background()
	r := Router(s, testToken, "")
	payload := map[string]any{"shop_id": shop.ID, "session_id": session.ID, "message_id": "local-case-1", "content": map[string]any{"liveId": "123", "comment": "这个杯子什么材质？"}}
	b, _ := json.Marshal(payload)
	if x := request(r, "POST", "/api/v1/taobao/events/replay", string(b), testToken); x.Code != 404 {
		t.Fatal("unbound replay accepted", x.Code)
	}
	if _, e := s.Store.BindTaobaoRoom(ctx, shop.ID, session.ID, "123"); e != nil {
		t.Fatal(e)
	}
	for n := 0; n < 2; n++ {
		x := request(r, "POST", "/api/v1/taobao/events/replay", string(b), testToken)
		if x.Code != 200 {
			t.Fatal(x.Body.String())
		}
		var body struct {
			Data struct {
				Event     store.Event `json:"event"`
				Duplicate bool        `json:"duplicate"`
			} `json:"data"`
		}
		_ = json.Unmarshal(x.Body.Bytes(), &body)
		if body.Data.Event.Source != "replay" || body.Data.Duplicate != (n == 1) {
			t.Fatal("bad replay identity")
		}
	}
	rows, _ := s.Store.ListTaobaoEvents(ctx, shop.ID, session.ID)
	if _, e := s.Takeover(ctx, shop.ID, session.ID, "takeover"); e != nil {
		t.Fatal(e)
	}
	if _, e := s.Resume(ctx, shop.ID, session.ID); e != nil {
		t.Fatal(e)
	}
	if _, e := s.Store.ClaimEvent(ctx, shop.ID, rows[0].ID); e == nil {
		t.Fatal("stale event survived takeover")
	}
}
func TestTaobaoActionUnknownIsNotRepeatedAndPayloadCannotChange(t *testing.T) {
	s, shop, _, session := serviceFixture(t, &fakeMedia{})
	ctx := context.Background()
	if _, e := s.Store.BindTaobaoRoom(ctx, shop.ID, session.ID, "123"); e != nil {
		t.Fatal(e)
	}
	calls := 0
	fixture := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(503) }))
	defer fixture.Close()
	if e := s.ConfigureIntegrations(config.Integrations{Taobao: taobao.Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: fixture.URL}, TaobaoShopID: shop.ID}); e != nil {
		t.Fatal(e)
	}
	router := Router(s, testToken, "")
	body := map[string]any{"shop_id": shop.ID, "session_id": session.ID, "request_id": domain.NewID(), "item_id": "999"}
	b, _ := json.Marshal(body)
	for n := 0; n < 2; n++ {
		r := request(router, "POST", "/api/v1/taobao/push-item", string(b), testToken)
		if r.Code != 200 || !strings.Contains(r.Body.String(), "delivery_unknown") {
			t.Fatalf("unknown hidden: %d %s", r.Code, r.Body.String())
		}
	}
	if calls != 1 {
		t.Fatal("ambiguous action repeated")
	}
	body["item_id"] = "888"
	b, _ = json.Marshal(body)
	if r := request(router, "POST", "/api/v1/taobao/push-item", string(b), testToken); r.Code != 409 {
		t.Fatal("idempotency payload collision accepted")
	}
}
