package store

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrations embed.FS

const instanceLock int64 = 837462019305

type Store struct {
	pool     *pgxpool.Pool
	lockMu   sync.Mutex
	lockConn *pgxpool.Conn
}

func Open(ctx context.Context, dsn string) (*Store, error) {
	if dsn == "" {
		return nil, errors.New("DATABASE_URL is required")
	}
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, errors.New("invalid DATABASE_URL configuration")
	}
	cfg.MaxConns = 8
	cfg.ConnConfig.ConnectTimeout = 5 * time.Second
	cfg.ConnConfig.RuntimeParams["application_name"] = "shuziren_local_workbench"
	p, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, errors.New("unable to initialize PostgreSQL pool")
	}
	if err = p.Ping(ctx); err != nil {
		p.Close()
		return nil, errors.New("unable to connect to PostgreSQL")
	}
	return &Store{pool: p}, nil
}

func (s *Store) Ping(ctx context.Context) error { return s.pool.Ping(ctx) }

// A session advisory lock MUST stay on a dedicated acquired connection. It must
// never be acquired/released through arbitrary pool connections.
func (s *Store) AcquireInstance(ctx context.Context) error {
	s.lockMu.Lock()
	defer s.lockMu.Unlock()
	if s.lockConn != nil {
		return nil
	}
	c, err := s.pool.Acquire(ctx)
	if err != nil {
		return errors.New("unable to acquire instance connection")
	}
	var ok bool
	if err = c.QueryRow(ctx, "SELECT pg_try_advisory_lock($1)", instanceLock).Scan(&ok); err != nil || !ok {
		c.Release()
		return errors.New("another backend owns this database or the instance lock is unavailable")
	}
	s.lockConn = c
	return nil
}

func (s *Store) CheckInstance(ctx context.Context) error {
	s.lockMu.Lock()
	defer s.lockMu.Unlock()
	if s.lockConn == nil {
		return errors.New("instance lock not held")
	}
	if err := s.lockConn.Conn().Ping(ctx); err != nil {
		return errors.New("instance lock connection lost")
	}
	return nil
}

func (s *Store) Close() {
	s.lockMu.Lock()
	if s.lockConn != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		_, _ = s.lockConn.Exec(ctx, "SELECT pg_advisory_unlock($1)", instanceLock)
		cancel()
		s.lockConn.Release()
		s.lockConn = nil
	}
	s.lockMu.Unlock()
	s.pool.Close()
}

