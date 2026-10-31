package store

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/retrieval"
	"github.com/jackc/pgx/v5"
	"time"
)

func ContentHash(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}
func (s *Store) Embedding(ctx context.Context, shop, id, hash, revision string) ([]float32, error) {
	var v []float32
	e := s.pool.QueryRow(ctx, `SELECT embedding FROM knowledge_embeddings WHERE shop_id=$1 AND knowledge_id=$2 AND content_hash=$3 AND model_revision=$4`, shop, id, hash, revision).Scan(&v)
	if errors.Is(e, pgx.ErrNoRows) {
		return nil, nil
	}
	return v, dbError(e)
}
func (s *Store) SaveEmbedding(ctx context.Context, shop, id, hash, revision string, v []float32) error {
	if !retrieval.Valid(v) || !retrieval.ValidRevision(revision) {
		return domain.Invalid("向量维度或归一化值无效。")
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return dbError(e)
	}
	defer tx.Rollback(ctx)
	var owner string
	if e = tx.QueryRow(ctx, "SELECT id::text FROM shops WHERE id=$1 FOR SHARE", shop).Scan(&owner); e != nil {
		return dbError(e)
	}
	var title, content string
	var deleted, expires *time.Time
	if e = tx.QueryRow(ctx, "SELECT title,content,deleted_at,expires_at FROM knowledge WHERE shop_id=$1 AND id=$2 FOR SHARE", shop, id).Scan(&title, &content, &deleted, &expires); e != nil {
		return dbError(e)
	}
	if deleted != nil || (expires != nil && !time.Now().Before(*expires)) || ContentHash(title+"\n"+content) != hash {
		return domain.Conflict("stale_knowledge", "嵌入期间知识已修改、删除或过期，请刷新后重试。")
	}
	_, e = tx.Exec(ctx, `INSERT INTO knowledge_embeddings(shop_id,knowledge_id,content_hash,model_revision,embedding) VALUES($1,$2,$3,$4,$5) ON CONFLICT(shop_id,knowledge_id) DO UPDATE SET content_hash=excluded.content_hash,model_revision=excluded.model_revision,embedding=excluded.embedding,updated_at=now()`, shop, id, hash, revision, v)
	if e != nil {
		return dbError(e)
	}
	return dbError(tx.Commit(ctx))
}

type Room struct {
	ShopID    string    `json:"shop_id"`
	SessionID string    `json:"session_id"`
	LiveID    string    `json:"live_id"`
	UpdatedAt time.Time `json:"updated_at"`
}

func scanRoom(r scanner) (Room, error) {
	var x Room
	e := r.Scan(&x.ShopID, &x.SessionID, &x.LiveID, &x.UpdatedAt)
	return x, dbError(e)
}
func (s *Store) BindTaobaoRoom(ctx context.Context, shop, session, liveID string) (Room, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Room{}, dbError(e)
	}
	defer tx.Rollback(ctx)
	p, e := scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2 FOR UPDATE", session, shop))
	if e != nil {
		return Room{}, e
	}
	if p.Status == "ended" {
		return Room{}, domain.Conflict("session_ended", "已结束场次不能重新绑定直播间。")
	}
	var old string
	e = tx.QueryRow(ctx, "SELECT live_id FROM taobao_rooms WHERE session_id=$1", session).Scan(&old)
	if e != nil && !errors.Is(e, pgx.ErrNoRows) {
		return Room{}, dbError(e)
	}
	// Changing a room with already received events would reassign old questions.
	if old != "" && old != liveID {
		return Room{}, domain.Conflict("room_already_bound", "此场次已绑定其他直播间，请新建场次。")
	}
	p2, e := scanRoom(tx.QueryRow(ctx, `INSERT INTO taobao_rooms(shop_id,session_id,live_id) VALUES($1,$2,$3) ON CONFLICT(session_id) DO UPDATE SET updated_at=now() RETURNING shop_id::text,session_id::text,live_id,updated_at`, shop, session, liveID))
	if e != nil {
		return p2, e
	}
	return p2, dbError(tx.Commit(ctx))
}
func (s *Store) ListTaobaoRooms(ctx context.Context, shop string) ([]Room, error) {
	if e := requireShop(ctx, s.pool, shop); e != nil {
		return nil, e
	}
	r, e := s.pool.Query(ctx, "SELECT shop_id::text,session_id::text,live_id,updated_at FROM taobao_rooms WHERE shop_id=$1 ORDER BY updated_at DESC", shop)
	if e != nil {
		return nil, dbError(e)
	}
	defer r.Close()
	out := []Room{}
	for r.Next() {
		x, e := scanRoom(r)
		if e != nil {
			return nil, e
		}
		out = append(out, x)
	}
	return out, dbError(r.Err())
}
func (s *Store) TaobaoRoom(ctx context.Context, shop, session string) (Room, error) {
	return scanRoom(s.pool.QueryRow(ctx, "SELECT shop_id::text,session_id::text,live_id,updated_at FROM taobao_rooms WHERE shop_id=$1 AND session_id=$2", shop, session))
}
func (s *Store) TaobaoRoomByLiveID(ctx context.Context, shop, liveID string) (Room, error) {
	return scanRoom(s.pool.QueryRow(ctx, "SELECT shop_id::text,session_id::text,live_id,updated_at FROM taobao_rooms WHERE shop_id=$1 AND live_id=$2", shop, liveID))
}

