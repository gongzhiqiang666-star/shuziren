package api

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/deepseek"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
)

type Media interface {
	TTSConfigured() bool
	LiveConfigured() bool
	Synthesize(context.Context, string) ([]byte, error)
	Negotiate(context.Context, media.Offer) (media.Answer, error)
	SendAudio(context.Context, string, []byte) error
	Interrupt(context.Context, string) error
}
type Generator interface {
	Configured() bool
	Model() string
	Generate(context.Context, domain.Snapshot, string) (deepseek.Result, error)
}
type operation struct {
	session, job string
	cancel       context.CancelFunc
}
type sessionLocks struct {
	control  sync.Mutex
	dispatch sync.Mutex
}
type Service struct {
	Store     *store.Store
	Media     Media
	Generator Generator
	AudioDir  string
	mu        sync.Mutex
	sessions  map[string]*sessionLocks
	shops     map[string]*sync.RWMutex
	ops       map[string]operation
	wake      chan struct{}
}

func New(st *store.Store, m Media, g Generator, audioDir string) (*Service, error) {
	if audioDir == "" {
		audioDir = "./data/audio"
	}
	abs, err := filepath.Abs(audioDir)
	if err != nil {
		return nil, errors.New("invalid AUDIO_DIR")
	}
	if err = os.MkdirAll(abs, 0750); err != nil {
		return nil, errors.New("unable to create AUDIO_DIR")
	}
	return &Service{Store: st, Media: m, Generator: g, AudioDir: abs, sessions: map[string]*sessionLocks{}, shops: map[string]*sync.RWMutex{}, ops: map[string]operation{}, wake: make(chan struct{}, 1)}, nil
}
func (s *Service) sessionLock(id string) *sessionLocks {
	s.mu.Lock()
	defer s.mu.Unlock()
	p := s.sessions[id]
	if p == nil {
		p = &sessionLocks{}
		s.sessions[id] = p
	}
	return p
}
func (s *Service) shopLock(id string) *sync.RWMutex {
	s.mu.Lock()
	defer s.mu.Unlock()
	p := s.shops[id]
	if p == nil {
		p = &sync.RWMutex{}
		s.shops[id] = p
	}
	return p
}
func (s *Service) register(ctx context.Context, session, job string) (context.Context, func()) {
	ctx, cancel := context.WithCancel(ctx)
	id := domain.NewID()
	s.mu.Lock()
	s.ops[id] = operation{session, job, cancel}
	s.mu.Unlock()
	return ctx, func() { cancel(); s.mu.Lock(); delete(s.ops, id); s.mu.Unlock() }
}
func (s *Service) cancelOperations(session, job string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, o := range s.ops {
		if (session != "" && o.session == session) || (job != "" && o.job == job) {
			o.cancel()
		}
	}
}
func (s *Service) Wake() {
	select {
	case s.wake <- struct{}{}:
	default:
	}
}

func (s *Service) Manual(ctx context.Context, shop, session, product, text string) (domain.Job, error) {
	snap, err := s.Store.Snapshot(ctx, shop, session, product)
	if err != nil {
		return domain.Job{}, err
	}
	return s.Store.CreateJob(ctx, snap, domain.Job{Source: "manual", Text: text, Status: "draft", Reason: "人工草稿，仍需检查事实来源并审批。"})
}
func (s *Service) Generate(ctx context.Context, shop, session, product, question string) (domain.Job, error) {
	if s.Generator == nil || !s.Generator.Configured() {
		return domain.Job{}, domain.Unavailable("deepseek_not_configured", "尚未配置 DeepSeek，仍可创建人工草稿。")
	}
	ctx, done := s.register(ctx, session, "")
	defer done()
	snap, err := s.Store.Snapshot(ctx, shop, session, product)
	if err != nil {
		return domain.Job{}, err
	}
	result, err := s.Generator.Generate(ctx, snap, question)
	if err != nil {
		return domain.Job{}, err
	}
	status := "draft"
	if result.NeedsHuman {
		status = "blocked"
	}
	return s.Store.CreateJob(ctx, snap, domain.Job{Source: "deepseek", Question: question, Text: result.Answer, Status: status, Reason: result.Reason, InputTokens: result.InputTokens, OutputTokens: result.OutputTokens})
}

type TakeoverResult struct {
	Session         domain.Session `json:"session"`
	MediaStopStatus string         `json:"media_stop_status"`
}

