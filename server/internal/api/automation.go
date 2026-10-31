package api

import (
	"context"
	"errors"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

func (s *Service) RegisterAutomationRoutes(a *gin.RouterGroup) {
	a.GET("/generation/limits", func(c *gin.Context) {
		shop, valid := queryShop(c)
		if !valid {
			return
		}
		p, e := s.Store.GetGenerationLimits(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.PUT("/generation/limits", func(c *gin.Context) {
		var in struct {
			ShopID            string `json:"shop_id"`
			RequestsPerMinute int    `json:"requests_per_minute"`
			DailyRequestLimit int64  `json:"daily_request_limit"`
			DailyTokenLimit   int64  `json:"daily_token_limit"`
			Version           int64  `json:"version"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if in.RequestsPerMinute < 1 || in.RequestsPerMinute > 60 || in.DailyRequestLimit < 0 || in.DailyRequestLimit > 100000 || in.DailyTokenLimit < 0 || in.DailyTokenLimit > 1000000000 || in.Version < 0 {
			fail(c, domain.Invalid("生成限额或版本无效。0表示不设对应日限额。"))
			return
		}
		p, e := s.Store.SaveGenerationLimits(c.Request.Context(), domain.GenerationLimits{ShopID: in.ShopID, RequestsPerMinute: in.RequestsPerMinute, DailyRequestLimit: in.DailyRequestLimit, DailyTokenLimit: in.DailyTokenLimit, Version: in.Version})
		respond(c, p, e)
	})
	a.GET("/generation/usage", func(c *gin.Context) {
		shop, valid := queryShop(c)
		if !valid {
			return
		}
		p, e := s.Store.GenerationUsage(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.PUT("/jobs/:id/dispatch-policy", func(c *gin.Context) {
		var in struct {
			ShopID    string     `json:"shop_id"`
			Priority  int        `json:"priority"`
			ExpiresAt *time.Time `json:"expires_at"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, c.Param("id")) {
			return
		}
		if in.Priority < 0 || in.Priority > 100 || (in.ExpiresAt != nil && !in.ExpiresAt.After(time.Now())) {
			fail(c, domain.Invalid("优先级应为0至100，截止时间应在未来或为null。"))
			return
		}
		p, e := s.Store.SetDispatchPolicy(c.Request.Context(), in.ShopID, c.Param("id"), in.Priority, in.ExpiresAt)
		respond(c, p, e)
	})
	a.POST("/jobs/:id/schedule", func(c *gin.Context) {
		var in struct {
			ShopID    string    `json:"shop_id"`
			RunAt     time.Time `json:"run_at"`
			ExpiresAt time.Time `json:"expires_at"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, c.Param("id")) {
			return
		}
		now := time.Now()
		if !in.RunAt.After(now) || in.RunAt.After(now.Add(7*24*time.Hour)) || !in.ExpiresAt.After(in.RunAt) || in.ExpiresAt.After(in.RunAt.Add(time.Hour)) {
			fail(c, domain.Invalid("定时派发需在未来7天内，允许窗口应为计划时间后的1小时以内。"))
			return
		}
		j, e := s.Store.GetJob(c.Request.Context(), in.ShopID, c.Param("id"))
		if e != nil {
			fail(c, e)
			return
		}
		if j.Status != "ready" && (s.Media == nil || !s.Media.TTSConfigured()) {
			fail(c, domain.Unavailable("tts_not_configured", "尚未配置本地语音服务，不能安排未合成任务。"))
			return
		}
		p, e := s.Store.CreateSchedule(c.Request.Context(), in.ShopID, c.Param("id"), in.RunAt, in.ExpiresAt)
		if e == nil {
			s.Wake()
		}
		respond(c, p, e)
	})
	a.GET("/schedules", func(c *gin.Context) {
		shop, valid := queryShop(c)
		if !valid {
			return
		}
		session := c.Query("session_id")
		if session != "" && !ids(c, session) {
			return
		}
		p, e := s.Store.ListSchedules(c.Request.Context(), shop, session)
		respond(c, p, e)
	})
	a.POST("/schedules/:id/cancel", func(c *gin.Context) {
		shop, valid := bodyShop(c)
		if !valid {
			return
		}
		p, e := s.Store.CancelSchedule(c.Request.Context(), shop, c.Param("id"))
		respond(c, p, e)
	})
}
func (s *Service) RunScheduler(ctx context.Context) {
	t := time.NewTicker(time.Second)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		p, err := s.Store.ClaimSchedule(ctx)
		if err == nil {
			s.dispatchScheduled(ctx, p)
			continue
		}
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}
func (s *Service) dispatchScheduled(ctx context.Context, p domain.SpeechSchedule) {
	j, err := s.Send(ctx, p.ShopID, p.JobID)
	status, reason, code := "delivery_unknown", "定时派发结果不明，请接管核对，禁止自动重播。", "schedule_delivery_unknown"
	if err == nil {
		switch j.Status {
		case "sent":
			status = "sent"
			reason = "上游已接收定时音频；不代表实际播出完成。"
			code = ""
		case "delivery_unknown", "sending":
		default:
			status = "failed"
			reason = "任务未进入上游，请核对后重新安排。"
			code = "job_state_changed"
		}
	} else {
		c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		current, readErr := s.Store.GetJob(c, p.ShopID, p.JobID)
		cancel()
		if readErr == nil {
			switch current.Status {
			case "sent":
				status = "sent"
				reason = "该任务的上游接收已记录；不会再次派发。"
				code = ""
			case "sending", "delivery_unknown":
			default:
				status = "failed"
				reason = "任务未派发，请核对场次、音频与输出连接后重新安排。"
				code = "schedule_failed"
				var d *domain.Error
				if errors.As(err, &d) {
					code = d.Code
				}
			}
		}
	}
	c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
	defer cancel()
	_ = s.Store.FinishSchedule(c, p.ShopID, p.ID, status, reason, code)
}
