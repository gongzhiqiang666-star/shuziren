package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/jackc/pgx/v5"
)

const promotionColumns = `id::text,shop_id::text,product_id::text,title,description,offer_price_cents,starts_at,ends_at,active,version,updated_at`
const knowledgeRecordColumns = `id::text,shop_id::text,title,content,kind,updated_at,source,scope,scope_id::text,expires_at,version,deleted_at`
const assetColumns = `id::text,shop_id::text,kind,name,identifier,sha256,model_version,authorized,active,version,updated_at`

func scanPromotion(r scanner) (p domain.Promotion, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.ProductID, &p.Title, &p.Description, &p.OfferPriceCents, &p.StartsAt, &p.EndsAt, &p.Active, &p.Version, &p.UpdatedAt)
	return p, dbError(err)
}
func scanKnowledgeRecord(r scanner) (p domain.KnowledgeRecord, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.Title, &p.Content, &p.Kind, &p.UpdatedAt, &p.Source, &p.Scope, &p.ScopeID, &p.ExpiresAt, &p.Version, &p.DeletedAt)
	return p, dbError(err)
}
func scanAsset(r scanner) (p domain.Asset, err error) {
	err = r.Scan(&p.ID, &p.ShopID, &p.Kind, &p.Name, &p.Identifier, &p.SHA256, &p.ModelVersion, &p.Authorized, &p.Active, &p.Version, &p.UpdatedAt)
	p.BindingStatus = "record_only"
	return p, dbError(err)
}
func lockBusinessShop(ctx context.Context, q querier, shop string) error {
	var id string
	return dbError(q.QueryRow(ctx, "SELECT id::text FROM shops WHERE id=$1 FOR UPDATE", shop).Scan(&id))
}
func staleBusinessVersion() error {
	return domain.Conflict("stale_version", "资源已被修改，请刷新后使用最新版本。")
}
func archiveBusiness(ctx context.Context, q querier, table, shop, id string, version int64, snapshot any) error {
	if table != "promotion_history" && table != "asset_history" {
		return domain.Invalid("历史资源类型无效。")
	}
	b, err := json.Marshal(snapshot)
	if err != nil {
		return err
	}
	_, err = q.Exec(ctx, "INSERT INTO "+table+"(resource_id,shop_id,version,snapshot) VALUES($1,$2,$3,$4)", id, shop, version, b)
	return dbError(err)
}

