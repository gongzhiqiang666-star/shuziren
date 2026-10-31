package store

import (
	"context"
	"crypto/subtle"
	"errors"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/jackc/pgx/v5"
)

type outputRecord struct {
	Config                          domain.OutputConfig
	Enabled                         bool
	Generation                      int64
	TokenHash                       []byte
	LeaseID, ReceiverID             *string
	LeaseEpoch                      *int64
	LeaseExpiresAt, LastHeartbeatAt *time.Time
	PeerState                       string
	VideoReady, AudioReady          bool
	MediaID                         *string
}

const outputColumns = `width,height,fit,background,enabled,generation,token_hash,lease_id::text,receiver_id::text,lease_epoch,lease_expires_at,last_heartbeat_at,peer_state,video_ready,audio_ready,media_session_id`
const clearLeaseSQL = `lease_id=NULL,receiver_id=NULL,lease_epoch=NULL,lease_expires_at=NULL,last_heartbeat_at=NULL,peer_state='closed',video_ready=false,audio_ready=false`

func readOutput(ctx context.Context, q querier, shop, id, lock string) (outputRecord, error) {
	o := outputRecord{Config: domain.DefaultOutputConfig(), PeerState: "closed"}
	err := q.QueryRow(ctx, "SELECT "+outputColumns+" FROM session_outputs WHERE session_id=$1 AND shop_id=$2 "+lock, id, shop).Scan(&o.Config.Width, &o.Config.Height, &o.Config.Fit, &o.Config.Background, &o.Enabled, &o.Generation, &o.TokenHash, &o.LeaseID, &o.ReceiverID, &o.LeaseEpoch, &o.LeaseExpiresAt, &o.LastHeartbeatAt, &o.PeerState, &o.VideoReady, &o.AudioReady, &o.MediaID)
	if errors.Is(err, pgx.ErrNoRows) {
		return o, nil
	}
	return o, dbError(err)
}
func outputStatus(o outputRecord, p domain.Session, receiver string) domain.OutputStatus {
	now := time.Now().UTC()
	valid := o.Enabled && o.LeaseID != nil && o.LeaseEpoch != nil && *o.LeaseEpoch == p.Epoch && o.LeaseExpiresAt != nil && o.LeaseExpiresAt.After(now)
	online := valid && p.Status == "active" && o.MediaID != nil && p.MediaSessionID != nil && *o.MediaID == *p.MediaSessionID && o.PeerState == "connected" && o.VideoReady && o.AudioReady && o.LastHeartbeatAt != nil && o.LastHeartbeatAt.After(now.Add(-time.Duration(domain.OutputLeaseMS)*time.Millisecond))
	state := "offline"
	switch {
	case p.Status == "ended":
		state = "ended"
	case !o.Enabled:
		state = "disabled"
	case p.Status == "paused":
		state = "paused"
	case online:
		state = "connected"
	case valid:
		state = "negotiating"
	}
	r := domain.OutputStatus{SessionID: p.ID, Enabled: o.Enabled, Generation: o.Generation, SessionStatus: p.Status, Epoch: p.Epoch, Config: o.Config, State: state, Online: online, PeerState: o.PeerState, VideoReady: o.VideoReady, AudioReady: o.AudioReady, LastHeartbeatAt: o.LastHeartbeatAt, LeaseExpiresAt: o.LeaseExpiresAt, HeartbeatIntervalMS: domain.OutputHeartbeatMS, LeaseTTLMS: domain.OutputLeaseMS}
	if valid && receiver != "" && o.ReceiverID != nil && *o.ReceiverID == receiver {
		r.LeaseOwned = true
		r.LeaseID = o.LeaseID
	}
	return r
}
func outputAuthValid(o outputRecord, a domain.OutputAuth) bool {
	return o.Enabled && o.Generation == a.Generation && len(o.TokenHash) == 32 && subtle.ConstantTimeCompare(o.TokenHash, a.TokenHash) == 1
}
func outputLeaseValid(o outputRecord, p domain.Session, receiver, lease string) bool {
	return o.LeaseID != nil && *o.LeaseID == lease && o.ReceiverID != nil && *o.ReceiverID == receiver && o.LeaseEpoch != nil && *o.LeaseEpoch == p.Epoch && o.LeaseExpiresAt != nil && o.LeaseExpiresAt.After(time.Now())
}
func outputLeaseError() error {
	return domain.Conflict("output_lease_invalid", "输出租约已失效。请关闭旧连接，查询状态后重新连接。")
}
func outputSession(ctx context.Context, tx pgx.Tx, shop, id, lock string) (domain.Session, error) {
	// Shop -> session -> output/job is the shared lock order. Generation quota
	// reservations lock the shop; never hold a session while waiting on its FK.
	var owner string
	if err := tx.QueryRow(ctx, "SELECT id::text FROM shops WHERE id=$1 FOR SHARE", shop).Scan(&owner); err != nil {
		return domain.Session{}, dbError(err)
	}
	return scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2 "+lock, id, shop))
}
func ensureOutput(ctx context.Context, tx pgx.Tx, shop, id string) error {
	_, err := tx.Exec(ctx, "INSERT INTO session_outputs(session_id,shop_id) VALUES($1,$2) ON CONFLICT(session_id) DO NOTHING", id, shop)
	return dbError(err)
}

