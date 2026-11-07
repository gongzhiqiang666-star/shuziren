package api

import (
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

func (s *Service) registerLiveReadinessRoutes(a *gin.RouterGroup) {
	a.POST("/live-readiness/runs", func(c *gin.Context) {
		var in struct {
			ShopID     string `json:"shop_id"`
			Title      string `json:"title"`
			OutputMode string `json:"output_mode"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		in.Title = strings.TrimSpace(in.Title)
		if !domain.TextWithin(in.Title, 1, 160) || (in.OutputMode != "virtual_camera" && in.OutputMode != "srs") {
			fail(c, domain.Invalid("验证名称或输出模式无效。"))
			return
		}
		r, err := s.Store.CreateLiveReadinessRun(c.Request.Context(), in.ShopID, in.Title, in.OutputMode)
		respond(c, r, err)
	})
	a.GET("/live-readiness/runs", func(c *gin.Context) {
		shop, ok := queryShop(c)
		if !ok {
			return
		}
		r, err := s.Store.ListLiveReadinessRuns(c.Request.Context(), shop)
		respond(c, r, err)
	})
	a.GET("/live-readiness/runs/:id", func(c *gin.Context) {
		shop, ok := queryShop(c)
		if !ok || !ids(c, c.Param("id")) {
			return
		}
		r, err := s.Store.GetLiveReadinessRun(c.Request.Context(), shop, c.Param("id"))
		respond(c, r, err)
	})
	a.GET("/live-readiness/runs/:id/export", func(c *gin.Context) {
		shop, ok := queryShop(c)
		if !ok || !ids(c, c.Param("id")) {
			return
		}
		r, err := s.Store.GetLiveReadinessRun(c.Request.Context(), shop, c.Param("id"))
		respond(c, r, err)
	})
	a.PUT("/live-readiness/runs/:id/gates/:gate", func(c *gin.Context) {
		var in struct {
			ShopID   string         `json:"shop_id"`
			Version  int64          `json:"version"`
			Status   string         `json:"status"`
			Evidence map[string]any `json:"evidence"`
			Note     string         `json:"note"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, c.Param("id")) {
			return
		}
		g := domain.LiveReadinessGate{Name: c.Param("gate"), Status: in.Status, Evidence: in.Evidence, Note: strings.TrimSpace(in.Note)}
		if in.Version < 1 {
			fail(c, domain.Invalid("更新需提供当前版本。"))
			return
		}
		if err := domain.ValidateLiveReadinessGate(g); err != nil {
			fail(c, err)
			return
		}
		r, err := s.Store.UpdateLiveReadinessGate(c.Request.Context(), in.ShopID, c.Param("id"), in.Version, g)
		respond(c, r, err)
	})
}
