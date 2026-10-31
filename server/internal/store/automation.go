package store

import (
	"context"
	"errors"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/jackc/pgx/v5"
)

func generationLimits(ctx context.Context, q querier, shop string) (domain.GenerationLimits, error) {
	p := domain.DefaultGenerationLimits(shop)
	err := q.QueryRow(ctx, "SELECT requests_per_minute,daily_request_limit,daily_token_limit,version,updated_at FROM generation_limits WHERE shop_id=$1", shop).Scan(&p.RequestsPerMinute, &p.DailyRequestLimit, &p.DailyTokenLimit, &p.Version, &p.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return p, nil
	}
	return p, dbError(err)
}
func (s *Store) GetGenerationLimits(ctx context.Context, shop string) (domain.GenerationLimits, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return domain.GenerationLimits{}, err
	}
	return generationLimits(ctx, s.pool, shop)
}
func (s *Store) SaveGenerationLimits(ctx context.Context, p domain.GenerationLimits) (domain.GenerationLimits, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, p.ShopID); err != nil {
		return p, err
	}
	old, err := generationLimits(ctx, tx, p.ShopID)
	if err != nil {
		return p, err
	}
	if old.Version != p.Version {
		return p, domain.Conflict("stale_version", "生成限额已改变，请刷新后编辑。")
	}
	_, err = tx.Exec(ctx, `INSERT INTO generation_limits(shop_id,requests_per_minute,daily_request_limit,daily_token_limit) VALUES($1,$2,$3,$4) ON CONFLICT(shop_id) DO UPDATE SET requests_per_minute=EXCLUDED.requests_per_minute,daily_request_limit=EXCLUDED.daily_request_limit,daily_token_limit=EXCLUDED.daily_token_limit,version=generation_limits.version+1,updated_at=now()`, p.ShopID, p.RequestsPerMinute, p.DailyRequestLimit, p.DailyTokenLimit)
	if err != nil {
		return p, dbError(err)
	}
	p, err = generationLimits(ctx, tx, p.ShopID)
	if err != nil {
		return p, err
	}
	if err = audit(ctx, tx, p.ShopID, p.ShopID, "generation_limits_saved", map[string]any{"version": p.Version}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}
func (s *Store) GenerationUsage(ctx context.Context, shop string) (domain.GenerationUsage, error) {
	l, err := s.GetGenerationLimits(ctx, shop)
	if err != nil {
		return domain.GenerationUsage{}, err
	}
	p := domain.GenerationUsage{Limits: l, DateUTC: time.Now().UTC().Format("2006-01-02"), Enforcement: "本地保守预留限额；未知请求保留预留，不代表供应商账单上限。"}
	err = s.pool.QueryRow(ctx, `SELECT count(*),COALESCE(sum(charged_tokens),0),count(*) FILTER(WHERE status='unknown'),count(*) FILTER(WHERE status='pending') FROM usage_events WHERE shop_id=$1 AND quota_date=$2::date`, shop, p.DateUTC).Scan(&p.RequestsToday, &p.ChargedTokensToday, &p.UnknownRequestsToday, &p.PendingRequestsToday)
	return p, dbError(err)
}
func (s *Store) StartLimitedUsage(ctx context.Context, shop, session, model string, reservation int64) (domain.UsageEvent, error) {
	p := domain.UsageEvent{ID: domain.NewID(), ShopID: shop, SessionID: session, Model: model, Status: "pending"}
	if reservation != domain.GenerationReservationTokens || !domain.TextWithin(model, 1, 120) {
		return p, domain.Invalid("生成预留参数无效。")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, shop); err != nil {
		return p, err
	}
	sess, err := outputSession(ctx, tx, shop, session, "FOR SHARE")
	if err != nil {
		return p, err
	}
	if sess.Status != "active" {
		return p, domain.Conflict("session_inactive", "场次已暂停或结束，本次未请求模型。")
	}
	l, err := generationLimits(ctx, tx, shop)
	if err != nil {
		return p, err
	}
	var requests, charged, recent int64
	err = tx.QueryRow(ctx, `SELECT count(*) FILTER(WHERE quota_date=(now() AT TIME ZONE 'UTC')::date),COALESCE(sum(charged_tokens) FILTER(WHERE quota_date=(now() AT TIME ZONE 'UTC')::date),0),count(*) FILTER(WHERE created_at>now()-interval '1 minute') FROM usage_events WHERE shop_id=$1`, shop).Scan(&requests, &charged, &recent)
	if err != nil {
		return p, dbError(err)
	}
	if recent >= int64(l.RequestsPerMinute) {
		return p, &domain.Error{Status: 429, Code: "generation_rate_limited", Message: "本店本分钟生成请求已达上限，本次未请求模型。"}
	}
	if (l.DailyRequestLimit > 0 && requests >= l.DailyRequestLimit) || (l.DailyTokenLimit > 0 && charged+reservation > l.DailyTokenLimit) {
		return p, &domain.Error{Status: 429, Code: "generation_budget_exceeded", Message: "当日生成限额不足以预留本次请求；未知用量仍占用预留。"}
	}
	err = tx.QueryRow(ctx, `INSERT INTO usage_events(id,shop_id,session_id,model,reserved_tokens,charged_tokens) VALUES($1,$2,$3,$4,$5,$5) RETURNING created_at,updated_at`, p.ID, shop, session, model, reservation).Scan(&p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		return p, dbError(err)
	}
	return p, dbError(tx.Commit(ctx))
}

