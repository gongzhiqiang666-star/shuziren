package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/jackc/pgx/v5"
)

var ErrNoWork = errors.New("no queued synthesis")

// Every transition acquires context locks BEFORE the job lock. Takeover locks
// the session before cancelling jobs, so the reverse order would deadlock.
func snapshot(ctx context.Context, tx pgx.Tx, shop, session, product string) (domain.Snapshot, error) {
	var s domain.Snapshot
	err := tx.QueryRow(ctx, "SELECT id::text,name,created_at,knowledge_version FROM shops WHERE id=$1 FOR SHARE", shop).Scan(&s.Shop.ID, &s.Shop.Name, &s.Shop.CreatedAt, &s.KnowledgeVersion)
	if err != nil {
		return s, dbError(err)
	}
	s.Session, err = scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2 FOR SHARE", session, shop))
	if err != nil {
		return s, err
	}
	s.Product, err = scanProduct(tx.QueryRow(ctx, "SELECT "+productColumns+" FROM products WHERE id=$1 AND shop_id=$2 FOR SHARE", product, shop))
	if err != nil {
		return s, err
	}
	s.Persona, err = scanPersona(tx.QueryRow(ctx, "SELECT "+personaColumns+" FROM personas WHERE shop_id=$1 FOR SHARE", shop))
	if err != nil {
		return s, err
	}
	s.Knowledge, err = listKnowledge(ctx, tx, shop)
	return s, err
}

func (s *Store) Snapshot(ctx context.Context, shop, session, product string) (domain.Snapshot, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Snapshot{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	snap, err := snapshot(ctx, tx, shop, session, product)
	if err != nil {
		return snap, err
	}
	if err = domain.ValidateSnapshot(snap, time.Now()); err != nil {
		return snap, err
	}
	return snap, dbError(tx.Commit(ctx))
}

func (s *Store) CreateJob(ctx context.Context, original domain.Snapshot, j domain.Job) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return j, dbError(err)
	}
	defer tx.Rollback(ctx)
	current, err := snapshot(ctx, tx, original.Shop.ID, original.Session.ID, original.Product.ID)
	if err != nil {
		return j, err
	}
	j.ID = domain.NewID()
	j.ShopID = original.Shop.ID
	j.SessionID = original.Session.ID
	j.ProductID = original.Product.ID
	j.ProductVersion = original.Product.Version
	j.PersonaVersion = original.Persona.Version
	j.KnowledgeVersion = original.KnowledgeVersion
	j.Epoch = original.Session.Epoch
	if err = domain.ValidateJob(j, current, time.Now()); err != nil {
		return j, err
	}
	if j.Status != "draft" && j.Status != "blocked" {
		return j, domain.Invalid("新任务只能是草稿或等待人工处理。")
	}
	b, err := json.Marshal(original)
	if err != nil {
		return j, err
	}
	j, err = scanJob(tx.QueryRow(ctx, `INSERT INTO speech_jobs(id,shop_id,session_id,product_id,product_version,persona_version,knowledge_version,epoch,source,question,text,status,reason,input_tokens,output_tokens,context_snapshot) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) RETURNING `+jobColumns, j.ID, j.ShopID, j.SessionID, j.ProductID, j.ProductVersion, j.PersonaVersion, j.KnowledgeVersion, j.Epoch, j.Source, j.Question, j.Text, j.Status, j.Reason, j.InputTokens, j.OutputTokens, b))
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, j.ShopID, j.ID, "job_created", map[string]any{"source": j.Source, "status": j.Status, "epoch": j.Epoch, "product_version": j.ProductVersion, "persona_version": j.PersonaVersion, "knowledge_version": j.KnowledgeVersion}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) GetJob(ctx context.Context, shop, id string) (domain.Job, error) {
	return scanJob(s.pool.QueryRow(ctx, "SELECT "+jobColumns+" FROM speech_jobs WHERE id=$1 AND shop_id=$2", id, shop))
}

func (s *Store) ListJobs(ctx context.Context, shop, session string) ([]domain.Job, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	if session != "" {
		if _, err := s.GetSession(ctx, shop, session); err != nil {
			return nil, err
		}
	}
	r, err := s.pool.Query(ctx, "SELECT "+jobColumns+" FROM speech_jobs WHERE shop_id=$1 AND ($2='' OR session_id::text=$2) ORDER BY created_at DESC LIMIT 100", shop, session)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Job{}
	for r.Next() {
		j, err := scanJob(r)
		if err != nil {
			return nil, err
		}
		out = append(out, j)
	}
	return out, dbError(r.Err())
}

