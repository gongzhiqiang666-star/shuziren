package api

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
)

func TestBusinessHTTPRejectsInvalidMetadataBeforeStorage(t *testing.T) {
	r := Router(&Service{}, testToken, "")
	shop := "11111111-1111-4111-8111-111111111111"
	for _, tc := range []struct{ method, path, body string }{
		{"POST", "/api/v1/promotions", fmt.Sprintf(`{"shop_id":%q,"title":"bad","starts_at":"2026-11-01T00:00:00Z","ends_at":"2026-10-01T00:00:00Z","version":0}`, shop)},
		{"POST", "/api/v1/knowledge-records", fmt.Sprintf(`{"shop_id":%q,"title":"x","content":"x","kind":"memory","source":"operator","scope":"session","scope_id":null,"version":0}`, shop)},
		{"POST", "/api/v1/assets", fmt.Sprintf(`{"shop_id":%q,"kind":"voice","name":"x","identifier":"voice","sha256":%q,"active":true,"authorized":false,"version":0}`, shop, strings.Repeat("a", 64))},
		{"PUT", "/api/v1/cost-settings", fmt.Sprintf(`{"shop_id":%q,"input_cny_per_million":-1,"version":0}`, shop)},
		{"POST", "/api/v1/persona/restore", fmt.Sprintf(`{"shop_id":%q,"version":0,"target_version":1}`, shop)},
		{"DELETE", "/api/v1/knowledge-records/" + shop + "?shop_id=" + shop + "&version=0", ""},
	} {
		out := request(r, tc.method, tc.path, tc.body, testToken)
		if out.Code != 400 {
			t.Fatalf("%s %s: %d %s", tc.method, tc.path, out.Code, out.Body.String())
		}
	}
}
func TestBusinessHTTPPersistsEffectivePromotionAndScopedMemory(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, err := s.CreateShop(ctx, "业务接口测试店")
	if err != nil {
		t.Fatal(err)
	}
	service, err := New(s, nil, nil, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	r := Router(service, testToken, "")
	now := time.Now().UTC()
	body := fmt.Sprintf(`{"shop_id":%q,"title":"活动","description":"运费以订单页面为准","starts_at":%q,"ends_at":%q,"active":true,"version":0}`, shop.ID, now.Add(-time.Hour).Format(time.RFC3339), now.Add(time.Hour).Format(time.RFC3339))
	out := request(r, "POST", "/api/v1/promotions", body, testToken)
	if out.Code != 200 {
		t.Fatal(out.Code, out.Body.String())
	}
	out = request(r, "POST", "/api/v1/knowledge-records", fmt.Sprintf(`{"shop_id":%q,"title":"品牌记忆","content":"语气温和","kind":"memory","source":"店主确认","scope":"shop","scope_id":null,"expires_at":null,"version":0}`, shop.ID), testToken)
	if out.Code != 200 {
		t.Fatal(out.Code, out.Body.String())
	}
	var envelope struct {
		Data struct {
			ID      string `json:"id"`
			Version int64  `json:"version"`
		}
	}
	if json.Unmarshal(out.Body.Bytes(), &envelope) != nil || envelope.Data.Version != 1 {
		t.Fatal("knowledge response missing version")
	}
	out = request(r, "GET", "/api/v1/knowledge-records/"+envelope.Data.ID+"/history?shop_id="+shop.ID, "", testToken)
	if out.Code != 200 || !strings.Contains(out.Body.String(), "店主确认") {
		t.Fatal(out.Code, out.Body.String())
	}
	out = request(r, "GET", "/api/v1/costs?shop_id="+shop.ID, "", testToken)
	if out.Code != 200 || !strings.Contains(out.Body.String(), `"estimated_ai_cny":null`) {
		t.Fatal(out.Code, out.Body.String())
	}
}