func (s *Service) Takeover(ctx context.Context, shop, id, action string) (TakeoverResult, error) {
	locks := s.sessionLock(id)
	locks.control.Lock()
	defer locks.control.Unlock()
	// Commit pause + epoch before waiting for an in-flight HTTP send. No late
	// synthesis or generation can become usable while stop is waiting.
	p, err := s.Store.ChangeSession(ctx, shop, id, action)
	if err != nil {
		return TakeoverResult{}, err
	}
	s.cancelOperations(id, "")
	locks.dispatch.Lock()
	defer locks.dispatch.Unlock()
	result := TakeoverResult{Session: p, MediaStopStatus: "not_connected"}
	if p.MediaSessionID != nil && s.Media != nil && s.Media.LiveConfigured() {
		stopCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 35*time.Second)
		defer cancel()
		if err = s.Media.Interrupt(stopCtx, *p.MediaSessionID); errors.Is(err, media.ErrSessionNotFound) {
			result.MediaStopStatus = "not_connected"
		} else if err != nil {
			result.MediaStopStatus = "failed"
		} else {
			result.MediaStopStatus = "sent"
		}
	}
	auditCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	_ = s.Store.RecordMediaStop(auditCtx, shop, id, result.MediaStopStatus)
	return result, nil
}
func (s *Service) Resume(ctx context.Context, shop, id string) (domain.Session, error) {
	l := s.sessionLock(id)
	l.control.Lock()
	defer l.control.Unlock()
	l.dispatch.Lock()
	defer l.dispatch.Unlock()
	return s.Store.ChangeSession(ctx, shop, id, "resume")
}
func (s *Service) Negotiate(ctx context.Context, shop, id string, offer media.Offer) (media.Answer, error) {
	if s.Media == nil || !s.Media.LiveConfigured() {
		return media.Answer{}, domain.Unavailable("media_not_configured", "尚未配置 LiveTalking 服务。")
	}
	l := s.sessionLock(id)
	l.dispatch.Lock()
	defer l.dispatch.Unlock()
	p, err := s.Store.GetSession(ctx, shop, id)
	if err != nil {
		return media.Answer{}, err
	}
	if p.Status == "ended" {
		return media.Answer{}, domain.Conflict("session_ended", "已结束场次不能建立媒体连接。")
	}
	// Replacing an existing preview cannot silently leave its audio queue live.
	if p.MediaSessionID != nil {
		if err = s.Media.Interrupt(ctx, *p.MediaSessionID); err != nil && !errors.Is(err, media.ErrSessionNotFound) {
			return media.Answer{}, domain.Unavailable("media_stop_failed", "旧媒体会话停止失败，请核对上游后再连接。")
		}
	}
	a, err := s.Media.Negotiate(ctx, offer)
	if err != nil {
		return a, mediaError(err)
	}
	if _, err = s.Store.BindMedia(ctx, shop, id, p.Epoch, a.SessionID); err != nil {
		cleanup, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		_ = s.Media.Interrupt(cleanup, a.SessionID)
		return media.Answer{}, err
	}
	return a, nil
}

func (s *Service) Send(ctx context.Context, shop, id string) (domain.Job, error) {
	if s.Media == nil || !s.Media.LiveConfigured() {
		return domain.Job{}, domain.Unavailable("media_not_configured", "尚未配置 LiveTalking 服务。")
	}
	j, err := s.Store.GetJob(ctx, shop, id)
	if err != nil {
		return j, err
	}
	l := s.sessionLock(j.SessionID)
	l.dispatch.Lock()
	defer l.dispatch.Unlock()
	// UI metadata writes use the same shop gate, so a product/persona edit
	// cannot slip between the final validation and the outbound media request.
	gate := s.shopLock(shop)
	gate.RLock()
	defer gate.RUnlock()
	if _, err = s.Store.Revalidate(ctx, shop, id, "ready"); err != nil {
		return j, err
	}
	wav, err := s.readAudio(id)
	if err != nil {
		return j, err
	}
	j, session, err := s.Store.StartSend(ctx, shop, id)
	if err != nil {
		return j, err
	}
	callErr := s.Media.SendAudio(ctx, *session.MediaSessionID, wav)
	// Persist outcome even when the browser/request was disconnected. Any error
	// after entering SendAudio is conservatively ambiguous and never retried.
	finishCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
	defer cancel()
	result, err := s.Store.FinishSend(finishCtx, shop, id, callErr == nil)
	if err != nil {
		return j, err
	}
	return result, nil
}

