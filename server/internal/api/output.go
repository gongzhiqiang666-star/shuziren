package api

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"regexp"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
)

type OutputControlResult struct {
	Output          domain.OutputStatus `json:"output"`
	MediaStopStatus string              `json:"media_stop_status"`
}
type OutputIssueResult struct {
	OutputControlResult
	Token      string `json:"token"`
	OutputPath string `json:"output_path"`
}
type OutputOfferResult struct {
	media.Answer
	LeaseID string              `json:"lease_id"`
	Output  domain.OutputStatus `json:"output"`
}

func outputTokenHash(token string) ([]byte, bool) {
	if !strings.HasPrefix(token, "out_") || len(token) != 47 {
		return nil, false
	}
	b, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(token, "out_"))
	if err != nil || len(b) != 32 {
		return nil, false
	}
	sum := sha256.Sum256([]byte(token))
	return sum[:], true
}
func (s *Service) authorizeOutput(c *gin.Context) bool {
	value := c.GetHeader("Authorization")
	if !strings.HasPrefix(value, "Bearer ") {
		fail(c, domain.OutputUnauthorized())
		return false
	}
	hash, valid := outputTokenHash(strings.TrimPrefix(value, "Bearer "))
	if !valid {
		fail(c, domain.OutputUnauthorized())
		return false
	}
	if s.Store == nil {
		fail(c, domain.Unavailable("storage_unavailable", "数据服务暂不可用。"))
		return false
	}
	a, err := s.Store.AuthenticateOutput(c.Request.Context(), hash)
	if err != nil {
		fail(c, err)
		return false
	}
	c.Set("output_auth", a)
	return true
}
func outputAuth(c *gin.Context) domain.OutputAuth {
	return c.MustGet("output_auth").(domain.OutputAuth)
}
func (s *Service) stopOutputMedia(ctx context.Context, shop, session string, id *string) string {
	status := "not_connected"
	if id != nil && (s.Media == nil || !s.Media.LiveConfigured()) {
		status = "failed"
	}
	if id != nil && s.Media != nil && s.Media.LiveConfigured() {
		c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 35*time.Second)
		defer cancel()
		err := s.Media.Interrupt(c, *id)
		switch {
		case errors.Is(err, media.ErrSessionNotFound):
		case err != nil:
			status = "failed"
		default:
			status = "sent"
		}
	}
	c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	_ = s.Store.RecordMediaStop(c, shop, session, status)
	return status
}
func (s *Service) IssueOutput(ctx context.Context, shop, id string) (OutputIssueResult, error) {
	var raw [32]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return OutputIssueResult{}, domain.Unavailable("secure_random_unavailable", "暂时无法生成安全输出令牌。")
	}
	token := "out_" + base64.RawURLEncoding.EncodeToString(raw[:])
	hash, _ := outputTokenHash(token)
	l := s.sessionLock(id)
	l.control.Lock()
	defer l.control.Unlock()
	status, stop, err := s.Store.IssueOutput(ctx, shop, id, hash)
	if err != nil {
		return OutputIssueResult{}, err
	}
	l.dispatch.Lock()
	defer l.dispatch.Unlock()
	stopped := s.stopOutputMedia(ctx, shop, id, stop)
	return OutputIssueResult{OutputControlResult: OutputControlResult{Output: status, MediaStopStatus: stopped}, Token: token, OutputPath: "/output#token=" + token}, nil
}
func (s *Service) RevokeOutput(ctx context.Context, shop, id string) (OutputControlResult, error) {
	l := s.sessionLock(id)
	l.control.Lock()
	defer l.control.Unlock()
	status, stop, err := s.Store.RevokeOutput(ctx, shop, id)
	if err != nil {
		return OutputControlResult{}, err
	}
	s.cancelOperations(id, "")
	l.dispatch.Lock()
	defer l.dispatch.Unlock()
	return OutputControlResult{Output: status, MediaStopStatus: s.stopOutputMedia(ctx, shop, id, stop)}, nil
}
func (s *Service) OfferOutput(ctx context.Context, a domain.OutputAuth, receiver string, offer media.Offer) (OutputOfferResult, error) {
	if s.Media == nil || !s.Media.LiveConfigured() {
		return OutputOfferResult{}, domain.Unavailable("media_not_configured", "尚未配置 LiveTalking 服务。")
	}
	ctx, done := s.register(ctx, a.SessionID, "")
	defer done()
	locks := s.sessionLock(a.SessionID)
	locks.dispatch.Lock()
	defer locks.dispatch.Unlock()
	lease, err := s.Store.ClaimOutput(ctx, a, receiver)
	if err != nil {
		return OutputOfferResult{}, err
	}
	abort := func() {
		c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		defer cancel()
		_, _, _ = s.Store.ReleaseOutput(c, a, receiver, lease.ID)
	}
	if lease.OldMediaID != nil {
		if err = s.Media.Interrupt(ctx, *lease.OldMediaID); err != nil && !errors.Is(err, media.ErrSessionNotFound) {
			abort()
			return OutputOfferResult{}, domain.Unavailable("media_stop_failed", "旧媒体会话停止失败，请在工作台核对上游后再连接。")
		}
	}
	answer, err := s.Media.Negotiate(ctx, offer)
	if err != nil {
		abort()
		return OutputOfferResult{}, mediaError(err)
	}
	status, err := s.Store.BindOutput(ctx, a, lease, answer.SessionID)
	if err != nil {
		c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		_ = s.Media.Interrupt(c, answer.SessionID)
		abort()
		return OutputOfferResult{}, err
	}
	return OutputOfferResult{Answer: answer, LeaseID: lease.ID, Output: status}, nil
}
func (s *Service) ReleaseOutput(ctx context.Context, a domain.OutputAuth, receiver, lease string) (OutputControlResult, error) {
	status, stop, err := s.Store.ReleaseOutput(ctx, a, receiver, lease)
	if err != nil {
		return OutputControlResult{}, err
	}
	l := s.sessionLock(a.SessionID)
	l.dispatch.Lock()
	defer l.dispatch.Unlock()
	return OutputControlResult{Output: status, MediaStopStatus: s.stopOutputMedia(ctx, a.ShopID, a.SessionID, stop)}, nil
}

