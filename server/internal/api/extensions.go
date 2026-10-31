package api

import (
	"encoding/hex"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

// RegisterBusinessRoutes shares the operator authorization middleware. It does
// not expose any of these resources to the narrowly scoped output receiver.
func (s *Service) RegisterBusinessRoutes(a *gin.RouterGroup) {
	a.GET("/promotions", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListPromotions(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.POST("/promotions", s.savePromotion(true))
	a.PUT("/promotions/:id", s.savePromotion(false))
	a.GET("/promotions/:id/history", s.businessHistory("promotion"))
	a.GET("/persona/history", s.businessHistory("persona"))
	a.POST("/persona/restore", s.restoreBusiness("persona"))
	a.GET("/products/:id/history", s.businessHistory("product"))
	a.POST("/products/:id/restore", s.restoreBusiness("product"))
	a.GET("/knowledge-records", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListKnowledgeRecords(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.POST("/knowledge-records", s.saveKnowledgeRecord(true))
	a.PUT("/knowledge-records/:id", s.saveKnowledgeRecord(false))
	a.DELETE("/knowledge-records/:id", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes || !ids(c, c.Param("id")) {
			return
		}
		v, e := strconv.ParseInt(c.Query("version"), 10, 64)
		if e != nil || v < 1 {
			fail(c, domain.Invalid("删除需提供当前version。"))
			return
		}
		gate := s.shopLock(shop)
		gate.Lock()
		defer gate.Unlock()
		e = s.Store.DeleteKnowledgeRecord(c.Request.Context(), shop, c.Param("id"), v)
		respond(c, gin.H{"deleted": true}, e)
	})
	a.GET("/knowledge-records/:id/history", s.businessHistory("knowledge"))
	a.POST("/knowledge-records/:id/restore", s.restoreBusiness("knowledge"))
	a.GET("/assets", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListAssets(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.POST("/assets", s.saveAsset(true))
	a.PUT("/assets/:id", s.saveAsset(false))
	a.GET("/assets/:id/history", s.businessHistory("asset"))
	a.GET("/cost-settings", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.GetCostSettings(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.PUT("/cost-settings", func(c *gin.Context) {
		var in domain.CostSettings
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		in.Notes = strings.TrimSpace(in.Notes)
		if !domain.ValidCostSettings(in) {
			fail(c, domain.Invalid("费率必须为0至10000000的有限数值或null，备注最多2000字，需提供当前版本。"))
			return
		}
		p, e := s.Store.SaveCostSettings(c.Request.Context(), in)
		respond(c, p, e)
	})
	a.GET("/costs", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		session := c.Query("session_id")
		if session != "" && !ids(c, session) {
			return
		}
		p, e := s.Store.CostSummary(c.Request.Context(), shop, session)
		respond(c, p, e)
	})
	a.GET("/business-snapshot", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes || !ids(c, c.Query("session_id"), c.Query("product_id")) {
			return
		}
		p, e := s.Store.BusinessSnapshot(c.Request.Context(), shop, c.Query("session_id"), c.Query("product_id"))
		respond(c, p, e)
	})
}
func (s *Service) businessHistory(kind string) gin.HandlerFunc {
	return func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		id := c.Param("id")
		if kind != "persona" && !ids(c, id) {
			return
		}
		p, e := s.Store.BusinessHistory(c.Request.Context(), shop, kind, id)
		respond(c, p, e)
	}
}
func (s *Service) restoreBusiness(kind string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in struct {
			ShopID        string `json:"shop_id"`
			Version       int64  `json:"version"`
			TargetVersion int64  `json:"target_version"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		id := c.Param("id")
		if kind != "persona" && !ids(c, id) {
			return
		}
		if in.Version < 1 || in.TargetVersion < 1 {
			fail(c, domain.Invalid("恢复需提供当前版本与目标历史版本。"))
			return
		}
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		switch kind {
		case "persona":
			p, e := s.Store.RestorePersona(c.Request.Context(), in.ShopID, in.Version, in.TargetVersion)
			respond(c, p, e)
		case "product":
			p, e := s.Store.RestoreProduct(c.Request.Context(), in.ShopID, id, in.Version, in.TargetVersion)
			respond(c, p, e)
		case "knowledge":
			p, e := s.Store.RestoreKnowledgeRecord(c.Request.Context(), in.ShopID, id, in.Version, in.TargetVersion)
			respond(c, p, e)
		}
	}
}
func (s *Service) savePromotion(create bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in domain.Promotion
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if !create && !ids(c, c.Param("id")) {
			return
		}
		if in.ProductID != nil && !ids(c, *in.ProductID) {
			return
		}
		in.Title = strings.TrimSpace(in.Title)
		in.Description = strings.TrimSpace(in.Description)
		if !domain.TextWithin(in.Title, 1, 160) || !domain.TextWithin(in.Description, 0, 4000) || in.StartsAt.IsZero() || in.EndsAt.IsZero() || !in.EndsAt.After(in.StartsAt) || (in.OfferPriceCents != nil && (*in.OfferPriceCents < 0 || *in.OfferPriceCents > 1000000000000)) || (create && in.Version != 0) || (!create && in.Version < 1) {
			fail(c, domain.Invalid("活动标题、描述、金额、时间范围或版本无效。"))
			return
		}
		in.ID = c.Param("id")
		in.StartsAt = in.StartsAt.UTC()
		in.EndsAt = in.EndsAt.UTC()
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		p, e := s.Store.SavePromotion(c.Request.Context(), in, create)
		respond(c, p, e)
	}
}
func (s *Service) saveKnowledgeRecord(create bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in domain.KnowledgeRecord
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if !create && !ids(c, c.Param("id")) {
			return
		}
		in.Title = strings.TrimSpace(in.Title)
		in.Content = strings.TrimSpace(in.Content)
		in.Source = strings.TrimSpace(in.Source)
		valid := domain.TextWithin(in.Title, 1, 120) && domain.TextWithin(in.Content, 1, 4000) && domain.TextWithin(in.Source, 1, 500) && (in.Kind == "faq" || in.Kind == "memory") && ((in.Scope == "shop" && in.ScopeID == nil) || ((in.Scope == "product" || in.Scope == "session") && in.ScopeID != nil && domain.ValidID(*in.ScopeID))) && ((create && in.Version == 0) || (!create && in.Version > 0))
		if !valid || in.DeletedAt != nil {
			fail(c, domain.Invalid("知识内容、来源、作用范围或版本无效；删除记录请通过历史恢复。"))
			return
		}
		in.ID = c.Param("id")
		if in.ExpiresAt != nil {
			t := in.ExpiresAt.UTC()
			in.ExpiresAt = &t
		}
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		p, e := s.Store.SaveKnowledgeRecord(c.Request.Context(), in, create)
		respond(c, p, e)
	}
}
func (s *Service) saveAsset(create bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in domain.Asset
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if !create && !ids(c, c.Param("id")) {
			return
		}
		in.Name = strings.TrimSpace(in.Name)
		in.Identifier = strings.TrimSpace(in.Identifier)
		in.ModelVersion = strings.TrimSpace(in.ModelVersion)
		hash, e := hex.DecodeString(in.SHA256)
		valid := (in.Kind == "avatar" || in.Kind == "voice" || in.Kind == "model") && domain.TextWithin(in.Name, 1, 160) && domain.TextWithin(in.Identifier, 1, 200) && domain.TextWithin(in.ModelVersion, 0, 200) && e == nil && len(hash) == 32 && in.SHA256 == strings.ToLower(in.SHA256) && (!in.Active || in.Authorized) && ((create && in.Version == 0) || (!create && in.Version > 0))
		if !valid {
			fail(c, domain.Invalid("素材类型、名称、标签、SHA256、授权或版本无效。启用素材必须确认授权。"))
			return
		}
		in.ID = c.Param("id")
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		p, e := s.Store.SaveAsset(c.Request.Context(), in, create)
		respond(c, p, e)
	}
}