func (s *Store) Migrate(ctx context.Context) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return dbError(err)
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock($1)", instanceLock+1); err != nil {
		return dbError(err)
	}
	if _, err = tx.Exec(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`); err != nil {
		return dbError(err)
	}
	entries, err := migrations.ReadDir("migrations")
	if err != nil {
		return err
	}
	for _, e := range entries {
		var exists bool
		if err = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version=$1)", e.Name()).Scan(&exists); err != nil {
			return dbError(err)
		}
		if exists {
			continue
		}
		b, err := migrations.ReadFile("migrations/" + e.Name())
		if err != nil {
			return err
		}
		if _, err = tx.Exec(ctx, string(b)); err != nil {
			return fmt.Errorf("migration %s failed (%s)", e.Name(), sqlState(err))
		}
		if _, err = tx.Exec(ctx, "INSERT INTO schema_migrations(version) VALUES($1)", e.Name()); err != nil {
			return dbError(err)
		}
	}
	return dbError(tx.Commit(ctx))
}

// Recovery never replays a possibly delivered message. A lost synthesis must be
// explicitly requested again; an uncertain media delivery requires takeover.
func (s *Store) Recover(ctx context.Context) error {
	if err := s.CheckInstance(ctx); err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return dbError(err)
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `UPDATE speech_jobs SET status='failed',error_code='restart_interrupted',reason='服务重启中断了合成，需要人工确认后重试。',updated_at=now() WHERE status='synthesizing'`); err != nil {
		return dbError(err)
	}
	if _, err = tx.Exec(ctx, `UPDATE speech_jobs SET status='delivery_unknown',error_code='restart_delivery_unknown',reason='发送期间服务重启，不能确认上游结果；请接管场次核对，禁止自动重播。',updated_at=now() WHERE status='sending'`); err != nil {
		return dbError(err)
	}
	return dbError(tx.Commit(ctx))
}

func sqlState(err error) string {
	var p *pgconn.PgError
	if errors.As(err, &p) {
		return p.Code
	}
	return "unavailable"
}
func dbError(err error) error {
	if err == nil {
		return nil
	}
	var d *domain.Error
	if errors.As(err, &d) {
		return err
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.NotFound()
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return err
	}
	var p *pgconn.PgError
	if errors.As(err, &p) {
		switch p.Code {
		case "23505":
			return domain.Conflict("duplicate_resource", "该资源已存在，或状态已经被其他操作改变。")
		case "23503":
			return domain.NotFound()
		case "23514", "22P02", "22001", "22003":
			return domain.Invalid("字段类型、范围或资源标识不正确。")
		case "40001", "40P01":
			return domain.Conflict("concurrent_change", "数据正在被其他操作修改，请刷新后重试。")
		}
	}
	return domain.Unavailable("storage_unavailable", "数据服务暂时不可用，请稍后重试。")
}

type scanner interface{ Scan(...any) error }
type querier interface {
	QueryRow(context.Context, string, ...any) pgx.Row
	Query(context.Context, string, ...any) (pgx.Rows, error)
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
}

const productColumns = `id::text,shop_id::text,title,sku,description,specs,price_cents,stock,active,version,expires_at,updated_at`
const personaColumns = `shop_id::text,name,tone,prompt,version,updated_at`
const sessionColumns = `id::text,shop_id::text,title,status,epoch,media_session_id,created_at,updated_at`
const jobColumns = `id::text,shop_id::text,session_id::text,product_id::text,product_version,persona_version,epoch,source,question,text,status,reason,error_code,input_tokens,output_tokens,created_at,updated_at,knowledge_version,approved_at,audio_ready`

func scanProduct(r scanner) (p domain.Product, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.Title, &p.SKU, &p.Description, &p.Specs, &p.PriceCents, &p.Stock, &p.Active, &p.Version, &p.ExpiresAt, &p.UpdatedAt)
	return p, dbError(err)
}
func scanPersona(r scanner) (p domain.Persona, err error) {
	err = r.Scan(&p.ShopID, &p.Name, &p.Tone, &p.Prompt, &p.Version, &p.UpdatedAt)
	return p, dbError(err)
}
func scanSession(r scanner) (p domain.Session, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.Title, &p.Status, &p.Epoch, &p.MediaSessionID, &p.CreatedAt, &p.UpdatedAt)
	return p, dbError(err)
}
func scanJob(r scanner) (p domain.Job, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.SessionID, &p.ProductID, &p.ProductVersion, &p.PersonaVersion, &p.Epoch, &p.Source, &p.Question, &p.Text, &p.Status, &p.Reason, &p.ErrorCode, &p.InputTokens, &p.OutputTokens, &p.CreatedAt, &p.UpdatedAt, &p.KnowledgeVersion, &p.ApprovedAt, &p.AudioReady)
	return p, dbError(err)
}

func requireShop(ctx context.Context, q querier, shopID string) error {
	var id string
	return dbError(q.QueryRow(ctx, "SELECT id::text FROM shops WHERE id=$1", shopID).Scan(&id))
}
func audit(ctx context.Context, q querier, shopID, id, event string, details any) error {
	b, err := json.Marshal(details)
	if err != nil {
		return err
	}
	_, err = q.Exec(ctx, "INSERT INTO audit_events(shop_id,resource_id,event,details) VALUES($1,$2,$3,$4)", shopID, id, event, b)
	return dbError(err)
}

func (s *Store) ListShops(ctx context.Context) ([]domain.Shop, error) {
	r, err := s.pool.Query(ctx, "SELECT id::text,name,created_at FROM shops ORDER BY created_at DESC LIMIT 1000")
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Shop{}
	for r.Next() {
		var p domain.Shop
		if err = r.Scan(&p.ID, &p.Name, &p.CreatedAt); err != nil {
			return nil, dbError(err)
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) CreateShop(ctx context.Context, name string) (domain.Shop, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Shop{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p := domain.Shop{ID: domain.NewID(), Name: name}
	if err = tx.QueryRow(ctx, "INSERT INTO shops(id,name) VALUES($1,$2) RETURNING created_at", p.ID, p.Name).Scan(&p.CreatedAt); err != nil {
		return p, dbError(err)
	}
	persona := domain.DefaultPersona(p.ID)
	if _, err = tx.Exec(ctx, "INSERT INTO personas(shop_id,name,tone,prompt) VALUES($1,$2,$3,$4)", p.ID, persona.Name, persona.Tone, persona.Prompt); err != nil {
		return p, dbError(err)
	}
	if err = audit(ctx, tx, p.ID, p.ID, "shop_created", map[string]any{}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) ListProducts(ctx context.Context, shopID string) ([]domain.Product, error) {
	if err := requireShop(ctx, s.pool, shopID); err != nil {
		return nil, err
	}
	r, err := s.pool.Query(ctx, "SELECT "+productColumns+" FROM products WHERE shop_id=$1 ORDER BY updated_at DESC LIMIT 1000", shopID)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Product{}
	for r.Next() {
		p, err := scanProduct(r)
		if err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) SaveProduct(ctx context.Context, p domain.Product, create bool) (domain.Product, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = requireShop(ctx, tx, p.ShopID); err != nil {
		return p, err
	}
	if create {
		p.ID = domain.NewID()
		p, err = scanProduct(tx.QueryRow(ctx, `INSERT INTO products(id,shop_id,title,sku,description,specs,price_cents,stock,active,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING `+productColumns, p.ID, p.ShopID, p.Title, p.SKU, p.Description, p.Specs, p.PriceCents, p.Stock, p.Active, p.ExpiresAt))
	} else {
		oldID, shop, expected := p.ID, p.ShopID, p.Version
		p, err = scanProduct(tx.QueryRow(ctx, `UPDATE products SET title=$3,sku=$4,description=$5,specs=$6,price_cents=$7,stock=$8,active=$9,expires_at=$10,version=version+1,updated_at=now() WHERE id=$1 AND shop_id=$2 AND version=$11 RETURNING `+productColumns, p.ID, p.ShopID, p.Title, p.SKU, p.Description, p.Specs, p.PriceCents, p.Stock, p.Active, p.ExpiresAt, p.Version))
		if err != nil {
			var v int64
			if e := tx.QueryRow(ctx, "SELECT version FROM products WHERE id=$1 AND shop_id=$2", oldID, shop).Scan(&v); e == nil && v != expected {
				return p, domain.Conflict("stale_version", "商品已被修改，请刷新后重新编辑。")
			}
			return p, err
		}
	}
	if err != nil {
		return p, err
	}
	b, _ := json.Marshal(p)
	if _, err = tx.Exec(ctx, "INSERT INTO product_history(product_id,version,shop_id,snapshot) VALUES($1,$2,$3,$4)", p.ID, p.Version, p.ShopID, b); err != nil {
		return p, dbError(err)
	}
	if err = audit(ctx, tx, p.ShopID, p.ID, "product_saved", map[string]any{"version": p.Version}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) GetPersona(ctx context.Context, shopID string) (domain.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx, "SELECT "+personaColumns+" FROM personas WHERE shop_id=$1", shopID))
}
func (s *Store) SavePersona(ctx context.Context, p domain.Persona) (domain.Persona, error) {
	shop, expected := p.ShopID, p.Version
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err = scanPersona(tx.QueryRow(ctx, `UPDATE personas SET name=$2,tone=$3,prompt=$4,version=version+1,updated_at=now() WHERE shop_id=$1 AND version=$5 RETURNING `+personaColumns, p.ShopID, p.Name, p.Tone, p.Prompt, p.Version))
	if err != nil {
		var v int64
		if e := tx.QueryRow(ctx, "SELECT version FROM personas WHERE shop_id=$1", shop).Scan(&v); e == nil && v != expected {
			return p, domain.Conflict("stale_version", "人格已被修改，请刷新后重新编辑。")
		}
		return p, err
	}
	if err = audit(ctx, tx, p.ShopID, p.ShopID, "persona_saved", map[string]any{"version": p.Version}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) ListKnowledge(ctx context.Context, shopID string) ([]domain.Knowledge, error) {
	if err := requireShop(ctx, s.pool, shopID); err != nil {
		return nil, err
	}
	return listKnowledge(ctx, s.pool, shopID)
}
func listKnowledge(ctx context.Context, q querier, shopID string) ([]domain.Knowledge, error) {
	r, err := q.Query(ctx, "SELECT id::text,shop_id::text,title,content,kind,updated_at FROM knowledge WHERE shop_id=$1 ORDER BY updated_at DESC LIMIT 1000", shopID)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Knowledge{}
	for r.Next() {
		var k domain.Knowledge
		if err = r.Scan(&k.ID, &k.ShopID, &k.Title, &k.Content, &k.Kind, &k.UpdatedAt); err != nil {
			return nil, dbError(err)
		}
		out = append(out, k)
	}
	return out, dbError(r.Err())
}
func (s *Store) SaveKnowledge(ctx context.Context, k domain.Knowledge, create bool) (domain.Knowledge, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return k, dbError(err)
	}
	defer tx.Rollback(ctx)
	var v int64
	if err = tx.QueryRow(ctx, "SELECT knowledge_version FROM shops WHERE id=$1 FOR UPDATE", k.ShopID).Scan(&v); err != nil {
		return k, dbError(err)
	}
	if create {
		k.ID = domain.NewID()
		err = tx.QueryRow(ctx, "INSERT INTO knowledge(id,shop_id,title,content,kind) VALUES($1,$2,$3,$4,$5) RETURNING updated_at", k.ID, k.ShopID, k.Title, k.Content, k.Kind).Scan(&k.UpdatedAt)
	} else {
		err = tx.QueryRow(ctx, "UPDATE knowledge SET title=$3,content=$4,kind=$5,updated_at=now() WHERE id=$1 AND shop_id=$2 RETURNING updated_at", k.ID, k.ShopID, k.Title, k.Content, k.Kind).Scan(&k.UpdatedAt)
	}
	if err != nil {
		return k, dbError(err)
	}
	if _, err = tx.Exec(ctx, "UPDATE shops SET knowledge_version=knowledge_version+1 WHERE id=$1", k.ShopID); err != nil {
		return k, dbError(err)
	}
	if err = audit(ctx, tx, k.ShopID, k.ID, "knowledge_saved", map[string]any{"kind": k.Kind, "knowledge_version": v + 1}); err != nil {
		return k, err
	}
	return k, dbError(tx.Commit(ctx))
}
func (s *Store) DeleteKnowledge(ctx context.Context, shopID, id string) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return dbError(err)
	}
	defer tx.Rollback(ctx)
	var v int64
	if err = tx.QueryRow(ctx, "SELECT knowledge_version FROM shops WHERE id=$1 FOR UPDATE", shopID).Scan(&v); err != nil {
		return dbError(err)
	}
	tag, err := tx.Exec(ctx, "DELETE FROM knowledge WHERE id=$1 AND shop_id=$2", id, shopID)
	if err != nil {
		return dbError(err)
	}
	if tag.RowsAffected() == 0 {
		return domain.NotFound()
	}
	if _, err = tx.Exec(ctx, "UPDATE shops SET knowledge_version=knowledge_version+1 WHERE id=$1", shopID); err != nil {
		return dbError(err)
	}
	if err = audit(ctx, tx, shopID, id, "knowledge_deleted", map[string]any{"knowledge_version": v + 1}); err != nil {
		return err
	}
	return dbError(tx.Commit(ctx))
}

func (s *Store) ListSessions(ctx context.Context, shopID string) ([]domain.Session, error) {
	if err := requireShop(ctx, s.pool, shopID); err != nil {
		return nil, err
	}
	r, err := s.pool.Query(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE shop_id=$1 ORDER BY created_at DESC LIMIT 1000", shopID)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Session{}
	for r.Next() {
		p, err := scanSession(r)
		if err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) CreateSession(ctx context.Context, shopID, title string) (domain.Session, error) {
	if err := requireShop(ctx, s.pool, shopID); err != nil {
		return domain.Session{}, err
	}
	return scanSession(s.pool.QueryRow(ctx, "INSERT INTO live_sessions(id,shop_id,title) VALUES($1,$2,$3) RETURNING "+sessionColumns, domain.NewID(), shopID, title))
}
func (s *Store) GetSession(ctx context.Context, shopID, id string) (domain.Session, error) {
	return scanSession(s.pool.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2", id, shopID))
}

func (s *Store) ChangeSession(ctx context.Context, shopID, id, action string) (domain.Session, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.Session{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	p, err := scanSession(tx.QueryRow(ctx, "SELECT "+sessionColumns+" FROM live_sessions WHERE id=$1 AND shop_id=$2 FOR UPDATE", id, shopID))
	if err != nil {
		return p, err
	}
	if action == "resume" {
		if p.Status == "ended" {
			return p, domain.Conflict("session_ended", "已结束的本地场次不能恢复，请创建新场次。")
		}
		p, err = scanSession(tx.QueryRow(ctx, "UPDATE live_sessions SET status='active',updated_at=now() WHERE id=$1 RETURNING "+sessionColumns, id))
	} else {
		status := "paused"
		if action == "end" {
			status = "ended"
		}
		if p.Status == "ended" && action != "end" {
			return p, domain.Conflict("session_ended", "本地场次已经结束。")
		}
		p, err = scanSession(tx.QueryRow(ctx, "UPDATE live_sessions SET status=$2,epoch=epoch+1,updated_at=now() WHERE id=$1 RETURNING "+sessionColumns, id, status))
		if err != nil {
			return p, err
		}
		if _, err = tx.Exec(ctx, `UPDATE speech_jobs SET status='cancelled',reason='场次接管或结束，旧执行批次已作废。',error_code='session_interrupted',updated_at=now() WHERE session_id=$1 AND status IN ('draft','blocked','approved','queued','synthesizing','ready','failed')`, id); err != nil {
			return p, dbError(err)
		}
		if _, err = tx.Exec(ctx, `UPDATE speech_jobs SET status='delivery_unknown',reason='接管时发送尚未确认；需停止上游并核对，不能自动重播。',error_code='interrupted_in_flight',updated_at=now() WHERE session_id=$1 AND status='sending'`, id); err != nil {
			return p, dbError(err)
		}
	}
	if err != nil {
		return p, err
	}
	if err = audit(ctx, tx, shopID, id, "session_"+action, map[string]any{"epoch": p.Epoch, "status": p.Status}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) BindMedia(ctx context.Context, shopID, id string, epoch int64, mediaID string) (domain.Session, error) {
	p, err := scanSession(s.pool.QueryRow(ctx, "UPDATE live_sessions SET media_session_id=$4,updated_at=now() WHERE id=$1 AND shop_id=$2 AND epoch=$3 AND status<>'ended' RETURNING "+sessionColumns, id, shopID, epoch, mediaID))
	if err != nil {
		if _, e := s.GetSession(ctx, shopID, id); e == nil {
			return p, domain.Conflict("stale_epoch", "连接过程中场次状态改变，媒体会话未绑定。")
		}
	}
	return p, err
}

func (s *Store) GetQuality(ctx context.Context, shopID string) (domain.QualityProfile, error) {
	var created time.Time
	if err := s.pool.QueryRow(ctx, "SELECT created_at FROM shops WHERE id=$1", shopID).Scan(&created); err != nil {
		return domain.QualityProfile{}, dbError(err)
	}
	var p domain.QualityProfile
	var checks []byte
	err := s.pool.QueryRow(ctx, `SELECT shop_id::text,avatar_name,source_resolution,model_version,canvas_resolution,fps,sync_target_ms,notes,checks,updated_at FROM quality_profiles WHERE shop_id=$1`, shopID).Scan(&p.ShopID, &p.AvatarName, &p.SourceResolution, &p.ModelVersion, &p.CanvasResolution, &p.FPS, &p.SyncTargetMS, &p.Notes, &checks, &p.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.DefaultQuality(shopID, time.Time{}), nil
	}
	if err != nil {
		return p, dbError(err)
	}
	if err = json.Unmarshal(checks, &p.Checks); err != nil {
		return p, domain.Unavailable("quality_invalid", "质量档案无法读取。")
	}
	if p.Checks == nil {
		p.Checks = []domain.QualityCheck{}
	}
	return p, nil
}
func (s *Store) SaveQuality(ctx context.Context, p domain.QualityProfile) (domain.QualityProfile, error) {
	if err := requireShop(ctx, s.pool, p.ShopID); err != nil {
		return p, err
	}
	if p.Checks == nil {
		p.Checks = []domain.QualityCheck{}
	}
	sort.SliceStable(p.Checks, func(i, j int) bool { return p.Checks[i].Key < p.Checks[j].Key })
	b, _ := json.Marshal(p.Checks)
	err := s.pool.QueryRow(ctx, `INSERT INTO quality_profiles(shop_id,avatar_name,source_resolution,model_version,canvas_resolution,fps,sync_target_ms,notes,checks) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(shop_id) DO UPDATE SET avatar_name=EXCLUDED.avatar_name,source_resolution=EXCLUDED.source_resolution,model_version=EXCLUDED.model_version,canvas_resolution=EXCLUDED.canvas_resolution,fps=EXCLUDED.fps,sync_target_ms=EXCLUDED.sync_target_ms,notes=EXCLUDED.notes,checks=EXCLUDED.checks,updated_at=now() RETURNING updated_at`, p.ShopID, p.AvatarName, p.SourceResolution, p.ModelVersion, p.CanvasResolution, p.FPS, p.SyncTargetMS, p.Notes, b).Scan(&p.UpdatedAt)
	return p, dbError(err)
}
