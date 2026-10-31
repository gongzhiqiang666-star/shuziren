package api

import (
	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"strconv"
	"strings"
)

func (s *Service) RegisterTemplateRoutes(a *gin.RouterGroup) {
	a.GET("/templates", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListTemplates(c.Request.Context(), shop)
		respond(c, p, e)
	})
	save := func(create bool) gin.HandlerFunc {
		return func(c *gin.Context) {
			var in struct {
				ShopID  string `json:"shop_id"`
				Name    string `json:"name"`
				Body    string `json:"body"`
				Version int64  `json:"version"`
			}
			if !decode(c, &in) || !ids(c, in.ShopID) {
				return
			}
			if !create && !ids(c, c.Param("id")) {
				return
			}
			if (create && in.Version != 0) || (!create && in.Version < 1) {
				fail(c, domain.Invalid("模板版本无效。"))
				return
			}
			p, e := s.Store.SaveTemplate(c.Request.Context(), domain.SpeechTemplate{ID: c.Param("id"), ShopID: in.ShopID, Name: strings.TrimSpace(in.Name), Body: strings.TrimSpace(in.Body), Version: in.Version}, create)
			respond(c, p, e)
		}
	}
	a.POST("/templates", save(true))
	a.PUT("/templates/:id", save(false))
	a.DELETE("/templates/:id", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes || !ids(c, c.Param("id")) {
			return
		}
		v, e := strconv.ParseInt(c.Query("version"), 10, 64)
		if e != nil || v < 1 {
			fail(c, domain.Invalid("删除模板需提供当前版本。"))
			return
		}
		e = s.Store.DeleteTemplate(c.Request.Context(), shop, c.Param("id"), v)
		respond(c, gin.H{"deleted": true}, e)
	})
	a.POST("/templates/:id/apply", func(c *gin.Context) {
		var in struct {
			ShopID    string `json:"shop_id"`
			SessionID string `json:"session_id"`
			ProductID string `json:"product_id"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID, in.ProductID, c.Param("id")) {
			return
		}
		ctx := c.Request.Context()
		template, e := s.Store.GetTemplate(ctx, in.ShopID, c.Param("id"))
		if e != nil {
			fail(c, e)
			return
		}
		snap, e := s.Store.Snapshot(ctx, in.ShopID, in.SessionID, in.ProductID)
		if e != nil {
			fail(c, e)
			return
		}
		text, e := domain.RenderTemplate(template.Body, snap.Product)
		if e != nil {
			fail(c, e)
			return
		}
		j, e := s.Store.CreateJob(ctx, snap, domain.Job{Source: "manual", Text: text, Status: "draft", Reason: "由商品模板展开；固定文字和当前事实仍需人工审核。"})
		respond(c, j, e)
	})
}
