package api

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
)

const Version = "0.1.0"

func Router(s *Service, token, webDist string) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.RedirectTrailingSlash = false
	r.RedirectFixedPath = false
	r.HandleMethodNotAllowed = true
	expected := sha256.Sum256([]byte("Bearer " + token))
	r.Use(func(c *gin.Context) {
		c.Header("X-Content-Type-Options", "nosniff")
		c.Header("Referrer-Policy", "no-referrer")
		if c.Request.URL.Path == "/api/v1" || strings.HasPrefix(c.Request.URL.Path, "/api/v1/") {
			c.Header("Cache-Control", "no-store")
			supplied := sha256.Sum256([]byte(c.GetHeader("Authorization")))
			if len(token) < 24 || subtle.ConstantTimeCompare(supplied[:], expected[:]) != 1 {
				c.Header("WWW-Authenticate", "Bearer")
				fail(c, &domain.Error{Status: 401, Code: "unauthorized", Message: "请提供有效的本地工作台访问口令。"})
				return
			}
		}
		c.Next()
	})
	// Gin's default panic logger prints headers; a bearer secret must never be
	// included in a panic dump. This recovery returns a fixed safe response.
	r.Use(func(c *gin.Context) {
		defer func() {
			if recover() != nil {
				fail(c, &domain.Error{Status: 500, Code: "internal_error", Message: "服务内部错误，请重试或查看本地状态。"})
			}
		}()
		c.Next()
	})
	r.GET("/healthz", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok"}) })
	a := r.Group("/api/v1")
	a.GET("/status", func(c *gin.Context) {
		ctx, cancel := context.WithTimeout(c.Request.Context(), 2*time.Second)
		defer cancel()
		if err := s.Store.Ping(ctx); err != nil {
			fail(c, domain.Unavailable("storage_unavailable", "数据服务暂不可用。"))
			return
		}
		configured := s.Generator != nil && s.Generator.Configured()
		model := "deepseek-flash"
		if s.Generator != nil {
			model = s.Generator.Model()
		}
		ok(c, gin.H{"version": Version, "storage": "postgresql", "deepseek": gin.H{"configured": configured, "model": model}, "media": gin.H{"tts_configured": s.Media != nil && s.Media.TTSConfigured(), "live_configured": s.Media != nil && s.Media.LiveConfigured()}, "taobao": gin.H{"status": "not_connected"}, "retrieval": gin.H{"mode": "keyword"}})
	})
	a.GET("/shops", func(c *gin.Context) { p, e := s.Store.ListShops(c.Request.Context()); respond(c, p, e) })
	a.POST("/shops", func(c *gin.Context) {
		var in struct {
			Name string `json:"name"`
		}
		if !decode(c, &in) {
			return
		}
		in.Name = strings.TrimSpace(in.Name)
		if !domain.TextWithin(in.Name, 1, 120) {
			fail(c, domain.Invalid("店铺名应为1至120字。"))
			return
		}
		p, e := s.Store.CreateShop(c.Request.Context(), in.Name)
		respond(c, p, e)
	})
	a.GET("/products", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListProducts(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.POST("/products", s.saveProduct(true))
	a.PUT("/products/:id", s.saveProduct(false))
	a.GET("/persona", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.GetPersona(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.PUT("/persona", func(c *gin.Context) {
		var in struct {
			ShopID  string `json:"shop_id"`
			Name    string `json:"name"`
			Tone    string `json:"tone"`
			Prompt  string `json:"prompt"`
			Version int64  `json:"version"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		in.Name = strings.TrimSpace(in.Name)
		in.Tone = strings.TrimSpace(in.Tone)
		in.Prompt = strings.TrimSpace(in.Prompt)
		if !domain.TextWithin(in.Name, 1, 120) || !domain.TextWithin(in.Tone, 1, 500) || !domain.TextWithin(in.Prompt, 0, 4000) || in.Version < 1 {
			fail(c, domain.Invalid("人格名称、语气、提示内容或版本无效。"))
			return
		}
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		p, e := s.Store.SavePersona(c.Request.Context(), domain.Persona{ShopID: in.ShopID, Name: in.Name, Tone: in.Tone, Prompt: in.Prompt, Version: in.Version})
		respond(c, p, e)
	})
	a.GET("/knowledge", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListKnowledge(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.POST("/knowledge", s.saveKnowledge(true))
	a.PUT("/knowledge/:id", s.saveKnowledge(false))
	a.DELETE("/knowledge/:id", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes || !ids(c, c.Param("id")) {
			return
		}
		gate := s.shopLock(shop)
		gate.Lock()
		defer gate.Unlock()
		e := s.Store.DeleteKnowledge(c.Request.Context(), shop, c.Param("id"))
		respond(c, gin.H{"deleted": true}, e)
	})
	a.GET("/sessions", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.ListSessions(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.POST("/sessions", func(c *gin.Context) {
		var in struct {
			ShopID string `json:"shop_id"`
			Title  string `json:"title"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		in.Title = strings.TrimSpace(in.Title)
		if !domain.TextWithin(in.Title, 1, 160) {
			fail(c, domain.Invalid("场次标题应为1至160字。"))
			return
		}
		p, e := s.Store.CreateSession(c.Request.Context(), in.ShopID, in.Title)
		respond(c, p, e)
	})
	a.POST("/sessions/:id/takeover", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		p, e := s.Takeover(c.Request.Context(), shop, c.Param("id"), "takeover")
		respond(c, p, e)
	})
	a.POST("/sessions/:id/end", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		p, e := s.Takeover(c.Request.Context(), shop, c.Param("id"), "end")
		respond(c, p, e)
	})
	a.POST("/sessions/:id/resume", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		p, e := s.Resume(c.Request.Context(), shop, c.Param("id"))
		respond(c, p, e)
	})
	a.POST("/sessions/:id/media/offer", func(c *gin.Context) {
		var in struct {
			ShopID string `json:"shop_id"`
			SDP    string `json:"sdp"`
			Type   string `json:"type"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, c.Param("id")) {
			return
		}
		if in.Type != "offer" || len(in.SDP) > 512<<10 || !strings.HasPrefix(in.SDP, "v=0") {
			fail(c, domain.Invalid("WebRTC offer 无效。"))
			return
		}
		p, e := s.Negotiate(c.Request.Context(), in.ShopID, c.Param("id"), media.Offer{SDP: in.SDP, Type: in.Type})
		respond(c, p, e)
	})
	a.GET("/jobs", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		session := c.Query("session_id")
		if session != "" && !ids(c, session) {
			return
		}
		p, e := s.Store.ListJobs(c.Request.Context(), shop, session)
		respond(c, p, e)
	})
	a.POST("/jobs/manual", s.createJob(false))
	a.POST("/jobs/generate", s.createJob(true))
	a.POST("/jobs/:id/approve", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		p, e := s.Store.Approve(c.Request.Context(), shop, c.Param("id"))
		respond(c, p, e)
	})
	a.POST("/jobs/:id/synthesize", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		if s.Media == nil || !s.Media.TTSConfigured() {
			fail(c, domain.Unavailable("tts_not_configured", "尚未配置本地 CosyVoice 语音服务。"))
			return
		}
		p, e := s.Store.QueueSynthesis(c.Request.Context(), shop, c.Param("id"))
		if e == nil {
			s.Wake()
		}
		respond(c, p, e)
	})
	a.POST("/jobs/:id/send", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		p, e := s.Send(c.Request.Context(), shop, c.Param("id"))
		respond(c, p, e)
	})
	a.POST("/jobs/:id/cancel", func(c *gin.Context) {
		shop, yes := bodyShop(c)
		if !yes {
			return
		}
		p, e := s.Store.CancelJob(c.Request.Context(), shop, c.Param("id"))
		if e == nil {
			s.cancelOperations("", p.ID)
		}
		respond(c, p, e)
	})
	a.GET("/jobs/:id/audio", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes || !ids(c, c.Param("id")) {
			return
		}
		j, e := s.Store.GetJob(c.Request.Context(), shop, c.Param("id"))
		if e != nil {
			fail(c, e)
			return
		}
		if !j.AudioReady {
			fail(c, domain.Conflict("audio_not_ready", "该任务尚未生成可预听音频。"))
			return
		}
		b, e := s.readAudio(j.ID)
		if e != nil {
			fail(c, e)
			return
		}
		c.Header("Content-Disposition", "inline; filename=\"speech.wav\"")
		c.Data(200, "audio/wav", b)
	})
	a.GET("/quality", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		p, e := s.Store.GetQuality(c.Request.Context(), shop)
		respond(c, p, e)
	})
	a.PUT("/quality", s.saveQuality())
	r.NoMethod(func(c *gin.Context) {
		fail(c, &domain.Error{Status: 405, Code: "method_not_allowed", Message: "此接口不支持该请求方法。"})
	})
	r.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") || c.Request.Method != http.MethodGet || webDist == "" {
			fail(c, &domain.Error{Status: 404, Code: "not_found", Message: "未找到此页面或接口。"})
			return
		}
		serveFrontend(c, webDist)
	})
	return r
}

func (s *Service) saveProduct(create bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in struct {
			ShopID      string     `json:"shop_id"`
			Title       string     `json:"title"`
			SKU         string     `json:"sku"`
			Description string     `json:"description"`
			Specs       string     `json:"specs"`
			PriceCents  *int64     `json:"price_cents"`
			Stock       *int64     `json:"stock"`
			Active      *bool      `json:"active"`
			Version     int64      `json:"version"`
			ExpiresAt   *time.Time `json:"expires_at"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if !create && !ids(c, c.Param("id")) {
			return
		}
		in.Title = strings.TrimSpace(in.Title)
		in.SKU = strings.TrimSpace(in.SKU)
		in.Description = strings.TrimSpace(in.Description)
		in.Specs = strings.TrimSpace(in.Specs)
		if !domain.TextWithin(in.Title, 1, 200) || !domain.TextWithin(in.SKU, 1, 120) || !domain.TextWithin(in.Description, 0, 4000) || !domain.TextWithin(in.Specs, 0, 4000) || in.PriceCents == nil || in.Stock == nil || *in.PriceCents < 0 || *in.PriceCents > 1000000000000 || *in.Stock < 0 || *in.Stock > 1000000000000 || (!create && in.Version < 1) || (create && in.Version != 0) {
			fail(c, domain.Invalid("商品字段无效；金额必须使用非负整数分，编辑需提供当前版本。"))
			return
		}
		active := true
		if in.Active != nil {
			active = *in.Active
		}
		if in.ExpiresAt != nil {
			t := in.ExpiresAt.UTC()
			in.ExpiresAt = &t
		}
		p := domain.Product{ID: c.Param("id"), ShopID: in.ShopID, Title: in.Title, SKU: in.SKU, Description: in.Description, Specs: in.Specs, PriceCents: *in.PriceCents, Stock: *in.Stock, Active: active, Version: in.Version, ExpiresAt: in.ExpiresAt}
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		p, e := s.Store.SaveProduct(c.Request.Context(), p, create)
		respond(c, p, e)
	}
}
func (s *Service) saveKnowledge(create bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in struct {
			ShopID  string `json:"shop_id"`
			Title   string `json:"title"`
			Content string `json:"content"`
			Kind    string `json:"kind"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if !create && !ids(c, c.Param("id")) {
			return
		}
		in.Title = strings.TrimSpace(in.Title)
		in.Content = strings.TrimSpace(in.Content)
		if !domain.TextWithin(in.Title, 1, 120) || !domain.TextWithin(in.Content, 1, 4000) || (in.Kind != "faq" && in.Kind != "memory") {
			fail(c, domain.Invalid("知识标题、内容或类型无效。"))
			return
		}
		gate := s.shopLock(in.ShopID)
		gate.Lock()
		defer gate.Unlock()
		p, e := s.Store.SaveKnowledge(c.Request.Context(), domain.Knowledge{ID: c.Param("id"), ShopID: in.ShopID, Title: in.Title, Content: in.Content, Kind: in.Kind}, create)
		respond(c, p, e)
	}
}
func (s *Service) createJob(generated bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in struct {
			ShopID    string `json:"shop_id"`
			SessionID string `json:"session_id"`
			ProductID string `json:"product_id"`
			Text      string `json:"text"`
			Question  string `json:"question"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID, in.ProductID) {
			return
		}
		in.Text = strings.TrimSpace(in.Text)
		in.Question = strings.TrimSpace(in.Question)
		if generated {
			if !domain.TextWithin(in.Question, 1, 2000) || in.Text != "" {
				fail(c, domain.Invalid("问题应为1至2000字，生成接口不接受预设回答。"))
				return
			}
			p, e := s.Generate(c.Request.Context(), in.ShopID, in.SessionID, in.ProductID, in.Question)
			respond(c, p, e)
		} else {
			if !domain.TextWithin(in.Text, 1, 2000) || in.Question != "" {
				fail(c, domain.Invalid("人工草稿应为1至2000字。"))
				return
			}
			p, e := s.Manual(c.Request.Context(), in.ShopID, in.SessionID, in.ProductID, in.Text)
			respond(c, p, e)
		}
	}
}
func (s *Service) saveQuality() gin.HandlerFunc {
	return func(c *gin.Context) {
		var in struct {
			ShopID           string                `json:"shop_id"`
			AvatarName       string                `json:"avatar_name"`
			SourceResolution string                `json:"source_resolution"`
			ModelVersion     string                `json:"model_version"`
			CanvasResolution string                `json:"canvas_resolution"`
			FPS              int                   `json:"fps"`
			SyncTargetMS     int                   `json:"sync_target_ms"`
			Notes            string                `json:"notes"`
			Checks           []domain.QualityCheck `json:"checks"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		valid := domain.TextWithin(in.AvatarName, 0, 160) && domain.TextWithin(in.SourceResolution, 0, 120) && domain.TextWithin(in.ModelVersion, 0, 200) && domain.TextWithin(in.CanvasResolution, 0, 120) && domain.TextWithin(in.Notes, 0, 6000) && in.FPS >= 1 && in.FPS <= 120 && in.SyncTargetMS >= 0 && in.SyncTargetMS <= 2000 && len(in.Checks) <= 40
		seen := map[string]bool{}
		for _, check := range in.Checks {
			if !domain.TextWithin(check.Key, 1, 80) || !domain.TextWithin(check.Label, 1, 160) || !domain.TextWithin(check.Notes, 0, 2000) || seen[check.Key] {
				valid = false
			}
			seen[check.Key] = true
		}
		if !valid {
			fail(c, domain.Invalid("质量档案字段、检查项或数值范围无效。"))
			return
		}
		p, e := s.Store.SaveQuality(c.Request.Context(), domain.QualityProfile{ShopID: in.ShopID, AvatarName: in.AvatarName, SourceResolution: in.SourceResolution, ModelVersion: in.ModelVersion, CanvasResolution: in.CanvasResolution, FPS: in.FPS, SyncTargetMS: in.SyncTargetMS, Notes: in.Notes, Checks: in.Checks})
		respond(c, p, e)
	}
}

func decode(c *gin.Context, dst any) bool {
	if c.GetHeader("Content-Type") != "" {
		kind, _, err := mime.ParseMediaType(c.GetHeader("Content-Type"))
		if err != nil || kind != "application/json" {
			fail(c, domain.Invalid("请求应使用 application/json。"))
			return false
		}
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 1<<20)
	d := json.NewDecoder(c.Request.Body)
	d.DisallowUnknownFields()
	if err := d.Decode(dst); err != nil {
		fail(c, domain.Invalid("JSON字段、类型或长度无效。"))
		return false
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		fail(c, domain.Invalid("请求只能包含一个完整的JSON对象。"))
		return false
	}
	return true
}
func ids(c *gin.Context, values ...string) bool {
	for _, id := range values {
		if !domain.ValidID(id) {
			fail(c, domain.Invalid("店铺或资源标识必须是UUID。"))
			return false
		}
	}
	return true
}
func queryShop(c *gin.Context) (string, bool) { shop := c.Query("shop_id"); return shop, ids(c, shop) }
func bodyShop(c *gin.Context) (string, bool) {
	var in struct {
		ShopID string `json:"shop_id"`
	}
	if !decode(c, &in) {
		return "", false
	}
	return in.ShopID, ids(c, in.ShopID, c.Param("id"))
}
func ok(c *gin.Context, data any) { c.JSON(http.StatusOK, gin.H{"data": data}) }
func respond(c *gin.Context, data any, err error) {
	if err != nil {
		fail(c, err)
		return
	}
	ok(c, data)
}
func fail(c *gin.Context, err error) {
	var e *domain.Error
	if !errors.As(err, &e) {
		switch {
		case errors.Is(err, context.Canceled):
			e = &domain.Error{Status: 409, Code: "operation_cancelled", Message: "操作已中断，请刷新场次和任务状态。"}
		case errors.Is(err, context.DeadlineExceeded):
			e = &domain.Error{Status: 504, Code: "operation_timeout", Message: "操作超时，请先检查当前状态，发送结果不明时不能重播。"}
		default:
			e = &domain.Error{Status: 500, Code: "internal_error", Message: "服务内部错误，请检查本地服务状态。"}
		}
	}
	c.AbortWithStatusJSON(e.Status, gin.H{"error": gin.H{"code": e.Code, "message": e.Message}})
}
func serveFrontend(c *gin.Context, root string) {
	root, err := filepath.Abs(root)
	if err != nil {
		c.Status(404)
		return
	}
	rel := filepath.Clean("/" + c.Request.URL.Path)
	file := filepath.Join(root, strings.TrimPrefix(rel, "/"))
	info, err := os.Stat(file)
	if err != nil || info.IsDir() {
		if filepath.Ext(c.Request.URL.Path) != "" {
			c.Status(404)
			return
		}
		file = filepath.Join(root, "index.html")
	}
	resolved, err := filepath.EvalSymlinks(file)
	if err != nil {
		c.Status(404)
		return
	}
	base, err := filepath.EvalSymlinks(root)
	if err != nil {
		c.Status(404)
		return
	}
	inside, err := filepath.Rel(base, resolved)
	if err != nil || inside == ".." || strings.HasPrefix(inside, ".."+string(filepath.Separator)) {
		c.Status(404)
		return
	}
	if strings.HasPrefix(filepath.Base(file), ".") {
		c.Status(404)
		return
	}
	http.ServeFile(c.Writer, c.Request, resolved)
}
