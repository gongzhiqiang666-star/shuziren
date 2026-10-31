package api

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/gin-gonic/gin"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/config"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/deepseek"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/retrieval"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/taobao"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
	"unicode/utf8"
)

type integrationState struct {
	bge                   *retrieval.Client
	tb                    *taobao.Client
	shop                  string
	pollEnabled           bool
	mu                    sync.Mutex
	pollMu                sync.Mutex
	lastPoll, lastSuccess *time.Time
	lastError             string
}

func (s *Service) ConfigureIntegrations(cfg config.Integrations) error {
	bge, e := retrieval.New(cfg.Retrieval)
	if e != nil {
		return e
	}
	tb, e := taobao.New(cfg.Taobao)
	if e != nil {
		return e
	}
	if tb.Configured() && !domain.ValidID(cfg.TaobaoShopID) {
		return errors.New("TAOBAO_SHOP_ID must bind one local shop")
	}
	if cfg.PollEnabled && !tb.Configured() {
		return errors.New("Taobao polling requires credentials")
	}
	s.integrations = &integrationState{bge: bge, tb: tb, shop: cfg.TaobaoShopID, pollEnabled: cfg.PollEnabled}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return s.Store.RecoverIntegrations(ctx)
}
func (s *Service) IntegrationStatus() (any, any) {
	tb := gin.H{"configured": false, "shop_id": "", "transport": "top_http_poll", "polling": false, "last_poll_at": nil, "last_success_at": nil, "last_error_code": "", "status": "not_configured"}
	r := gin.H{"mode": "keyword", "configured": false, "model": retrieval.Model}
	x := s.integrations
	if x == nil {
		return tb, r
	}
	x.mu.Lock()
	defer x.mu.Unlock()
	tb["configured"] = x.tb.Configured()
	tb["shop_id"] = x.shop
	tb["polling"] = x.pollEnabled
	tb["last_poll_at"] = x.lastPoll
	tb["last_success_at"] = x.lastSuccess
	tb["last_error_code"] = x.lastError
	if x.tb.Configured() {
		tb["status"] = "configured_unverified"
	}
	if x.lastSuccess != nil {
		tb["status"] = "last_poll_succeeded"
	}
	if x.lastError != "" {
		tb["status"] = "poll_failed"
	}
	r["configured"] = x.bge.Configured()
	if x.bge.Configured() {
		r["mode"] = "bge"
	}
	return tb, r
}
func (s *Service) PrepareGeneration(ctx context.Context, snap domain.Snapshot, question string) (context.Context, error) {
	records, _, e := s.retrieve(ctx, snap, question)
	if e != nil {
		return ctx, e
	}
	return deepseek.WithKnowledge(ctx, records), nil
}
func (s *Service) retrieve(ctx context.Context, snap domain.Snapshot, q string) ([]domain.Knowledge, string, error) {
	if s.integrations == nil || !s.integrations.bge.Configured() {
		return domain.SelectKnowledge(snap.Knowledge, q, snap.Product.Title), "keyword", nil
	}
	client := s.integrations.bge
	ctx, cancel := context.WithTimeout(ctx, 50*time.Second)
	defer cancel()
	// Product/session scope is already enforced by Snapshot. Appending a product
	// title here can drown out the actual question (e.g. returns vs. cup specs).
	// Structured product facts are supplied to the generator separately.
	query, e := client.Embed(ctx, []string{q}, true)
	if e != nil {
		return nil, "bge", domain.Unavailable("retrieval_unavailable", "本地 BGE 服务不可用，请检查模型与服务；本次没有调用 DeepSeek。")
	}
	type candidate struct {
		k      domain.Knowledge
		hash   string
		vector []float32
		score  float64
	}
	candidates := make([]candidate, 0, len(snap.Knowledge))
	missing := []int{}
	for _, k := range snap.Knowledge {
		hash := store.ContentHash(k.Title + "\n" + k.Content)
		v, e := s.Store.Embedding(ctx, snap.Shop.ID, k.ID, hash, query.Revision)
		if e != nil {
			return nil, "bge", e
		}
		candidates = append(candidates, candidate{k: k, hash: hash, vector: v})
		if !retrieval.Valid(v) {
			missing = append(missing, len(candidates)-1)
		}
	}
	for start := 0; start < len(missing); start += 16 {
		end := start + 16
		if end > len(missing) {
			end = len(missing)
		}
		texts := []string{}
		for _, index := range missing[start:end] {
			k := candidates[index].k
			texts = append(texts, k.Title+"\n"+k.Content)
		}
		result, e := client.Embed(ctx, texts, false)
		if e != nil || result.Revision != query.Revision {
			return nil, "bge", domain.Unavailable("retrieval_unavailable", "BGE 推理失败或模型版本已改变，请重试；本次没有调用 DeepSeek。")
		}
		for n, index := range missing[start:end] {
			candidates[index].vector = result.Vectors[n]
			if e = s.Store.SaveEmbedding(ctx, snap.Shop.ID, candidates[index].k.ID, candidates[index].hash, query.Revision, result.Vectors[n]); e != nil {
				return nil, "bge", e
			}
		}
	}
	for i := range candidates {
		candidates[i].score = retrieval.Cosine(query.Vectors[0], candidates[i].vector)
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].score == candidates[j].score {
			return candidates[i].k.ID < candidates[j].k.ID
		}
		return candidates[i].score > candidates[j].score
	})
	out := []domain.Knowledge{}
	remaining := 6000
	for _, c := range candidates {
		n := utf8.RuneCountInString(c.k.Title) + utf8.RuneCountInString(c.k.Content)
		if n > remaining || c.score < 0.35 {
			continue
		}
		out = append(out, c.k)
		remaining -= n
		if len(out) == 6 {
			break
		}
	}
	return out, "bge", nil
}