var outputColor = regexp.MustCompile(`^#[0-9a-fA-F]{6}$`)

func (s *Service) RegisterOutputRoutes(r *gin.Engine, a *gin.RouterGroup) {
	a.GET("/sessions/:id/output", func(c *gin.Context) {
		shop, valid := queryShop(c)
		if !valid || !ids(c, c.Param("id")) {
			return
		}
		p, e := s.Store.GetOutput(c.Request.Context(), shop, c.Param("id"), "")
		respond(c, p, e)
	})
	a.PUT("/sessions/:id/output", func(c *gin.Context) {
		var in struct {
			ShopID     string `json:"shop_id"`
			Width      int    `json:"width"`
			Height     int    `json:"height"`
			Fit        string `json:"fit"`
			Background string `json:"background"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, c.Param("id")) {
			return
		}
		if in.Width < 160 || in.Width > 3840 || in.Height < 160 || in.Height > 3840 || (in.Fit != "contain" && in.Fit != "cover") || !outputColor.MatchString(in.Background) {
			fail(c, domain.Invalid("输出画布尺寸、缩放方式或背景颜色无效。"))
			return
		}
		p, e := s.Store.SaveOutputConfig(c.Request.Context(), in.ShopID, c.Param("id"), domain.OutputConfig{Width: in.Width, Height: in.Height, Fit: in.Fit, Background: strings.ToUpper(in.Background)})
		respond(c, p, e)
	})
	a.POST("/sessions/:id/output/issue", func(c *gin.Context) {
		shop, valid := bodyShop(c)
		if !valid {
			return
		}
		p, e := s.IssueOutput(c.Request.Context(), shop, c.Param("id"))
		respond(c, p, e)
	})
	a.POST("/sessions/:id/output/revoke", func(c *gin.Context) {
		shop, valid := bodyShop(c)
		if !valid {
			return
		}
		p, e := s.RevokeOutput(c.Request.Context(), shop, c.Param("id"))
		respond(c, p, e)
	})
	o := r.Group("/output-api/v1")
	o.GET("/status", func(c *gin.Context) {
		receiver := c.Query("receiver_id")
		if !ids(c, receiver) {
			return
		}
		p, e := s.Store.GetScopedOutput(c.Request.Context(), outputAuth(c), receiver)
		respond(c, p, e)
	})
	o.POST("/offer", func(c *gin.Context) {
		var in struct {
			ReceiverID string `json:"receiver_id"`
			SDP        string `json:"sdp"`
			Type       string `json:"type"`
		}
		if !decode(c, &in) || !ids(c, in.ReceiverID) {
			return
		}
		if in.Type != "offer" || len(in.SDP) > 512<<10 || !strings.HasPrefix(in.SDP, "v=0") {
			fail(c, domain.Invalid("WebRTC offer 无效。"))
			return
		}
		p, e := s.OfferOutput(c.Request.Context(), outputAuth(c), in.ReceiverID, media.Offer{SDP: in.SDP, Type: in.Type})
		respond(c, p, e)
	})
	o.POST("/heartbeat", func(c *gin.Context) {
		var in domain.OutputHeartbeat
		if !decode(c, &in) || !ids(c, in.ReceiverID, in.LeaseID) {
			return
		}
		switch in.PeerState {
		case "new", "connecting", "connected", "disconnected", "failed", "closed":
		default:
			fail(c, domain.Invalid("peer_state 必须来自实际 WebRTC 连接状态。"))
			return
		}
		p, e := s.Store.HeartbeatOutput(c.Request.Context(), outputAuth(c), in)
		respond(c, p, e)
	})
	o.POST("/release", func(c *gin.Context) {
		var in struct {
			ReceiverID string `json:"receiver_id"`
			LeaseID    string `json:"lease_id"`
		}
		if !decode(c, &in) || !ids(c, in.ReceiverID, in.LeaseID) {
			return
		}
		p, e := s.ReleaseOutput(c.Request.Context(), outputAuth(c), in.ReceiverID, in.LeaseID)
		respond(c, p, e)
	})
}