type Event struct {
	ID         string    `json:"id"`
	ShopID     string    `json:"shop_id"`
	SessionID  string    `json:"session_id"`
	MessageID  string    `json:"message_id"`
	LiveID     string    `json:"live_id"`
	Comment    string    `json:"comment"`
	Source     string    `json:"source"`
	DedupKey   string    `json:"dedup_key"`
	Epoch      int64     `json:"epoch"`
	Status     string    `json:"status"`
	JobID      *string   `json:"job_id"`
	ErrorCode  string    `json:"error_code"`
	ReceivedAt time.Time `json:"received_at"`
}

const eventColumns = `id::text,shop_id::text,session_id::text,message_id,live_id,comment,source,dedup_key,epoch,status,job_id::text,error_code,received_at`

func scanEvent(r scanner) (Event, error) {
	var x Event
	e := r.Scan(&x.ID, &x.ShopID, &x.SessionID, &x.MessageID, &x.LiveID, &x.Comment, &x.Source, &x.DedupKey, &x.Epoch, &x.Status, &x.JobID, &x.ErrorCode, &x.ReceivedAt)
	return x, dbError(e)
}
func (s *Store) RecordTaobaoEvent(ctx context.Context, x Event) (Event, bool, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return x, false, dbError(e)
	}
	defer tx.Rollback(ctx)
	p, e := scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2 FOR SHARE", x.SessionID, x.ShopID))
	if e != nil {
		return x, false, e
	}
	x.Epoch = p.Epoch
	x.ID = domain.NewID()
	if p.Status != "active" {
		x.Status = "ignored"
		x.ErrorCode = "session_inactive"
	} else {
		x.Status = "pending"
	}
	row, e := scanEvent(tx.QueryRow(ctx, `INSERT INTO taobao_events(id,shop_id,session_id,message_id,live_id,comment,source,dedup_key,epoch,status,error_code) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT(shop_id,source,dedup_key) DO NOTHING RETURNING `+eventColumns, x.ID, x.ShopID, x.SessionID, x.MessageID, x.LiveID, x.Comment, x.Source, x.DedupKey, x.Epoch, x.Status, x.ErrorCode))
	duplicate := false
	if e != nil {
		var de *domain.Error
		if !errors.As(e, &de) || de.Code != "not_found" {
			return x, false, e
		}
		row, e = scanEvent(tx.QueryRow(ctx, "SELECT "+eventColumns+" FROM taobao_events WHERE shop_id=$1 AND source=$2 AND dedup_key=$3", x.ShopID, x.Source, x.DedupKey))
		duplicate = true
	}
	if e != nil {
		return x, false, e
	}
	return row, duplicate, dbError(tx.Commit(ctx))
}
func (s *Store) ListTaobaoEvents(ctx context.Context, shop, session string) ([]Event, error) {
	if e := requireShop(ctx, s.pool, shop); e != nil {
		return nil, e
	}
	r, e := s.pool.Query(ctx, "SELECT "+eventColumns+" FROM taobao_events WHERE shop_id=$1 AND ($2='' OR session_id::text=$2) ORDER BY received_at DESC,id LIMIT 100", shop, session)
	if e != nil {
		return nil, dbError(e)
	}
	defer r.Close()
	out := []Event{}
	for r.Next() {
		x, e := scanEvent(r)
		if e != nil {
			return nil, e
		}
		out = append(out, x)
	}
	return out, dbError(r.Err())
}
func (s *Store) ClaimEvent(ctx context.Context, shop, id string) (Event, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Event{}, dbError(e)
	}
	defer tx.Rollback(ctx)
	x, e := scanEvent(tx.QueryRow(ctx, "SELECT "+eventColumns+" FROM taobao_events WHERE id=$1 AND shop_id=$2", id, shop))
	if e != nil {
		return x, e
	}
	p, e := scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2 FOR SHARE", x.SessionID, shop))
	if e != nil {
		return x, e
	}
	if p.Status != "active" || p.Epoch != x.Epoch {
		return x, domain.Conflict("stale_event", "评论对应的场次已改变，请人工确认后新建问题。")
	}
	x, e = scanEvent(tx.QueryRow(ctx, "UPDATE taobao_events SET status='generating' WHERE id=$1 AND shop_id=$2 AND status='pending' RETURNING "+eventColumns, id, shop))
	if e != nil {
		return x, domain.Conflict("event_already_claimed", "此事件已处理或生成结果待核对，不自动重复调用。")
	}
	return x, dbError(tx.Commit(ctx))
}
func (s *Store) FinishEvent(ctx context.Context, shop, id string, jobID *string, code string) error {
	status := "drafted"
	if jobID == nil {
		status = "failed"
	}
	_, e := s.pool.Exec(ctx, "UPDATE taobao_events SET status=$3,job_id=$4,error_code=$5 WHERE id=$1 AND shop_id=$2 AND status='generating'", id, shop, status, jobID, code)
	return dbError(e)
}

