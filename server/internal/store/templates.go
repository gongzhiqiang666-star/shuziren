package store

import (
	"context"
	"errors"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

const templateColumns = `id::text,shop_id::text,name,body,version,updated_at`

func scanTemplate(r scanner) (domain.SpeechTemplate, error) {
	var p domain.SpeechTemplate
	e := r.Scan(&p.ID, &p.ShopID, &p.Name, &p.Body, &p.Version, &p.UpdatedAt)
	return p, dbError(e)
}
func (s *Store) ListTemplates(ctx context.Context, shop string) ([]domain.SpeechTemplate, error) {
	if e := requireShop(ctx, s.pool, shop); e != nil {
		return nil, e
	}
	rows, e := s.pool.Query(ctx, "SELECT "+templateColumns+" FROM speech_templates WHERE shop_id=$1 ORDER BY updated_at DESC LIMIT 1000", shop)
	if e != nil {
		return nil, dbError(e)
	}
	defer rows.Close()
	out := []domain.SpeechTemplate{}
	for rows.Next() {
		p, e := scanTemplate(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, p)
	}
	return out, dbError(rows.Err())
}
func (s *Store) GetTemplate(ctx context.Context, shop, id string) (domain.SpeechTemplate, error) {
	return scanTemplate(s.pool.QueryRow(ctx, "SELECT "+templateColumns+" FROM speech_templates WHERE id=$1 AND shop_id=$2", id, shop))
}
func (s *Store) SaveTemplate(ctx context.Context, p domain.SpeechTemplate, create bool) (domain.SpeechTemplate, error) {
	if !domain.TextWithin(p.Name, 1, 120) {
		return p, domain.Invalid("模板名称应为1至120字。")
	}
	if e := domain.ValidateTemplate(p.Body); e != nil {
		return p, e
	}
	if create {
		p.ID = domain.NewID()
		return scanTemplate(s.pool.QueryRow(ctx, "INSERT INTO speech_templates(id,shop_id,name,body) VALUES($1,$2,$3,$4) RETURNING "+templateColumns, p.ID, p.ShopID, p.Name, p.Body))
	}
	if _, e := s.GetTemplate(ctx, p.ShopID, p.ID); e != nil {
		return p, e
	}
	result, e := scanTemplate(s.pool.QueryRow(ctx, "UPDATE speech_templates SET name=$3,body=$4,version=version+1,updated_at=now() WHERE id=$1 AND shop_id=$2 AND version=$5 RETURNING "+templateColumns, p.ID, p.ShopID, p.Name, p.Body, p.Version))
	if e != nil {
		var de *domain.Error
		if errors.As(e, &de) && de.Code == "not_found" {
			return p, domain.Conflict("stale_template", "模板已被修改，请刷新后再保存。")
		}
		return p, e
	}
	return result, nil
}
func (s *Store) DeleteTemplate(ctx context.Context, shop, id string, version int64) error {
	if _, e := s.GetTemplate(ctx, shop, id); e != nil {
		return e
	}
	tag, e := s.pool.Exec(ctx, "DELETE FROM speech_templates WHERE id=$1 AND shop_id=$2 AND version=$3", id, shop, version)
	if e != nil {
		return dbError(e)
	}
	if tag.RowsAffected() != 1 {
		return domain.Conflict("stale_template", "模板已改变，请刷新后再删除。")
	}
	return nil
}