func (s *Store) AuthenticateOutput(ctx context.Context, hash []byte) (domain.OutputAuth, error) {
	var a domain.OutputAuth
	err := s.pool.QueryRow(ctx, `SELECT o.shop_id::text,o.session_id::text,o.generation,o.token_hash FROM session_outputs o JOIN live_sessions s ON s.id=o.session_id WHERE o.token_hash=$1 AND o.enabled AND s.status<>'ended'`, hash).Scan(&a.ShopID, &a.SessionID, &a.Generation, &a.TokenHash)
	if errors.Is(err, pgx.ErrNoRows) {
		return a, domain.OutputUnauthorized()
	}
	return a, dbError(err)
}
func (s *Store) GetOutput(ctx context.Context, shop, id, receiver string) (domain.OutputStatus, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, shop, id, "FOR SHARE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	o, err := readOutput(ctx, tx, shop, id, "")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	r := outputStatus(o, p, receiver)
	return r, dbError(tx.Commit(ctx))
}
func (s *Store) GetScopedOutput(ctx context.Context, a domain.OutputAuth, receiver string) (domain.OutputStatus, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, a.ShopID, a.SessionID, "FOR SHARE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	o, err := readOutput(ctx, tx, a.ShopID, a.SessionID, "FOR SHARE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	if !outputAuthValid(o, a) {
		return domain.OutputStatus{}, domain.OutputUnauthorized()
	}
	return outputStatus(o, p, receiver), dbError(tx.Commit(ctx))
}
func (s *Store) SaveOutputConfig(ctx context.Context, shop, id string, c domain.OutputConfig) (domain.OutputStatus, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, shop, id, "FOR SHARE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	if err = ensureOutput(ctx, tx, shop, id); err != nil {
		return domain.OutputStatus{}, err
	}
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET width=$3,height=$4,fit=$5,background=$6,updated_at=now() WHERE session_id=$1 AND shop_id=$2", id, shop, c.Width, c.Height, c.Fit, c.Background); err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	o, err := readOutput(ctx, tx, shop, id, "")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	if err = audit(ctx, tx, shop, id, "output_config_saved", c); err != nil {
		return domain.OutputStatus{}, err
	}
	return outputStatus(o, p, ""), dbError(tx.Commit(ctx))
}
func (s *Store) IssueOutput(ctx context.Context, shop, id string, hash []byte) (domain.OutputStatus, *string, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, shop, id, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	if p.Status == "ended" {
		return domain.OutputStatus{}, nil, domain.Conflict("session_ended", "已结束的场次不能签发输出链接。")
	}
	if err = ensureOutput(ctx, tx, shop, id); err != nil {
		return domain.OutputStatus{}, nil, err
	}
	old, err := readOutput(ctx, tx, shop, id, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	stop := p.MediaSessionID
	if stop == nil {
		stop = old.MediaID
	}
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET enabled=true,generation=generation+1,token_hash=$3,"+clearLeaseSQL+",media_session_id=$4,updated_at=now() WHERE session_id=$1 AND shop_id=$2", id, shop, hash, stop); err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	if _, err = tx.Exec(ctx, "UPDATE live_sessions SET media_session_id=NULL,updated_at=now() WHERE id=$1", id); err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	p.MediaSessionID = nil
	o, err := readOutput(ctx, tx, shop, id, "")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	if err = audit(ctx, tx, shop, id, "output_token_issued", map[string]any{"generation": o.Generation}); err != nil {
		return domain.OutputStatus{}, nil, err
	}
	return outputStatus(o, p, ""), stop, dbError(tx.Commit(ctx))
}
func (s *Store) RevokeOutput(ctx context.Context, shop, id string) (domain.OutputStatus, *string, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, shop, id, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	if err = ensureOutput(ctx, tx, shop, id); err != nil {
		return domain.OutputStatus{}, nil, err
	}
	o, err := readOutput(ctx, tx, shop, id, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	stop := p.MediaSessionID
	if stop == nil {
		stop = o.MediaID
	}
	status := "paused"
	if p.Status == "ended" {
		status = "ended"
	}
	p, err = scanSession(tx.QueryRow(ctx, "UPDATE live_sessions SET status=$2,epoch=epoch+1,media_session_id=NULL,updated_at=now() WHERE id=$1 RETURNING "+sessionColumns, id, status))
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET enabled=false,generation=generation+1,token_hash=NULL,"+clearLeaseSQL+",media_session_id=$3,updated_at=now() WHERE session_id=$1 AND shop_id=$2", id, shop, stop); err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	if err = cancelSessionJobs(ctx, tx, id); err != nil {
		return domain.OutputStatus{}, nil, err
	}
	o, err = readOutput(ctx, tx, shop, id, "")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	if err = audit(ctx, tx, shop, id, "output_revoked", map[string]any{"epoch": p.Epoch, "generation": o.Generation}); err != nil {
		return domain.OutputStatus{}, nil, err
	}
	return outputStatus(o, p, ""), stop, dbError(tx.Commit(ctx))
}
func (s *Store) ClaimOutput(ctx context.Context, a domain.OutputAuth, receiver string) (domain.OutputLease, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputLease{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputLease{}, err
	}
	o, err := readOutput(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputLease{}, err
	}
	if !outputAuthValid(o, a) {
		return domain.OutputLease{}, domain.OutputUnauthorized()
	}
	if p.Status != "active" {
		return domain.OutputLease{}, domain.Conflict("session_inactive", "场次暂停或结束，请等待管理端恢复。")
	}
	if o.LeaseID != nil && o.LeaseExpiresAt != nil && o.LeaseExpiresAt.After(time.Now()) {
		return domain.OutputLease{}, domain.Conflict("output_busy", "此场次已有接收页面租约，请关闭原页面或等待租约到期。")
	}
	l := domain.OutputLease{ID: domain.NewID(), ReceiverID: receiver, Epoch: p.Epoch, OldMediaID: o.MediaID}
	if l.OldMediaID == nil {
		l.OldMediaID = p.MediaSessionID
	}
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET lease_id=$3,receiver_id=$4,lease_epoch=$5,lease_expires_at=$6,last_heartbeat_at=NULL,peer_state='new',video_ready=false,audio_ready=false,updated_at=now() WHERE session_id=$1 AND shop_id=$2", a.SessionID, a.ShopID, l.ID, receiver, p.Epoch, time.Now().UTC().Add(domain.OutputNegotiationSeconds*time.Second)); err != nil {
		return l, dbError(err)
	}
	if _, err = tx.Exec(ctx, "UPDATE live_sessions SET media_session_id=NULL,updated_at=now() WHERE id=$1", a.SessionID); err != nil {
		return l, dbError(err)
	}
	return l, dbError(tx.Commit(ctx))
}
func (s *Store) BindOutput(ctx context.Context, a domain.OutputAuth, l domain.OutputLease, mediaID string) (domain.OutputStatus, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	o, err := readOutput(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	if !outputAuthValid(o, a) {
		return domain.OutputStatus{}, domain.OutputUnauthorized()
	}
	if p.Status != "active" || p.Epoch != l.Epoch || !outputLeaseValid(o, p, l.ReceiverID, l.ID) {
		return domain.OutputStatus{}, outputLeaseError()
	}
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET media_session_id=$3,updated_at=now() WHERE session_id=$1 AND shop_id=$2", a.SessionID, a.ShopID, mediaID); err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	if _, err = tx.Exec(ctx, "UPDATE live_sessions SET media_session_id=$2,updated_at=now() WHERE id=$1", a.SessionID, mediaID); err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	p.MediaSessionID = &mediaID
	o.MediaID = &mediaID
	if err = audit(ctx, tx, a.ShopID, a.SessionID, "output_bound", map[string]any{"lease_id": l.ID, "epoch": l.Epoch, "generation": a.Generation}); err != nil {
		return domain.OutputStatus{}, err
	}
	return outputStatus(o, p, l.ReceiverID), dbError(tx.Commit(ctx))
}
func (s *Store) HeartbeatOutput(ctx context.Context, a domain.OutputAuth, h domain.OutputHeartbeat) (domain.OutputStatus, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, a.ShopID, a.SessionID, "FOR SHARE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	o, err := readOutput(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, err
	}
	if !outputAuthValid(o, a) {
		return domain.OutputStatus{}, domain.OutputUnauthorized()
	}
	if p.Status != "active" || !outputLeaseValid(o, p, h.ReceiverID, h.LeaseID) || o.MediaID == nil || p.MediaSessionID == nil || *o.MediaID != *p.MediaSessionID {
		return domain.OutputStatus{}, outputLeaseError()
	}
	now := time.Now().UTC()
	expires := o.LeaseExpiresAt
	if h.PeerState == "connected" && h.VideoReady && h.AudioReady {
		next := now.Add(domain.OutputLeaseMS * time.Millisecond)
		expires = &next
	}
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET last_heartbeat_at=$3,peer_state=$4,video_ready=$5,audio_ready=$6,lease_expires_at=$7,updated_at=now() WHERE session_id=$1 AND shop_id=$2", a.SessionID, a.ShopID, now, h.PeerState, h.VideoReady, h.AudioReady, expires); err != nil {
		return domain.OutputStatus{}, dbError(err)
	}
	o.LastHeartbeatAt = &now
	o.LeaseExpiresAt = expires
	o.PeerState = h.PeerState
	o.VideoReady = h.VideoReady
	o.AudioReady = h.AudioReady
	return outputStatus(o, p, h.ReceiverID), dbError(tx.Commit(ctx))
}
func (s *Store) ReleaseOutput(ctx context.Context, a domain.OutputAuth, receiver, lease string) (domain.OutputStatus, *string, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := outputSession(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	o, err := readOutput(ctx, tx, a.ShopID, a.SessionID, "FOR UPDATE")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	if !outputAuthValid(o, a) {
		return domain.OutputStatus{}, nil, domain.OutputUnauthorized()
	}
	if o.LeaseID == nil || *o.LeaseID != lease || o.ReceiverID == nil || *o.ReceiverID != receiver {
		return domain.OutputStatus{}, nil, outputLeaseError()
	}
	stop := o.MediaID
	if _, err = tx.Exec(ctx, "UPDATE session_outputs SET "+clearLeaseSQL+",updated_at=now() WHERE session_id=$1 AND shop_id=$2", a.SessionID, a.ShopID); err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	if _, err = tx.Exec(ctx, "UPDATE live_sessions SET media_session_id=NULL,updated_at=now() WHERE id=$1 AND media_session_id=$2", a.SessionID, stop); err != nil {
		return domain.OutputStatus{}, nil, dbError(err)
	}
	p.MediaSessionID = nil
	o, err = readOutput(ctx, tx, a.ShopID, a.SessionID, "")
	if err != nil {
		return domain.OutputStatus{}, nil, err
	}
	return outputStatus(o, p, receiver), stop, dbError(tx.Commit(ctx))
}
func (s *Store) PreviewMedia(ctx context.Context, shop, id string) (*string, error) {
	p, err := s.GetSession(ctx, shop, id)
	if err != nil {
		return nil, err
	}
	o, err := readOutput(ctx, s.pool, shop, id, "")
	if err != nil {
		return nil, err
	}
	if o.Enabled {
		return nil, domain.Conflict("output_managed", "独立输出已启用，管理预览不能替换其接收连接。请先撤销独立输出。")
	}
	if p.MediaSessionID != nil {
		return p.MediaSessionID, nil
	}
	return o.MediaID, nil
}
func (s *Store) KnownMedia(ctx context.Context, shop, id string) (*string, error) {
	p, err := s.GetSession(ctx, shop, id)
	if err != nil {
		return nil, err
	}
	if p.MediaSessionID != nil {
		return p.MediaSessionID, nil
	}
	o, err := readOutput(ctx, s.pool, shop, id, "")
	return o.MediaID, err
}
func invalidateOutput(ctx context.Context, tx pgx.Tx, id, action string) error {
	extra := ""
	if action == "end" {
		extra = ",enabled=false,token_hash=NULL,generation=generation+1"
	}
	_, err := tx.Exec(ctx, "UPDATE session_outputs SET "+clearLeaseSQL+extra+",updated_at=now() WHERE session_id=$1", id)
	return dbError(err)
}
func recoverOutputs(ctx context.Context, tx pgx.Tx) error {
	if _, err := tx.Exec(ctx, "UPDATE live_sessions s SET media_session_id=NULL WHERE EXISTS(SELECT 1 FROM session_outputs o WHERE o.session_id=s.id AND o.enabled)"); err != nil {
		return dbError(err)
	}
	_, err := tx.Exec(ctx, "UPDATE session_outputs SET "+clearLeaseSQL+",updated_at=now()")
	return dbError(err)
}
func outputSendLease(ctx context.Context, tx pgx.Tx, p domain.Session) (*string, int64, error) {
	o, err := readOutput(ctx, tx, p.ShopID, p.ID, "FOR SHARE")
	if err != nil {
		return nil, 0, err
	}
	if !o.Enabled {
		return nil, 0, nil
	}
	if !outputStatus(o, p, "").Online {
		return nil, 0, domain.Conflict("output_offline", "独立接收页尚未报告可播放连接，或心跳租约已失效；禁止派发。")
	}
	return o.LeaseID, o.Generation, nil
}