type Action struct {
	RequestID string `json:"request_id"`
	Status    string `json:"status"`
	ErrorCode string `json:"error_code"`
}

func (s *Store) BeginTaobaoAction(ctx context.Context, shop, session, id, kind, hash string) (Action, bool, error) {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return Action{}, false, dbError(e)
	}
	defer tx.Rollback(ctx)
	p, e := scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE shop_id=$1 AND id=$2 FOR SHARE", shop, session))
	if e != nil {
		return Action{}, false, e
	}
	var a Action
	var priorShop, priorSession, priorKind, priorHash string
	e = tx.QueryRow(ctx, "SELECT request_id::text,status,error_code,shop_id::text,session_id::text,kind,payload_hash FROM taobao_actions WHERE request_id=$1", id).Scan(&a.RequestID, &a.Status, &a.ErrorCode, &priorShop, &priorSession, &priorKind, &priorHash)
	if e == nil {
		if priorShop != shop || priorSession != session || priorKind != kind || priorHash != hash {
			return a, false, domain.Conflict("idempotency_conflict", "操作标识已用于其他请求。")
		}
		return a, false, dbError(tx.Commit(ctx))
	}
	if !errors.Is(e, pgx.ErrNoRows) {
		return a, false, dbError(e)
	}
	if p.Status != "active" && kind == "push_item" {
		return Action{}, false, domain.Conflict("session_inactive", "只有进行中的场次可以弹卡。")
	}
	tag, e := tx.Exec(ctx, `INSERT INTO taobao_actions(request_id,shop_id,session_id,kind,payload_hash,epoch) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(request_id) DO NOTHING`, id, shop, session, kind, hash, p.Epoch)
	if e != nil {
		return a, false, dbError(e)
	}
	e = tx.QueryRow(ctx, `SELECT request_id::text,status,error_code FROM taobao_actions WHERE request_id=$1 AND shop_id=$2 AND session_id=$3 AND kind=$4 AND payload_hash=$5`, id, shop, session, kind, hash).Scan(&a.RequestID, &a.Status, &a.ErrorCode)
	if e != nil {
		if !errors.Is(e, pgx.ErrNoRows) {
			return a, false, dbError(e)
		}
		return a, false, domain.Conflict("idempotency_conflict", "操作标识已用于其他请求。")
	}
	return a, tag.RowsAffected() == 1, dbError(tx.Commit(ctx))
}
func (s *Store) FinishTaobaoAction(ctx context.Context, shop, id, status, code string) (Action, error) {
	var a Action
	if status != "succeeded" && status != "failed" && status != "delivery_unknown" {
		return a, domain.Invalid("平台操作完成状态无效。")
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return a, dbError(e)
	}
	defer tx.Rollback(ctx)
	var session string
	var epoch, currentEpoch int64
	if e = tx.QueryRow(ctx, "SELECT session_id::text,epoch FROM taobao_actions WHERE request_id=$1 AND shop_id=$2", id, shop).Scan(&session, &epoch); e != nil {
		return a, dbError(e)
	}
	if e = tx.QueryRow(ctx, "SELECT epoch FROM live_sessions WHERE id=$1 AND shop_id=$2 FOR SHARE", session, shop).Scan(&currentEpoch); e != nil {
		return a, dbError(e)
	}
	if e = tx.QueryRow(ctx, "SELECT request_id::text,status,error_code FROM taobao_actions WHERE request_id=$1 AND shop_id=$2 FOR UPDATE", id, shop).Scan(&a.RequestID, &a.Status, &a.ErrorCode); e != nil {
		return a, dbError(e)
	}
	if a.Status != "pending" {
		return a, dbError(tx.Commit(ctx))
	}
	if currentEpoch != epoch {
		status = "delivery_unknown"
		code = "session_interrupted"
	}
	e = tx.QueryRow(ctx, `UPDATE taobao_actions SET status=$3,error_code=$4,updated_at=now() WHERE request_id=$1 AND shop_id=$2 RETURNING request_id::text,status,error_code`, id, shop, status, code).Scan(&a.RequestID, &a.Status, &a.ErrorCode)
	if e != nil {
		return a, dbError(e)
	}
	return a, dbError(tx.Commit(ctx))
}
func (s *Store) RecoverIntegrations(ctx context.Context) error {
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return dbError(e)
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, "UPDATE taobao_events SET status='failed',error_code='restart_outcome_unknown' WHERE status='generating'"); e != nil {
		return dbError(e)
	}
	if _, e = tx.Exec(ctx, "UPDATE taobao_actions SET status='delivery_unknown',error_code='restart_outcome_unknown' WHERE status='pending'"); e != nil {
		return dbError(e)
	}
	return dbError(tx.Commit(ctx))
}