func (s *Service) RegisterIntegrationRoutes(a *gin.RouterGroup) {
	a.GET("/integrations/status", func(c *gin.Context) { tb, r := s.IntegrationStatus(); ok(c, gin.H{"taobao": tb, "retrieval": r}) })
	a.GET("/diagnostics", s.diagnostics)
	a.POST("/retrieval/search", func(c *gin.Context) {
		var in struct {
			ShopID    string `json:"shop_id"`
			SessionID string `json:"session_id"`
			ProductID string `json:"product_id"`
			Question  string `json:"question"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID, in.ProductID) {
			return
		}
		if !domain.TextWithin(in.Question, 1, 2000) {
			fail(c, domain.Invalid("问题应为1至2000字。"))
			return
		}
		snap, e := s.Store.Snapshot(c.Request.Context(), in.ShopID, in.SessionID, in.ProductID)
		if e != nil {
			fail(c, e)
			return
		}
		records, mode, e := s.retrieve(c.Request.Context(), snap, in.Question)
		respond(c, gin.H{"mode": mode, "matches": records, "note": "检索结果仅是候选上下文，仍须人工核对事实。"}, e)
	})
	a.GET("/taobao/rooms", func(c *gin.Context) {
		shop, yes := queryShop(c)
		if !yes {
			return
		}
		r, e := s.Store.ListTaobaoRooms(c.Request.Context(), shop)
		respond(c, r, e)
	})
	a.PUT("/taobao/rooms", func(c *gin.Context) {
		var in struct {
			ShopID    string `json:"shop_id"`
			SessionID string `json:"session_id"`
			LiveID    string `json:"live_id"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID) {
			return
		}
		if !taobao.ValidNumber(in.LiveID) {
			fail(c, domain.Invalid("淘宝直播间 ID 必须为正整数的字符串。"))
			return
		}
		r, e := s.Store.BindTaobaoRoom(c.Request.Context(), in.ShopID, in.SessionID, in.LiveID)
		respond(c, r, e)
	})
	a.GET("/taobao/events", func(c *gin.Context) {
		shop, yes := queryShop(c)
		session := c.Query("session_id")
		if !yes || (session != "" && !ids(c, session)) {
			return
		}
		r, e := s.Store.ListTaobaoEvents(c.Request.Context(), shop, session)
		respond(c, r, e)
	})
	a.POST("/taobao/events/replay", func(c *gin.Context) {
		var in struct {
			ShopID    string         `json:"shop_id"`
			SessionID string         `json:"session_id"`
			MessageID string         `json:"message_id"`
			Content   taobao.Comment `json:"content"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID) {
			return
		}
		room, e := s.Store.TaobaoRoom(c.Request.Context(), in.ShopID, in.SessionID)
		if e != nil {
			fail(c, e)
			return
		}
		if room.LiveID != in.Content.LiveID {
			fail(c, domain.Conflict("room_mismatch", "回放直播间与场次绑定不一致。"))
			return
		}
		event, duplicate, e := s.ingestComment(c.Request.Context(), room, in.MessageID, in.Content, "replay")
		respond(c, gin.H{"event": event, "duplicate": duplicate}, e)
	})
	a.POST("/taobao/events/:id/draft", func(c *gin.Context) {
		var in struct {
			ShopID    string `json:"shop_id"`
			ProductID string `json:"product_id"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.ProductID, c.Param("id")) {
			return
		}
		if s.Generator == nil || !s.Generator.Configured() {
			fail(c, domain.Unavailable("deepseek_not_configured", "请先配置 DeepSeek；事件仍保持待处理。"))
			return
		}
		event, e := s.Store.ClaimEvent(c.Request.Context(), in.ShopID, c.Param("id"))
		if e != nil {
			fail(c, e)
			return
		}
		job, e := s.Generate(c.Request.Context(), in.ShopID, event.SessionID, in.ProductID, event.Comment)
		finish, cancel := context.WithTimeout(context.WithoutCancel(c.Request.Context()), 5*time.Second)
		defer cancel()
		var jobID *string
		code := ""
		if e == nil {
			jobID = &job.ID
		} else {
			code = "generation_failed_or_unknown"
		}
		if persist := s.Store.FinishEvent(finish, in.ShopID, event.ID, jobID, code); persist != nil {
			fail(c, persist)
			return
		}
		respond(c, job, e)
	})
	a.POST("/taobao/poll", func(c *gin.Context) {
		var in struct {
			ShopID string `json:"shop_id"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		r, e := s.pollTaobao(c.Request.Context(), in.ShopID)
		respond(c, r, e)
	})
	a.POST("/taobao/live-detail", func(c *gin.Context) {
		var in struct {
			ShopID    string `json:"shop_id"`
			SessionID string `json:"session_id"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID) {
			return
		}
		client, e := s.taobaoFor(in.ShopID)
		if e != nil {
			fail(c, e)
			return
		}
		room, e := s.Store.TaobaoRoom(c.Request.Context(), in.ShopID, in.SessionID)
		if e != nil {
			fail(c, e)
			return
		}
		data, e := client.LiveDetail(c.Request.Context(), room.LiveID)
		respond(c, gin.H{"live_id": room.LiveID, "data": data}, taobaoError(e))
	})
	a.POST("/taobao/items", func(c *gin.Context) {
		var in struct {
			ShopID string `json:"shop_id"`
			Page   int    `json:"page_no"`
			Size   int    `json:"page_size"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID) {
			return
		}
		if in.Page < 1 || in.Size < 1 || in.Size > 200 || in.Page > 20000/in.Size {
			fail(c, domain.Invalid("分页超出范围。"))
			return
		}
		client, e := s.taobaoFor(in.ShopID)
		if e != nil {
			fail(c, e)
			return
		}
		r, e := client.Items(c.Request.Context(), in.Page, in.Size)
		respond(c, r, taobaoError(e))
	})
	a.POST("/taobao/push-item", s.taobaoAction(false))
	a.POST("/taobao/report", s.taobaoAction(true))
}

func (s *Service) taobaoFor(shop string) (*taobao.Client, error) {
	x := s.integrations
	if x == nil || !x.tb.Configured() {
		return nil, domain.Unavailable("taobao_not_configured", "尚未配置淘宝开放平台应用、授权和本地店铺绑定。")
	}
	if x.shop != shop {
		return nil, domain.NotFound()
	}
	return x.tb, nil
}
func taobaoError(e error) error {
	if e == nil {
		return nil
	}
	return &domain.Error{Status: 502, Code: taobao.ErrorCode(e), Message: "淘宝接口未完成，请检查应用权限、授权有效期和网络。上游正文与凭据不回显。"}
}
func (s *Service) ingestComment(ctx context.Context, room store.Room, messageID string, c taobao.Comment, source string) (store.Event, bool, error) {
	if !domain.TextWithin(c.Text, 1, 2000) || !taobao.ValidNumber(c.LiveID) || !domain.TextWithin(messageID, 0, 200) || !domain.TextWithin(c.UniqueCode, 0, 200) {
		return store.Event{}, false, domain.Invalid("评论字段、长度或直播间标识无效。")
	}
	if room.LiveID != c.LiveID {
		return store.Event{}, false, domain.Conflict("room_mismatch", "评论直播间不匹配。")
	}
	key := c.UniqueCode
	if key != "" {
		key = "unique:" + key
	} else if messageID != "" {
		key = "message:" + messageID
	} else {
		return store.Event{}, false, domain.Invalid("缺少可去重的消息标识。")
	}
	return s.Store.RecordTaobaoEvent(ctx, store.Event{ShopID: room.ShopID, SessionID: room.SessionID, MessageID: messageID, LiveID: c.LiveID, Comment: strings.TrimSpace(c.Text), Source: source, DedupKey: store.ContentHash(c.LiveID + "\x00" + key)})
}

type pollResult struct {
	Received   int `json:"received"`
	Stored     int `json:"stored"`
	Duplicates int `json:"duplicates"`
	Ignored    int `json:"ignored"`
	Confirmed  int `json:"confirmed"`
}

func (s *Service) pollTaobao(ctx context.Context, shop string) (out pollResult, err error) {
	client, e := s.taobaoFor(shop)
	if e != nil {
		return out, e
	}
	x := s.integrations
	if !x.pollMu.TryLock() {
		return out, domain.Conflict("taobao_poll_busy", "同一消息分组正在消费，请稍后重试。")
	}
	defer x.pollMu.Unlock()
	now := time.Now().UTC()
	x.mu.Lock()
	x.lastPoll = &now
	x.mu.Unlock()
	defer func() {
		x.mu.Lock()
		defer x.mu.Unlock()
		if err == nil {
			now := time.Now().UTC()
			x.lastSuccess = &now
			x.lastError = ""
		} else {
			var d *domain.Error
			if errors.As(err, &d) {
				x.lastError = d.Code
			} else {
				x.lastError = "taobao_poll_failed"
			}
		}
	}()
	messages, e := client.Consume(ctx)
	if e != nil {
		return out, taobaoError(e)
	}
	out.Received = len(messages)
	ack := []string{}
	for _, m := range messages {
		if m.Topic != taobao.CommentTopic {
			out.Ignored++
			continue
		}
		c, e := taobao.ParseComment(m.Content)
		if e != nil {
			out.Ignored++
			continue
		}
		room, e := s.Store.TaobaoRoomByLiveID(ctx, shop, c.LiveID)
		if e != nil {
			var d *domain.Error
			if errors.As(e, &d) && d.Status == 404 {
				out.Ignored++
				continue
			}
			return out, e
		}
		_, duplicate, e := s.ingestComment(ctx, room, string(m.ID), c, "taobao")
		if e != nil {
			var d *domain.Error
			if errors.As(e, &d) && d.Status == 400 {
				out.Ignored++
				continue
			}
			return out, e
		}
		if duplicate {
			out.Duplicates++
		} else {
			out.Stored++
		}
		ack = append(ack, string(m.ID))
	}
	if e = client.Confirm(ctx, ack); e != nil {
		return out, taobaoError(e)
	}
	out.Confirmed = len(ack)
	if out.Ignored > 0 {
		return out, domain.Conflict("taobao_messages_unrouted", "存在未匹配主题、直播间或无效字段的消息，未确认这些消息；请核对独立消息分组和场次绑定。")
	}
	return out, nil
}
func (s *Service) RunIntegrations(ctx context.Context) {
	if s.integrations == nil || !s.integrations.pollEnabled {
		return
	}
	delay := 5 * time.Second
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(delay):
		}
		_, e := s.pollTaobao(ctx, s.integrations.shop)
		if e != nil {
			delay *= 2
			if delay > 60*time.Second {
				delay = 60 * time.Second
			}
		} else {
			delay = 5 * time.Second
		}
	}
}
func (s *Service) taobaoAction(report bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in struct {
			ShopID    string         `json:"shop_id"`
			SessionID string         `json:"session_id"`
			ItemID    string         `json:"item_id,omitempty"`
			RequestID string         `json:"request_id"`
			Metrics   *taobao.Report `json:"metrics,omitempty"`
		}
		if !decode(c, &in) || !ids(c, in.ShopID, in.SessionID, in.RequestID) {
			return
		}
		if report {
			if in.Metrics == nil || in.Metrics.Validate() != nil || in.ItemID != "" {
				fail(c, domain.Invalid("上报字段无效，请填写平台要求的状态、模型类型和公司名称。"))
				return
			}
		} else if !taobao.ValidNumber(in.ItemID) || in.Metrics != nil {
			fail(c, domain.Invalid("商品 ID 应为正整数字符串。"))
			return
		}
		client, e := s.taobaoFor(in.ShopID)
		if e != nil {
			fail(c, e)
			return
		}
		room, e := s.Store.TaobaoRoom(c.Request.Context(), in.ShopID, in.SessionID)
		if e != nil {
			fail(c, e)
			return
		}
		kind := "push_item"
		if report {
			kind = "report"
		}
		payload, _ := json.Marshal(in)
		hash := store.ContentHash(room.LiveID + string(payload))
		operation, done := s.register(c.Request.Context(), in.SessionID, "")
		defer done()
		locks := s.sessionLock(in.SessionID)
		locks.dispatch.Lock()
		defer locks.dispatch.Unlock()
		action, fresh, e := s.Store.BeginTaobaoAction(operation, in.ShopID, in.SessionID, in.RequestID, kind, hash)
		if e != nil {
			fail(c, e)
			return
		}
		if !fresh {
			ok(c, action)
			return
		}
		if report {
			e = client.Report(operation, room.LiveID, *in.Metrics)
		} else {
			e = client.PushItem(operation, room.LiveID, in.ItemID)
		}
		status, code := "succeeded", ""
		if e != nil {
			status = "delivery_unknown"
			code = taobao.ErrorCode(e)
			var te *taobao.Error
			if errors.As(e, &te) && te.Definitive {
				status = "failed"
			}
		}
		finish, cancel := context.WithTimeout(context.WithoutCancel(c.Request.Context()), 5*time.Second)
		defer cancel()
		action, e = s.Store.FinishTaobaoAction(finish, in.ShopID, in.RequestID, status, code)
		respond(c, action, e)
	}
}

func (s *Service) diagnostics(c *gin.Context) {
	type check struct {
		Name   string `json:"name"`
		Status string `json:"status"`
		Detail string `json:"detail"`
	}
	checks := []check{}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 8*time.Second)
	defer cancel()
	if e := s.Store.Ping(ctx); e != nil {
		checks = append(checks, check{"postgresql", "failed", "数据库不可用"})
	} else {
		checks = append(checks, check{"postgresql", "ok", "数据库可连接；迁移由启动流程验证"})
	}
	if file, e := os.CreateTemp(s.AudioDir, ".diagnostic-*"); e != nil {
		checks = append(checks, check{"audio_directory", "failed", "音频目录不可写"})
	} else {
		name := file.Name()
		file.Close()
		os.Remove(name)
		checks = append(checks, check{"audio_directory", "ok", "音频目录可写"})
	}
	if s.Generator != nil && s.Generator.Configured() {
		checks = append(checks, check{"deepseek_configuration", "ok", "已配置；诊断不调用付费生成接口"})
	} else {
		checks = append(checks, check{"deepseek_configuration", "unconfigured", "人工草稿可用；生成需配置 DeepSeek"})
	}
	if identity, ok := s.Media.(interface {
		TTSIdentity(context.Context) (string, error)
	}); ok && s.Media.TTSConfigured() {
		if _, e := identity.TTSIdentity(ctx); e != nil {
			checks = append(checks, check{"tts_model", "failed", "本地语音模型未就绪或指纹不完整"})
		} else {
			checks = append(checks, check{"tts_model", "ok", "本地模型健康检查返回已加载的引擎指纹；仍须试听"})
		}
	} else {
		checks = append(checks, check{"tts_model", "unconfigured", "未配置本地语音服务或未支持引擎身份核验"})
	}
	if s.integrations != nil && s.integrations.bge.Configured() {
		if _, e := s.integrations.bge.Health(ctx); e != nil {
			checks = append(checks, check{"bge_model", "failed", "本地 BGE 模型不可用"})
		} else {
			checks = append(checks, check{"bge_model", "ok", "BGE 模型已加载，512维 CPU 检索可用"})
		}
	} else {
		checks = append(checks, check{"bge_model", "unconfigured", "当前使用关键词检索"})
	}
	ok(c, gin.H{"checked_at": time.Now().UTC(), "checks": checks, "note": "真实 WebRTC/OBS、GPU 性能、人物口型与淘宝接收需另行实测；配置与健康检查不能证明已播出。"})
}
