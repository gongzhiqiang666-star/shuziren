package domain

import (
	"fmt"
	"regexp"
	"strings"
	"time"
)

type SpeechTemplate struct {
	ID        string    `json:"id"`
	ShopID    string    `json:"shop_id"`
	Name      string    `json:"name"`
	Body      string    `json:"body"`
	Version   int64     `json:"version"`
	UpdatedAt time.Time `json:"updated_at"`
}

var templateFields = regexp.MustCompile(`\{(title|sku|price|stock|specs|description)\}`)

func ValidateTemplate(body string) error {
	if !TextWithin(body, 1, 2000) || strings.ContainsAny(templateFields.ReplaceAllString(body, ""), "{}") {
		return Invalid("模板仅支持约定的商品占位符，正文应为1至2000字。")
	}
	return nil
}
func RenderTemplate(body string, p Product) (string, error) {
	if e := ValidateTemplate(body); e != nil {
		return "", e
	}
	values := map[string]string{"{title}": p.Title, "{sku}": p.SKU, "{price}": fmt.Sprintf("%d.%02d", p.PriceCents/100, p.PriceCents%100), "{stock}": fmt.Sprint(p.Stock), "{specs}": p.Specs, "{description}": p.Description}
	// Replace only placeholders in the template. Product text is never expanded a second time.
	result := templateFields.ReplaceAllStringFunc(body, func(key string) string { return values[key] })
	if !TextWithin(result, 1, 2000) {
		return "", Invalid("模板展开后超过2000字或内容无效，请缩短模板。")
	}
	return result, nil
}