func (s *Store) ListPromotions(ctx context.Context, shop string) ([]domain.Promotion, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	return listPromotions(ctx, s.pool, shop)
}
func listPromotions(ctx context.Context, q querier, shop string) ([]domain.Promotion, error) {
	r, err := q.Query(ctx, "SELECT "+promotionColumns+" FROM promotions WHERE shop_id=$1 ORDER BY updated_at DESC,id LIMIT 1000", shop)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Promotion{}
	for r.Next() {
		p, e := scanPromotion(r)
		if e != nil {
			return nil, e
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) SavePromotion(ctx context.Context, p domain.Promotion, create bool) (domain.Promotion, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, p.ShopID); err != nil {
		return p, err
	}
	if p.ProductID != nil {
		var id string
		if err = tx.QueryRow(ctx, "SELECT id::text FROM products WHERE shop_id=$1 AND id=$2", p.ShopID, *p.ProductID).Scan(&id); err != nil {
			return p, dbError(err)
		}
	}
	if create {
		p.ID = domain.NewID()
		p, err = scanPromotion(tx.QueryRow(ctx, `INSERT INTO promotions(id,shop_id,product_id,title,description,offer_price_cents,starts_at,ends_at,active) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING `+promotionColumns, p.ID, p.ShopID, p.ProductID, p.Title, p.Description, p.OfferPriceCents, p.StartsAt, p.EndsAt, p.Active))
	} else {
		var v int64
		if err = tx.QueryRow(ctx, "SELECT version FROM promotions WHERE shop_id=$1 AND id=$2 FOR UPDATE", p.ShopID, p.ID).Scan(&v); err != nil {
			return p, dbError(err)
		}
		if v != p.Version {
			return p, staleBusinessVersion()
		}
		p, err = scanPromotion(tx.QueryRow(ctx, `UPDATE promotions SET product_id=$3,title=$4,description=$5,offer_price_cents=$6,starts_at=$7,ends_at=$8,active=$9,version=version+1,updated_at=now() WHERE id=$1 AND shop_id=$2 RETURNING `+promotionColumns, p.ID, p.ShopID, p.ProductID, p.Title, p.Description, p.OfferPriceCents, p.StartsAt, p.EndsAt, p.Active))
	}
	if err != nil {
		return p, err
	}
	if err = archiveBusiness(ctx, tx, "promotion_history", p.ShopID, p.ID, p.Version, p); err != nil {
		return p, err
	}
	if err = audit(ctx, tx, p.ShopID, p.ID, "promotion_saved", map[string]any{"version": p.Version, "active": p.Active}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) BusinessHistory(ctx context.Context, shop, kind, id string) ([]domain.HistoryEntry, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	var query string
	switch kind {
	case "persona":
		query = "SELECT version,snapshot,recorded_at,false FROM persona_history WHERE shop_id=$1 ORDER BY version DESC LIMIT 1000"
	case "product":
		query = "SELECT version,snapshot,recorded_at,false FROM product_history WHERE shop_id=$1 AND product_id=$2 ORDER BY version DESC LIMIT 1000"
	case "knowledge":
		query = "SELECT version,snapshot,recorded_at,deleted FROM knowledge_history WHERE shop_id=$1 AND resource_id=$2 ORDER BY version DESC LIMIT 1000"
	case "promotion":
		query = "SELECT version,snapshot,recorded_at,false FROM promotion_history WHERE shop_id=$1 AND resource_id=$2 ORDER BY version DESC LIMIT 1000"
	case "asset":
		query = "SELECT version,snapshot,recorded_at,false FROM asset_history WHERE shop_id=$1 AND resource_id=$2 ORDER BY version DESC LIMIT 1000"
	default:
		return nil, domain.Invalid("历史资源类型无效。")
	}
	args := []any{shop}
	if kind != "persona" {
		args = append(args, id)
	}
	r, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.HistoryEntry{}
	for r.Next() {
		var p domain.HistoryEntry
		if err = r.Scan(&p.Version, &p.Snapshot, &p.RecordedAt, &p.Deleted); err != nil {
			return nil, dbError(err)
		}
		out = append(out, p)
	}
	if err = r.Err(); err != nil {
		return nil, dbError(err)
	}
	if len(out) == 0 {
		return nil, domain.NotFound()
	}
	return out, nil
}
func historyTarget(list []domain.HistoryEntry, version int64, dst any) error {
	for _, p := range list {
		if p.Version == version {
			if json.Unmarshal(p.Snapshot, dst) != nil {
				return domain.Unavailable("history_invalid", "历史记录无法读取。")
			}
			return nil
		}
	}
	return domain.NotFound()
}
func (s *Store) RestorePersona(ctx context.Context, shop string, expected, target int64) (domain.Persona, error) {
	h, err := s.BusinessHistory(ctx, shop, "persona", shop)
	var p domain.Persona
	if err != nil {
		return p, err
	}
	if err = historyTarget(h, target, &p); err != nil {
		return p, err
	}
	p.ShopID = shop
	p.Version = expected
	return s.SavePersona(ctx, p)
}
func (s *Store) RestoreProduct(ctx context.Context, shop, id string, expected, target int64) (domain.Product, error) {
	h, err := s.BusinessHistory(ctx, shop, "product", id)
	var p domain.Product
	if err != nil {
		return p, err
	}
	if err = historyTarget(h, target, &p); err != nil {
		return p, err
	}
	p.ID = id
	p.ShopID = shop
	p.Version = expected
	return s.SaveProduct(ctx, p, false)
}

func listKnowledgeRecords(ctx context.Context, q querier, shop string) ([]domain.KnowledgeRecord, error) {
	r, err := q.Query(ctx, "SELECT "+knowledgeRecordColumns+" FROM knowledge WHERE shop_id=$1 ORDER BY updated_at DESC,id LIMIT 1000", shop)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.KnowledgeRecord{}
	for r.Next() {
		p, e := scanKnowledgeRecord(r)
		if e != nil {
			return nil, e
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) ListKnowledgeRecords(ctx context.Context, shop string) ([]domain.KnowledgeRecord, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	out, err := listKnowledgeRecords(ctx, s.pool, shop)
	if err != nil {
		return nil, err
	}
	// Legacy DELETE physically removed a row. Keep its final tombstone visible so
	// it can be restored through the same version-checked interface.
	r, err := s.pool.Query(ctx, `SELECT h.snapshot FROM (SELECT DISTINCT ON(resource_id) resource_id,snapshot,deleted,version FROM knowledge_history WHERE shop_id=$1 ORDER BY resource_id,version DESC) h WHERE h.deleted AND NOT EXISTS(SELECT 1 FROM knowledge k WHERE k.id=h.resource_id) LIMIT 1000`, shop)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	for r.Next() {
		var raw []byte
		if err = r.Scan(&raw); err != nil {
			return nil, dbError(err)
		}
		var p domain.KnowledgeRecord
		if json.Unmarshal(raw, &p) != nil {
			return nil, domain.Unavailable("history_invalid", "知识历史无法读取。")
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func checkKnowledgeScope(ctx context.Context, q querier, p domain.KnowledgeRecord) error {
	if p.Scope == "shop" && p.ScopeID == nil {
		return nil
	}
	if p.ScopeID == nil {
		return domain.Invalid("商品或场次范围需要指定资源。")
	}
	query := ""
	switch p.Scope {
	case "product":
		query = "SELECT id::text FROM products WHERE shop_id=$1 AND id=$2"
	case "session":
		query = "SELECT id::text FROM live_sessions WHERE shop_id=$1 AND id=$2"
	default:
		return domain.Invalid("知识范围无效。")
	}
	var id string
	return dbError(q.QueryRow(ctx, query, p.ShopID, *p.ScopeID).Scan(&id))
}
func saveKnowledgeRecord(ctx context.Context, tx pgx.Tx, p domain.KnowledgeRecord, create bool) (domain.KnowledgeRecord, error) {
	if err := checkKnowledgeScope(ctx, tx, p); err != nil {
		return p, err
	}
	var err error
	if create {
		if p.ID == "" {
			p.ID = domain.NewID()
		}
		if p.Version < 1 {
			p.Version = 1
		}
		p, err = scanKnowledgeRecord(tx.QueryRow(ctx, `INSERT INTO knowledge(id,shop_id,title,content,kind,source,scope,scope_id,expires_at,version) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING `+knowledgeRecordColumns, p.ID, p.ShopID, p.Title, p.Content, p.Kind, p.Source, p.Scope, p.ScopeID, p.ExpiresAt, p.Version))
	} else {
		var v int64
		if err = tx.QueryRow(ctx, "SELECT version FROM knowledge WHERE id=$1 AND shop_id=$2 FOR UPDATE", p.ID, p.ShopID).Scan(&v); err != nil {
			return p, dbError(err)
		}
		if v != p.Version {
			return p, staleBusinessVersion()
		}
		p, err = scanKnowledgeRecord(tx.QueryRow(ctx, `UPDATE knowledge SET title=$3,content=$4,kind=$5,source=$6,scope=$7,scope_id=$8,expires_at=$9,deleted_at=NULL WHERE id=$1 AND shop_id=$2 RETURNING `+knowledgeRecordColumns, p.ID, p.ShopID, p.Title, p.Content, p.Kind, p.Source, p.Scope, p.ScopeID, p.ExpiresAt))
	}
	if err != nil {
		return p, err
	}
	if _, err = tx.Exec(ctx, "UPDATE shops SET knowledge_version=knowledge_version+1 WHERE id=$1", p.ShopID); err != nil {
		return p, dbError(err)
	}
	if err = audit(ctx, tx, p.ShopID, p.ID, "knowledge_record_saved", map[string]any{"version": p.Version, "kind": p.Kind, "scope": p.Scope}); err != nil {
		return p, err
	}
	return p, nil
}
func (s *Store) SaveKnowledgeRecord(ctx context.Context, p domain.KnowledgeRecord, create bool) (domain.KnowledgeRecord, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, p.ShopID); err != nil {
		return p, err
	}
	if create {
		p.ID = ""
		p.Version = 1
	}
	p, err = saveKnowledgeRecord(ctx, tx, p, create)
	if err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}
func (s *Store) DeleteKnowledgeRecord(ctx context.Context, shop, id string, expected int64) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, shop); err != nil {
		return err
	}
	var v int64
	var deleted *time.Time
	if err = tx.QueryRow(ctx, "SELECT version,deleted_at FROM knowledge WHERE shop_id=$1 AND id=$2 FOR UPDATE", shop, id).Scan(&v, &deleted); err != nil {
		return dbError(err)
	}
	if v != expected {
		return staleBusinessVersion()
	}
	if deleted != nil {
		return domain.Conflict("already_deleted", "知识已删除，请通过历史恢复。")
	}
	if _, err = tx.Exec(ctx, "UPDATE knowledge SET deleted_at=now() WHERE shop_id=$1 AND id=$2", shop, id); err != nil {
		return dbError(err)
	}
	if _, err = tx.Exec(ctx, "UPDATE shops SET knowledge_version=knowledge_version+1 WHERE id=$1", shop); err != nil {
		return dbError(err)
	}
	if err = audit(ctx, tx, shop, id, "knowledge_record_deleted", map[string]any{"version": v + 1}); err != nil {
		return err
	}
	return dbError(tx.Commit(ctx))
}
func (s *Store) RestoreKnowledgeRecord(ctx context.Context, shop, id string, expected, target int64) (domain.KnowledgeRecord, error) {
	tx, err := s.pool.Begin(ctx)
	var p domain.KnowledgeRecord
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, shop); err != nil {
		return p, err
	}
	var raw []byte
	if err = tx.QueryRow(ctx, "SELECT snapshot FROM knowledge_history WHERE shop_id=$1 AND resource_id=$2 AND version=$3", shop, id, target).Scan(&raw); err != nil {
		return p, dbError(err)
	}
	if json.Unmarshal(raw, &p) != nil {
		return p, domain.Unavailable("history_invalid", "知识历史无法读取。")
	}
	var current int64
	err = tx.QueryRow(ctx, "SELECT version FROM knowledge WHERE shop_id=$1 AND id=$2 FOR UPDATE", shop, id).Scan(&current)
	create := errors.Is(err, pgx.ErrNoRows)
	if create {
		err = tx.QueryRow(ctx, "SELECT max(version) FROM knowledge_history WHERE shop_id=$1 AND resource_id=$2", shop, id).Scan(&current)
	}
	if err != nil {
		return p, dbError(err)
	}
	if current != expected {
		return p, staleBusinessVersion()
	}
	p.ID = id
	p.ShopID = shop
	p.Version = expected
	p.DeletedAt = nil
	if create {
		p.Version++
	}
	p, err = saveKnowledgeRecord(ctx, tx, p, create)
	if err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) ListAssets(ctx context.Context, shop string) ([]domain.Asset, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	return listAssets(ctx, s.pool, shop)
}
func listAssets(ctx context.Context, q querier, shop string) ([]domain.Asset, error) {
	r, err := q.Query(ctx, "SELECT "+assetColumns+" FROM assets WHERE shop_id=$1 ORDER BY updated_at DESC,id LIMIT 1000", shop)
	if err != nil {
		return nil, dbError(err)
	}
	defer r.Close()
	out := []domain.Asset{}
	for r.Next() {
		p, e := scanAsset(r)
		if e != nil {
			return nil, e
		}
		out = append(out, p)
	}
	return out, dbError(r.Err())
}
func (s *Store) SaveAsset(ctx context.Context, p domain.Asset, create bool) (domain.Asset, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, p.ShopID); err != nil {
		return p, err
	}
	if !create {
		var v int64
		if err = tx.QueryRow(ctx, "SELECT version FROM assets WHERE shop_id=$1 AND id=$2 FOR UPDATE", p.ShopID, p.ID).Scan(&v); err != nil {
			return p, dbError(err)
		}
		if v != p.Version {
			return p, staleBusinessVersion()
		}
	}
	if p.Active {
		r, e := tx.Query(ctx, "UPDATE assets SET active=false,version=version+1,updated_at=now() WHERE shop_id=$1 AND kind=$2 AND active AND id::text<>$3 RETURNING "+assetColumns, p.ShopID, p.Kind, p.ID)
		if e != nil {
			return p, dbError(e)
		}
		old := []domain.Asset{}
		for r.Next() {
			v, e := scanAsset(r)
			if e != nil {
				r.Close()
				return p, e
			}
			old = append(old, v)
		}
		err = r.Err()
		r.Close()
		if err != nil {
			return p, dbError(err)
		}
		for _, v := range old {
			if err = archiveBusiness(ctx, tx, "asset_history", v.ShopID, v.ID, v.Version, v); err != nil {
				return p, err
			}
		}
	}
	if create {
		p.ID = domain.NewID()
		p, err = scanAsset(tx.QueryRow(ctx, `INSERT INTO assets(id,shop_id,kind,name,identifier,sha256,model_version,authorized,active) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING `+assetColumns, p.ID, p.ShopID, p.Kind, p.Name, p.Identifier, p.SHA256, p.ModelVersion, p.Authorized, p.Active))
	} else {
		p, err = scanAsset(tx.QueryRow(ctx, `UPDATE assets SET kind=$3,name=$4,identifier=$5,sha256=$6,model_version=$7,authorized=$8,active=$9,version=version+1,updated_at=now() WHERE id=$1 AND shop_id=$2 RETURNING `+assetColumns, p.ID, p.ShopID, p.Kind, p.Name, p.Identifier, p.SHA256, p.ModelVersion, p.Authorized, p.Active))
	}
	if err != nil {
		return p, err
	}
	if err = archiveBusiness(ctx, tx, "asset_history", p.ShopID, p.ID, p.Version, p); err != nil {
		return p, err
	}
	if err = audit(ctx, tx, p.ShopID, p.ID, "asset_saved", map[string]any{"version": p.Version, "kind": p.Kind, "active": p.Active}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

// Called while the core snapshot holds the shop FOR SHARE lock. All extension
// mutations take that row FOR UPDATE, so one coherent effective set is read.
func loadBusinessSnapshot(ctx context.Context, tx pgx.Tx, s *domain.Snapshot, now time.Time) error {
	b := domain.BusinessSnapshot{}
	limitError := func() error {
		return domain.Conflict("business_context_limit", "当前范围内有效活动或知识超过1000条，请缩小范围或停用无关记录后再生成。")
	}
	rows, err := tx.Query(ctx, "SELECT "+promotionColumns+" FROM promotions WHERE shop_id=$1 AND active AND (product_id IS NULL OR product_id=$2) AND ends_at>$3 ORDER BY id LIMIT 1001", s.Shop.ID, s.Product.ID, now)
	if err != nil {
		return dbError(err)
	}
	count := 0
	for rows.Next() {
		p, e := scanPromotion(rows)
		if e != nil {
			rows.Close()
			return e
		}
		count++
		if count > 1000 {
			rows.Close()
			return limitError()
		}
		if now.Before(p.StartsAt) {
			b.Boundary(&p.StartsAt, now)
			continue
		}
		b.Promotions = append(b.Promotions, p)
		b.Boundary(&p.EndsAt, now)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return dbError(err)
	}
	rows, err = tx.Query(ctx, "SELECT "+assetColumns+" FROM assets WHERE shop_id=$1 AND active ORDER BY id", s.Shop.ID)
	if err != nil {
		return dbError(err)
	}
	for rows.Next() {
		p, e := scanAsset(rows)
		if e != nil {
			rows.Close()
			return e
		}
		b.Assets = append(b.Assets, p)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return dbError(err)
	}
	rows, err = tx.Query(ctx, "SELECT "+knowledgeRecordColumns+" FROM knowledge WHERE shop_id=$1 AND deleted_at IS NULL AND (expires_at IS NULL OR expires_at>$4) AND (scope='shop' OR (scope='product' AND scope_id=$2) OR (scope='session' AND scope_id=$3)) ORDER BY id LIMIT 1001", s.Shop.ID, s.Product.ID, s.Session.ID, now)
	if err != nil {
		return dbError(err)
	}
	s.Knowledge = []domain.Knowledge{}
	count = 0
	for rows.Next() {
		k, e := scanKnowledgeRecord(rows)
		if e != nil {
			rows.Close()
			return e
		}
		count++
		if count > 1000 {
			rows.Close()
			return limitError()
		}
		s.Knowledge = append(s.Knowledge, k.Knowledge)
		b.KnowledgeRefs = append(b.KnowledgeRefs, domain.KnowledgeRef{ID: k.ID, Version: k.Version, ExpiresAt: k.ExpiresAt})
		b.Boundary(k.ExpiresAt, now)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return dbError(err)
	}
	b.Seal()
	s.Business = b
	return nil
}

const costSettingColumns = `shop_id::text,input_cny_per_million::float8,output_cny_per_million::float8,electricity_cny_per_kwh::float8,device_watts::float8,monthly_budget_cny::float8,notes,version,updated_at`

func scanCostSettings(r scanner) (p domain.CostSettings, err error) {
	err = r.Scan(&p.ShopID, &p.InputCNYPerMillion, &p.OutputCNYPerMillion, &p.ElectricityCNYPerKWH, &p.DeviceWatts, &p.MonthlyBudgetCNY, &p.Notes, &p.Version, &p.UpdatedAt)
	return p, err
}
func (s *Store) GetCostSettings(ctx context.Context, shop string) (domain.CostSettings, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return domain.CostSettings{}, err
	}
	p, err := scanCostSettings(s.pool.QueryRow(ctx, "SELECT "+costSettingColumns+" FROM cost_settings WHERE shop_id=$1", shop))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.CostSettings{ShopID: shop}, nil
	}
	return p, dbError(err)
}
func (s *Store) SaveCostSettings(ctx context.Context, p domain.CostSettings) (domain.CostSettings, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return p, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = lockBusinessShop(ctx, tx, p.ShopID); err != nil {
		return p, err
	}
	var current int64
	err = tx.QueryRow(ctx, "SELECT version FROM cost_settings WHERE shop_id=$1", p.ShopID).Scan(&current)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return p, dbError(err)
	}
	if current != p.Version {
		return p, staleBusinessVersion()
	}
	p, err = scanCostSettings(tx.QueryRow(ctx, `INSERT INTO cost_settings(shop_id,input_cny_per_million,output_cny_per_million,electricity_cny_per_kwh,device_watts,monthly_budget_cny,notes) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(shop_id) DO UPDATE SET input_cny_per_million=EXCLUDED.input_cny_per_million,output_cny_per_million=EXCLUDED.output_cny_per_million,electricity_cny_per_kwh=EXCLUDED.electricity_cny_per_kwh,device_watts=EXCLUDED.device_watts,monthly_budget_cny=EXCLUDED.monthly_budget_cny,notes=EXCLUDED.notes,version=cost_settings.version+1,updated_at=now() RETURNING `+costSettingColumns, p.ShopID, p.InputCNYPerMillion, p.OutputCNYPerMillion, p.ElectricityCNYPerKWH, p.DeviceWatts, p.MonthlyBudgetCNY, p.Notes))
	if err != nil {
		return p, dbError(err)
	}
	if err = audit(ctx, tx, p.ShopID, p.ShopID, "cost_settings_saved", map[string]any{"version": p.Version}); err != nil {
		return p, err
	}
	return p, dbError(tx.Commit(ctx))
}

func (s *Store) StartUsage(ctx context.Context, shop, session, model string) (domain.UsageEvent, error) {
	p := domain.UsageEvent{ID: domain.NewID(), ShopID: shop, SessionID: session, Model: model, Status: "pending"}
	if !domain.TextWithin(model, 1, 120) {
		return p, domain.Invalid("模型名称无效。")
	}
	err := s.pool.QueryRow(ctx, "INSERT INTO usage_events(id,shop_id,session_id,model) VALUES($1,$2,$3,$4) RETURNING created_at,updated_at", p.ID, shop, session, model).Scan(&p.CreatedAt, &p.UpdatedAt)
	return p, dbError(err)
}

// An attempt is recorded before the request. Cancellation, process restart or an
// unreadable provider response remain unknown; never claim they were unbilled.
func (s *Store) FinishUsage(ctx context.Context, shop, id, status string, input, output int64, jobID *string, errorCode string) error {
	if (status != "complete" && status != "unknown") || input < 0 || output < 0 || input > 1000000000 || output > 1000000000 || !domain.TextWithin(errorCode, 0, 120) {
		return domain.Invalid("用量记录无效。")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return dbError(err)
	}
	defer tx.Rollback(ctx)
	var session string
	if err = tx.QueryRow(ctx, "SELECT session_id::text FROM usage_events WHERE shop_id=$1 AND id=$2 FOR UPDATE", shop, id).Scan(&session); err != nil {
		return dbError(err)
	}
	if jobID != nil {
		var owner string
		if err = tx.QueryRow(ctx, "SELECT id::text FROM speech_jobs WHERE id=$1 AND shop_id=$2 AND session_id=$3", *jobID, shop, session).Scan(&owner); err != nil {
			return dbError(err)
		}
	}
	tag, err := tx.Exec(ctx, "UPDATE usage_events SET status=$3,input_tokens=$4,output_tokens=$5,job_id=$6,error_code=$7,updated_at=now() WHERE shop_id=$1 AND id=$2 AND status='pending'", shop, id, status, input, output, jobID, errorCode)
	if err != nil {
		return dbError(err)
	}
	if tag.RowsAffected() == 0 {
		return domain.Conflict("usage_finalized", "用量事件已结算或不存在，不能重写。")
	}
	return dbError(tx.Commit(ctx))
}
func (s *Store) CostSummary(ctx context.Context, shop, session string) (domain.CostSummary, error) {
	p := domain.CostSummary{ShopID: shop, SessionID: session, Currency: "CNY", Basis: "operator_entered_rates", Note: "按操作者录入费率估算。未知用量可能已经计费；不含维修、人工、税费与平台费用。电费基于额定功率，非硬件实测。"}
	settings, err := s.GetCostSettings(ctx, shop)
	if err != nil {
		return p, err
	}
	p.Settings = settings
	if session != "" {
		if _, err = s.GetSession(ctx, shop, session); err != nil {
			return p, err
		}
	}
	// Historical v0.1 jobs have no attempt ledger. Include them exactly once;
	// new attempts also retain usage when no job could be persisted.
	err = s.pool.QueryRow(ctx, `SELECT COALESCE(sum(input_tokens),0),COALESCE(sum(output_tokens),0),count(*) FROM speech_jobs j WHERE shop_id=$1 AND ($2='' OR session_id::text=$2) AND source='deepseek' AND NOT EXISTS(SELECT 1 FROM usage_events u WHERE u.job_id=j.id)`, shop, session).Scan(&p.InputTokens, &p.OutputTokens, &p.GeneratedJobs)
	if err != nil {
		return p, dbError(err)
	}
	var in, out, events, unknown, linked int64
	err = s.pool.QueryRow(ctx, `SELECT COALESCE(sum(input_tokens),0),COALESCE(sum(output_tokens),0),count(*),count(*) FILTER(WHERE status<>'complete'),count(job_id) FROM usage_events WHERE shop_id=$1 AND ($2='' OR session_id::text=$2)`, shop, session).Scan(&in, &out, &events, &unknown, &linked)
	if err != nil {
		return p, dbError(err)
	}
	p.InputTokens += in
	p.OutputTokens += out
	p.UsageEvents = events
	p.UnknownUsageEvents = unknown
	p.GeneratedJobs += linked
	if settings.InputCNYPerMillion != nil && settings.OutputCNYPerMillion != nil {
		v := (float64(p.InputTokens)**settings.InputCNYPerMillion + float64(p.OutputTokens)**settings.OutputCNYPerMillion) / 1000000
		p.EstimatedAICNY = &v
	}
	if settings.ElectricityCNYPerKWH != nil && settings.DeviceWatts != nil {
		v := *settings.ElectricityCNYPerKWH * *settings.DeviceWatts / 1000
		p.EstimatedPowerCNYPerHour = &v
	}
	return p, nil
}

// Read-only inspection of the effective facts used in the next job.
func (s *Store) BusinessSnapshot(ctx context.Context, shop, session, product string) (domain.BusinessSnapshot, error) {
	snap, err := s.Snapshot(ctx, shop, session, product)
	return snap.Business, err
}
