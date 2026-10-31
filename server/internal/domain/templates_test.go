package domain

import (
	"strings"
	"testing"
)

func TestTemplateUsesIntegerMoneyAndNeverEvaluatesProductText(t *testing.T) {
	p := Product{Title: "含{price}字样的商品", SKU: "A-1", PriceCents: 105, Stock: 7, Specs: "500毫升"}
	text, e := RenderTemplate("{title}，{price}元，库存{stock}件，{specs}。", p)
	if e != nil || text != "含{price}字样的商品，1.05元，库存7件，500毫升。" {
		t.Fatal(text, e)
	}
	for _, body := range []string{"{unknown}", "{title", "{{title}}", "{os.exec}", " "} {
		if ValidateTemplate(body) == nil {
			t.Fatal("invalid template accepted", body)
		}
	}
	p.Description = strings.Repeat("长", 1990)
	if _, e = RenderTemplate("{description}，{description}", p); e == nil {
		t.Fatal("oversized expansion accepted")
	}
}