func (s *Service) RunWorker(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			s.cancelOperationsAll()
			return
		default:
		}
		if s.Media != nil && s.Media.TTSConfigured() {
			j, err := s.Store.ClaimNext(ctx)
			if err == nil {
				s.synthesize(ctx, j)
				continue
			}
		}
		select {
		case <-ctx.Done():
			s.cancelOperationsAll()
			return
		case <-ticker.C:
		case <-s.wake:
		}
	}
}
func (s *Service) cancelOperationsAll() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, o := range s.ops {
		o.cancel()
	}
}
func (s *Service) synthesize(ctx context.Context, j domain.Job) {
	work, done := s.register(ctx, j.SessionID, j.ID)
	defer done()
	if _, err := s.Store.Revalidate(work, j.ShopID, j.ID, "synthesizing"); err != nil {
		s.failSynthesis(ctx, j, "stale_context", "任务上下文已改变，合成未执行。")
		return
	}
	wav, err := s.Media.Synthesize(work, j.Text)
	if err != nil {
		s.failSynthesis(ctx, j, "tts_failed", "本地语音合成失败或被中断，请核对服务后人工重试。")
		return
	}
	if work.Err() != nil {
		s.failSynthesis(ctx, j, "synthesis_cancelled", "合成被取消，迟到音频已丢弃。")
		return
	}
	if err = s.writeAudio(j.ID, wav); err != nil {
		s.failSynthesis(ctx, j, "audio_storage_failed", "无法保存语音文件，请检查磁盘权限和空间。")
		return
	}
	s.completeSynthesis(ctx, j)
}

func (s *Service) completeSynthesis(ctx context.Context, j domain.Job) {
	finishCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	result, err := s.Store.FinishSynthesis(finishCtx, j.ShopID, j.ID)
	if err != nil {
		// A COMMIT acknowledgement can be lost after PostgreSQL has committed
		// ready. Never delete the only WAV on an ambiguous database error. The
		// conditional failure update leaves an already-ready row untouched.
		var stateErr *domain.Error
		if result.Status == "cancelled" && !result.AudioReady && errors.As(err, &stateErr) && stateErr.Status == 409 {
			_ = os.Remove(s.audioPath(j.ID))
		} else {
			s.failSynthesis(ctx, j, "synthesis_finalize_unknown", "合成写回未确认；已保留音频，请核对任务状态后人工处理。")
		}
	}
}
func (s *Service) failSynthesis(ctx context.Context, j domain.Job, code, reason string) {
	c, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	_ = s.Store.FailSynthesis(c, j.ShopID, j.ID, code, reason)
}
func (s *Service) audioPath(id string) string { return filepath.Join(s.AudioDir, id+".wav") }
func (s *Service) writeAudio(id string, wav []byte) error {
	if !domain.ValidID(id) || len(wav) == 0 || len(wav) > media.MaxAudioBytes {
		return errors.New("invalid audio")
	}
	f, err := os.CreateTemp(s.AudioDir, ".speech-*.tmp")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if _, err = f.Write(wav); err != nil {
		_ = f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		_ = f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return os.Rename(name, s.audioPath(id))
}
func (s *Service) readAudio(id string) ([]byte, error) {
	if !domain.ValidID(id) {
		return nil, domain.Invalid("任务标识无效。")
	}
	f, err := os.Open(s.audioPath(id))
	if err != nil {
		return nil, domain.Conflict("audio_missing", "语音文件缺失，请核对备份或重新生成任务。")
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > media.MaxAudioBytes {
		return nil, domain.Conflict("audio_invalid", "语音文件无效，不能发送。")
	}
	b, err := io.ReadAll(io.LimitReader(f, media.MaxAudioBytes+1))
	if err != nil || len(b) == 0 || len(b) > media.MaxAudioBytes {
		return nil, domain.Conflict("audio_invalid", "语音文件无法读取。")
	}
	return b, nil
}
func mediaError(err error) error {
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return err
	}
	if errors.Is(err, media.ErrInvalidInput) {
		return domain.Invalid("媒体输入无效，请检查浏览器会话或音频格式。")
	}
	if errors.Is(err, media.ErrNotConfigured) {
		return domain.Unavailable("media_not_configured", "本地媒体服务尚未配置。")
	}
	return &domain.Error{Status: 502, Code: "media_unavailable", Message: "本地媒体服务请求失败，请核对服务状态。上游正文未透传。"}
}