func lockJob(ctx context.Context, tx pgx.Tx, shop, id string) (domain.Job, domain.Snapshot, error) {
	j, err := scanJob(tx.QueryRow(ctx, "SELECT "+jobColumns+" FROM speech_jobs WHERE id=$1 AND shop_id=$2", id, shop))
	if err != nil {
		return j, domain.Snapshot{}, err
	}
	snap, err := snapshot(ctx, tx, shop, j.SessionID, j.ProductID)
	if err != nil {
		return j, snap, err
	}
	j, err = scanJob(tx.QueryRow(ctx, "SELECT "+jobColumns+" FROM speech_jobs WHERE id=$1 AND shop_id=$2 FOR UPDATE", id, shop))
	return j, snap, err
}

func updateJob(ctx context.Context, tx pgx.Tx, j domain.Job, status, reason, code string) (domain.Job, error) {
	return scanJob(tx.QueryRow(ctx, "UPDATE speech_jobs SET status=$3,reason=$4,error_code=$5,updated_at=now() WHERE id=$1 AND shop_id=$2 RETURNING "+jobColumns, j.ID, j.ShopID, status, reason, code))
}

func (s *Store) Approve(ctx context.Context, shop, id string) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, err
	}
	if err = domain.ValidateJob(j, snap, time.Now()); err != nil {
		return j, err
	}
	if j.Status == "approved" {
		return j, dbError(tx.Commit(ctx))
	}
	if j.Status != "draft" || !domain.TextWithin(j.Text, 1, 2000) {
		return j, domain.Conflict("not_draft", "仅可审批有效草稿；等待人工处理的任务请重新编写。")
	}
	j, err = scanJob(tx.QueryRow(ctx, "UPDATE speech_jobs SET status='approved',approved_at=now(),reason='',error_code='',updated_at=now() WHERE id=$1 RETURNING "+jobColumns, id))
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "job_approved", map[string]any{"epoch": j.Epoch}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) QueueSynthesis(ctx context.Context, shop, id string) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, err
	}
	if err = domain.ValidateJob(j, snap, time.Now()); err != nil {
		return j, err
	}
	if j.Status == "queued" || j.Status == "synthesizing" || j.Status == "ready" {
		return j, dbError(tx.Commit(ctx))
	}
	if j.Status != "approved" && !(j.Status == "failed" && j.ApprovedAt != nil) {
		return j, domain.Conflict("not_approved", "任务需先人工审批；发送结果不明或已发送的任务不能重试。")
	}
	j, err = updateJob(ctx, tx, j, "queued", "等待本地语音服务串行合成。", "")
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "synthesis_queued", map[string]any{}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) ClaimNext(ctx context.Context) (domain.Job, error) {
	var id, shop string
	err := s.pool.QueryRow(ctx, "SELECT id::text,shop_id::text FROM speech_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").Scan(&id, &shop)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Job{}, ErrNoWork
	}
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, err
	}
	if j.Status != "queued" {
		return j, ErrNoWork
	}
	if e := domain.ValidateJob(j, snap, time.Now()); e != nil {
		j, err = updateJob(ctx, tx, j, "cancelled", "商品、人格、知识或场次已经改变，请重新生成和审批。", "stale_context")
		if err != nil {
			return j, err
		}
		if err = tx.Commit(ctx); err != nil {
			return j, dbError(err)
		}
		return j, ErrNoWork
	}
	j, err = updateJob(ctx, tx, j, "synthesizing", "本地语音合成中。", "")
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "synthesis_started", map[string]any{}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

