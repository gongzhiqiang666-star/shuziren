package config

import (
	"errors"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/retrieval"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/taobao"
)

type Integrations struct {
	Retrieval    retrieval.Config
	Taobao       taobao.Config
	TaobaoShopID string
	PollEnabled  bool
}

func integrationsFromEnv(get func(string) string) (Integrations, error) {
	c := Integrations{Retrieval: retrieval.Config{BaseURL: get("BGE_BASE_URL"), APIKey: get("BGE_API_KEY")}, Taobao: taobao.Config{AppKey: get("TAOBAO_APP_KEY"), AppSecret: get("TAOBAO_APP_SECRET"), Session: get("TAOBAO_SESSION"), Gateway: get("TAOBAO_GATEWAY"), Group: get("TAOBAO_TMC_GROUP")}, TaobaoShopID: get("TAOBAO_SHOP_ID"), PollEnabled: get("TAOBAO_POLL_ENABLED") == "1"}
	if p := get("TAOBAO_POLL_ENABLED"); p != "" && p != "0" && p != "1" {
		return c, errors.New("TAOBAO_POLL_ENABLED must be 0 or 1")
	}
	if c.Taobao.AppKey != "" && !domain.ValidID(c.TaobaoShopID) {
		return c, errors.New("TAOBAO_SHOP_ID must bind the configured account to one local shop UUID")
	}
	if c.PollEnabled && c.Taobao.AppKey == "" {
		return c, errors.New("Taobao polling requires configured credentials")
	}
	return c, nil
}