const scheduleColumns = `id::text,shop_id::text,session_id::text,job_id::text,run_at,expires_at,status,reason,error_code,created_at,updated_at`

func scanSchedule(r scanner) (p domain.SpeechSchedule, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.SessionID, &p.JobID, &p.RunAt, &p.ExpiresAt, &p.Status, &p.Reason, &p.ErrorCode, &p.CreatedAt, &p.UpdatedAt)
	return p, dbError(err)
}
func (s *Store) SetDispatchPolicy(ctx context.Context, shop, id string, priority int, expires *time.Time) (domain.Job, error) {
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
	if j.Status == "sending" || j.Status == "sent" || j.Status == "cancelled" || j.Status == "delivery_unknown" {
		return j, domain.Conflict("job_state_changed", "已发送、取消或结果不明的任务不能修改派发策略。")
	}
	j, err = scanJob(tx.QueryRow(ctx, "UPDATE speech_jobs SET priority=$3,expires_at=$4,updated_at=now() WHERE id=$1 AND shop_id=$2 RETURNING "+jobColumns, id, shop, priority, expires))
	if err != nil {
		return j, err
	}
	if err = audit(ctx, tx, shop, id, "dispatch_policy_saved", map[string]any{"priority": priority, "expires_at": expires}); err != nil {
		return j, err
	}
	return j, dbError(tx.Commit(ctx))
}
func (s *Store) CreateSchedule(ctx context.Context, shop, job string, run, expires time.Time) (domain.SpeechSchedule, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.SpeechSchedule{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, job)
	if err != nil {
		return domain.SpeechSchedule{}, err
	}
	if err = domain.ValidateJob(j, snap, time.Now()); err != nil {
		return domain.SpeechSchedule{}, err
	}
	if j.Status != "approved" && j.Status != "queued" && j.Status != "synthesizing" && j.Status != "ready" {
		return domain.SpeechSchedule{}, domain.Conflict("not_approved", "只有已审核且尚未派发的有效任务可以定时安排。")
	}
	if j.ExpiresAt != nil && !run.Before(*j.ExpiresAt) {
		return domain.SpeechSchedule{}, domain.Conflict("job_expired", "计划时间必须早于任务截止时间。")
	}
	p, err := scanSchedule(tx.QueryRow(ctx, "INSERT INTO speech_schedules(id,shop_id,session_id,job_id,run_at,expires_at) VALUES($1,$2,$3,$4,$5,$6) RETURNING "+scheduleColumns, domain.NewID(), shop, j.SessionID, job, run.UTC(), expires.UTC()))
	if err != nil {
		return p, err
	}
	if j.Status == "approved" {
		if _, err = updateJob(ctx, tx, j, "queued", "定时计划已创建，等待本地合成。", ""); err != nil {
			return p, err
		}
	}
	if err = audit(ctx, tx, shop, p.ID, "speech_scheduled", map[string]any{"job_id": job, "run_at": run, "expires_at": expires}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}
func (s *Store) ListSchedules(ctx context.Context, shop, session string) ([]domain.SpeechSchedule, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	if session != "" {
		if _, err := s.GetSession(ctx, shop, session); err != nil {
			return nil, err
		}
	}
	r, err := s.pool.Query(ctx, "SELECT "+scheduleColumns+" FROM speech_schedules WHERE shop_id=$1 AND ($2='' OR session_id::text=$2) ORDER BY created_at DESC LIMIT 100", shop, session)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.SpeechSchedule{}
	for r.Next() {
		p, e := scanSchedule(r)
		if e != nil {
			return nil, e
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) CancelSchedule(ctx context.Context, shop, id string) (domain.SpeechSchedule, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.SpeechSchedule{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := scanSchedule(tx.QueryRow(ctx, "SELECT "+scheduleColumns+" FROM speech_schedules WHERE id=$1 AND shop_id=$2 FOR UPDATE", id, shop))
	if err != nil {
		return p, err
	}
	if p.Status == "dispatching" || p.Status == "sent" || p.Status == "delivery_unknown" {
		return p, domain.Conflict("requires_takeover", "计划已经开始派发或结果不明，请使用场次接管。")
	}
	p, err = scanSchedule(tx.QueryRow(ctx, "UPDATE speech_schedules SET status='cancelled',reason='操作者取消定时计划。',error_code='operator_cancelled',updated_at=now() WHERE id=$1 RETURNING "+scheduleColumns, id))
	if err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}
func (s *Store) ClaimSchedule(ctx context.Context) (domain.SpeechSchedule, error) {
	var id, shop, job string
	err := s.pool.QueryRow(ctx, `SELECT sc.id::text,sc.shop_id::text,sc.job_id::text FROM speech_schedules sc JOIN speech_jobs j ON j.id=sc.job_id WHERE sc.status='scheduled' AND sc.run_at<=now() AND (j.status NOT IN ('queued','synthesizing') OR sc.expires_at<=now()) ORDER BY j.priority DESC,sc.run_at,sc.id LIMIT 1`).Scan(&id, &shop, &job)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.SpeechSchedule{}, ErrNoWork
	}
	if err != nil {
		return domain.SpeechSchedule{}, dbError(err)
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.SpeechSchedule{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	j, snap, err := lockJob(ctx, tx, shop, job)
	if err != nil {
		return domain.SpeechSchedule{}, err
	}
	p, err := scanSchedule(tx.QueryRow(ctx, "SELECT "+scheduleColumns+" FROM speech_schedules WHERE id=$1 AND shop_id=$2 FOR UPDATE", id, shop))
	if err != nil {
		return p, err
	}
	if p.Status != "scheduled" {
		return p, ErrNoWork
	}
	code, reason := "", ""
	now := time.Now()
	if !now.Before(p.ExpiresAt) {
		code = "schedule_expired"
		reason = "计划已超过允许派发窗口，不会补播。"
	} else if err = domain.ValidateJob(j, snap, now); err != nil {
		code = "stale_context"
		reason = "任务资料、场次或截止时间已改变，请重新安排。"
	} else if j.Status != "ready" {
		code = "audio_not_ready"
		reason = "任务未保有可派发的音频，请检查后重新安排。"
	} else if lease, _, e := outputSendLease(ctx, tx, snap.Session); e != nil || lease == nil {
		code = "output_offline"
		reason = "独立输出未在线，本次计划不会自动重试。"
	}
	if code != "" {
		_, err = tx.Exec(ctx, "UPDATE speech_schedules SET status='failed',reason=$2,error_code=$3,updated_at=now() WHERE id=$1", id, reason, code)
		if err != nil {
			return p, dbError(err)
		}
		if err = tx.Commit(ctx); err != nil {
			return p, dbError(err)
		}
		return p, ErrNoWork
	}
	p, err = scanSchedule(tx.QueryRow(ctx, "UPDATE speech_schedules SET status='dispatching',reason='正在提交上游；不代表实际播出。',updated_at=now() WHERE id=$1 RETURNING "+scheduleColumns, id))
	if err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}
func (s *Store) FinishSchedule(ctx context.Context, shop, id, status, reason, code string) error {
	if status != "sent" && status != "failed" && status != "delivery_unknown" {
		return domain.Invalid("计划完成状态无效。")
	}
	_, err := s.pool.Exec(ctx, "UPDATE speech_schedules SET status=$3,reason=$4,error_code=$5,updated_at=now() WHERE id=$1 AND shop_id=$2 AND status='dispatching'", id, shop, status, reason, code)
	return dbError(err)
}
func cancelSessionSchedules(ctx context.Context, tx pgx.Tx, session string) error {
	_, err := tx.Exec(ctx, `UPDATE speech_schedules SET status=CASE WHEN status='dispatching' THEN 'delivery_unknown' ELSE 'cancelled' END,reason='场次接管、结束或输出撤销，旧计划已失效。',error_code='session_interrupted',updated_at=now() WHERE session_id=$1 AND status IN ('scheduled','dispatching')`, session)
	return dbError(err)
}
func recoverAutomation(ctx context.Context, tx pgx.Tx) error {
	if _, err := tx.Exec(ctx, "UPDATE usage_events SET status='unknown',error_code='restart_usage_unknown',updated_at=now() WHERE status='pending'"); err != nil {
		return dbError(err)
	}
	if _, err := tx.Exec(ctx, "UPDATE speech_schedules SET status='delivery_unknown',reason='派发期间重启，禁止自动重播。',error_code='restart_delivery_unknown',updated_at=now() WHERE status='dispatching'"); err != nil {
		return dbError(err)
	}
	_, err := tx.Exec(ctx, "UPDATE speech_schedules SET status='failed',reason='重启时已错过计划时间，不会补播。',error_code='restart_missed_schedule',updated_at=now() WHERE status='scheduled' AND run_at<=now()")
	return dbError(err)
}