// Revalidate is used after registering cancellation and before a long provider
// call, closing the race in which takeover occurs just before registration.
func (s *Store) Revalidate(ctx context.Context, shop, id, requiredStatus string) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, err
	}
	if err = domain.ValidateJob(j, snap, time.Now()); err != nil {
		return j, err
	}
	if requiredStatus != "" && j.Status != requiredStatus {
		return j, domain.Conflict("job_state_changed", "任务状态已经改变，请刷新。")
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) FinishSynthesis(ctx context.Context, shop, id string) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, err
	}
	if j.Status != "synthesizing" {
		return j, domain.Conflict("job_state_changed", "语音任务已取消或改变，迟到结果已丢弃。")
	}
	if e := domain.ValidateJob(j, snap, time.Now()); e != nil {
		j, err = updateJob(ctx, tx, j, "cancelled", "合成完成前资料或场次改变，旧音频已作废。", "stale_context")
		if err != nil {
			return j, err
		}
		if err = tx.Commit(ctx); err != nil {
			return j, dbError(err)
		}
		return j, e
	}
	j, err = scanJob(tx.QueryRow(ctx, "UPDATE speech_jobs SET status='ready',audio_ready=true,reason='音频已就绪，尚未发送。',error_code='',updated_at=now() WHERE id=$1 RETURNING "+jobColumns, id))
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "synthesis_ready", map[string]any{}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) FailSynthesis(ctx context.Context, shop, id, code, reason string) error {
	_, err := s.pool.Exec(ctx, "UPDATE speech_jobs SET status='failed',error_code=$3,reason=$4,updated_at=now() WHERE id=$1 AND shop_id=$2 AND status='synthesizing'", id, shop, code, reason)
	return dbError(err)
}

func (s *Store) StartSend(ctx context.Context, shop, id string) (domain.Job, domain.Session, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, domain.Session{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, snap.Session, err
	}
	if err = domain.ValidateJob(j, snap, time.Now()); err != nil {
		return j, snap.Session, err
	}
	if j.Status != "ready" || !j.AudioReady {
		return j, snap.Session, domain.Conflict("not_ready", "只有已合成且未发送的音频可以发送；结果不明时请接管核对。")
	}
	if snap.Session.MediaSessionID == nil || *snap.Session.MediaSessionID == "" {
		return j, snap.Session, domain.Conflict("media_not_connected", "请先建立该场次的 LiveTalking 预览连接。")
	}
	j, err = updateJob(ctx, tx, j, "sending", "正在提交上游；尚不能确认是否被接收。", "")
	if err != nil {
		return j, snap.Session, err
	}
	if err = audit(ctx, tx, shop, id, "media_send_started", map[string]any{"epoch": j.Epoch}); err != nil {
		return j, snap.Session, err
	}
	return j, snap.Session, dbError(tx.Commit(ctx))
}

// A stop may already have changed sending to delivery_unknown. Never overwrite
// that with a late successful HTTP acknowledgement.
func (s *Store) FinishSend(ctx context.Context, shop, id string, accepted bool) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, id)
	if err != nil {
		return j, err
	}
	if j.Status != "sending" {
		return j, dbError(tx.Commit(ctx))
	}
	status, reason, code := "delivery_unknown", "上游发送结果不明确，请接管场次核对；禁止自动重播。", "media_delivery_unknown"
	if accepted && domain.ValidateJob(j, snap, time.Now()) == nil {
		status = "sent"
		reason = "上游已接收音频；不代表实际播出完成。"
		code = ""
	}
	j, err = updateJob(ctx, tx, j, status, reason, code)
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "media_send_result", map[string]any{"status": status}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) CancelJob(ctx context.Context, shop, id string) (domain.Job, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Job{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	// Cancellation deliberately does not require an active/current context.
	j, err := scanJob(tx.QueryRow(ctx, "SELECT "+jobColumns+" FROM speech_jobs WHERE id=$1 AND shop_id=$2 FOR UPDATE", id, shop))
	if err != nil {
		return j, err
	}
	if j.Status == "sending" || j.Status == "sent" || j.Status == "delivery_unknown" {
		return j, domain.Conflict("requires_takeover", "音频已经开始派发或结果不明，请使用场次接管停止上游。")
	}
	if j.Status == "cancelled" {
		return j, dbError(tx.Commit(ctx))
	}
	j, err = updateJob(ctx, tx, j, "cancelled", "操作者取消了任务。", "operator_cancelled")
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "job_cancelled", map[string]any{}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}

func (s *Store) RecordMediaStop(ctx context.Context, shop, session, status string) error {
	return audit(ctx, s.pool, shop, session, "media_stop", map[string]any{"status": status})
}
