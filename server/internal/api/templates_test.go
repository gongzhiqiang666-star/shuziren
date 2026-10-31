package api

import (
	"context"
	"encoding/json"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"strings"
	"testing"
)

func TestTemplateAppliesCurrentFactsAsUnapprovedDraftAndKeepsShopBoundary(t *testing.T) {
	s, shop, p, session := serviceFixture(t, &fakeMedia{})
	ctx := context.Background()
	template, e := s.Store.SaveTemplate(ctx, domain.SpeechTemplate{ShopID: shop.ID, Name: "常用介绍", Body: "{title}当前{price}元，库存{stock}件。"}, true)
	if e != nil {
		t.Fatal(e)
	}
	p.PriceCents = 10888
	p, e = s.Store.SaveProduct(ctx, p, false)
	if e != nil {
		t.Fatal(e)
	}
	router := Router(s, testToken, "")
	body, _ := json.Marshal(map[string]string{"shop_id": shop.ID, "session_id": session.ID, "product_id": p.ID})
	response := request(router, "POST", "/api/v1/templates/"+template.ID+"/apply", string(body), testToken)
	if response.Code != 200 {
		t.Fatal(response.Body.String())
	}
	var result struct {
		Data domain.Job `json:"data"`
	}
	_ = json.Unmarshal(response.Body.Bytes(), &result)
	if result.Data.Status != "draft" || !strings.Contains(result.Data.Text, "108.88元") || result.Data.ProductVersion != p.Version {
		t.Fatal("template did not snapshot current facts")
	}
	template.Name = "新模板名称"
	if _, e = s.Store.SaveTemplate(ctx, template, false); e != nil {
		t.Fatal(e)
	}
	if _, e = s.Store.SaveTemplate(ctx, template, false); e == nil {
		t.Fatal("stale edit accepted")
	}
	other, e := s.Store.CreateShop(ctx, "另一家测试店")
	if e != nil {
		t.Fatal(e)
	}
	if _, e = s.Store.GetTemplate(ctx, other.ID, template.ID); e == nil {
		t.Fatal("cross-shop template read")
	}
}
