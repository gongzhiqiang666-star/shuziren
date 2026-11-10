package store

import (
	"context"
	"encoding/json"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

const readinessRunColumns = `id::text,shop_id::text,title,output_mode,conclusion,version,created_at,updated_at`

func scanReadinessRun(row scanner) (r domain.LiveReadinessRun, err error) {
	err = row.Scan(&r.ID, &r.ShopID, &r.Title, &r.OutputMode, &r.Conclusion, &r.Version, &r.CreatedAt, &r.UpdatedAt)
	return r, dbError(err)
}

func readinessGates(ctx context.Context, q querier, run string) ([]domain.LiveReadinessGate, error) {
	rows, err := q.Query(ctx, `SELECT name,status,evidence,note,version,updated_at FROM live_readiness_gates WHERE run_id=$1 ORDER BY CASE name WHEN 'install' THEN 1 WHEN 'generation' THEN 2 WHEN 'obs' THEN 3 WHEN 'platform' THEN 4 ELSE 5 END`, run)
	if err != nil {
		return nil, dbError(err)
	}
	defer rows.Close()
	out := []domain.LiveReadinessGate{}
	for rows.Next() {
		var g domain.LiveReadinessGate
		var raw []byte
		if err = rows.Scan(&g.Name, &g.Status, &raw, &g.Note, &g.Version, &g.UpdatedAt); err != nil {
			return nil, dbError(err)
		}
		if json.Unmarshal(raw, &g.Evidence) != nil {
			return nil, domain.Unavailable("readiness_invalid", "验证记录无法读取。")
		}
		out = append(out, g)
	}
	return out, dbError(rows.Err())
}

func readinessRun(ctx context.Context, q querier, shop, id string) (domain.LiveReadinessRun, error) {
	r, err := scanReadinessRun(q.QueryRow(ctx, `SELECT `+readinessRunColumns+` FROM live_readiness_runs WHERE shop_id=$1 AND id=$2`, shop, id))
	if err != nil {
		return r, err
	}
	r.Gates, err = readinessGates(ctx, q, r.ID)
	return r, err
}

func (s *Store) CreateLiveReadinessRun(ctx context.Context, shop, title, mode string) (domain.LiveReadinessRun, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.LiveReadinessRun{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	if err = requireShop(ctx, tx, shop); err != nil {
		return domain.LiveReadinessRun{}, err
	}
	id := domain.NewID()
	if _, err = tx.Exec(ctx, `INSERT INTO live_readiness_runs(id,shop_id,title,output_mode) VALUES($1,$2,$3,$4)`, id, shop, title, mode); err != nil {
		return domain.LiveReadinessRun{}, dbError(err)
	}
	for _, gate := range domain.DefaultLiveReadinessGates() {
		raw, _ := json.Marshal(gate.Evidence)
		if _, err = tx.Exec(ctx, `INSERT INTO live_readiness_gates(run_id,name,status,evidence,note) VALUES($1,$2,$3,$4,$5)`, id, gate.Name, gate.Status, raw, gate.Note); err != nil {
			return domain.LiveReadinessRun{}, dbError(err)
		}
	}
	r, err := readinessRun(ctx, tx, shop, id)
	if err != nil {
		return r, err
	}
	if err = tx.Commit(ctx); err != nil {
		return r, dbError(err)
	}
	return r, nil
}

func (s *Store) ListLiveReadinessRuns(ctx context.Context, shop string) ([]domain.LiveReadinessRun, error) {
	if err := requireShop(ctx, s.pool, shop); err != nil {
		return nil, err
	}
	rows, err := s.pool.Query(ctx, `SELECT `+readinessRunColumns+` FROM live_readiness_runs WHERE shop_id=$1 ORDER BY updated_at DESC,id LIMIT 100`, shop)
	if err != nil {
		return nil, dbError(err)
	}
	defer rows.Close()
	out := []domain.LiveReadinessRun{}
	for rows.Next() {
		r, e := scanReadinessRun(rows)
		if e != nil {
			return nil, e
		}
		r.Gates, e = readinessGates(ctx, s.pool, r.ID)
		if e != nil {
			return nil, e
		}
		out = append(out, r)
	}
	return out, dbError(rows.Err())
}

func (s *Store) GetLiveReadinessRun(ctx context.Context, shop, id string) (domain.LiveReadinessRun, error) {
	return readinessRun(ctx, s.pool, shop, id)
}

func (s *Store) UpdateLiveReadinessGate(ctx context.Context, shop, id string, expected int64, gate domain.LiveReadinessGate) (domain.LiveReadinessRun, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.LiveReadinessRun{}, dbError(err)
	}
	defer tx.Rollback(ctx)
	var current int64
	if err = tx.QueryRow(ctx, `SELECT version FROM live_readiness_runs WHERE shop_id=$1 AND id=$2 FOR UPDATE`, shop, id).Scan(&current); err != nil {
		return domain.LiveReadinessRun{}, dbError(err)
	}
	if current != expected {
		return domain.LiveReadinessRun{}, domain.Conflict("stale_version", "验证记录已被修改，请刷新后重试。")
	}
	raw, _ := json.Marshal(gate.Evidence)
	if tag, e := tx.Exec(ctx, `UPDATE live_readiness_gates SET status=$4,evidence=$5,note=$6,version=version+1,updated_at=now() WHERE run_id=$1 AND name=$2 AND EXISTS(SELECT 1 FROM live_readiness_runs WHERE id=$1 AND shop_id=$3)`, id, gate.Name, shop, gate.Status, raw, gate.Note); e != nil || tag.RowsAffected() != 1 {
		if e != nil {
			return domain.LiveReadinessRun{}, dbError(e)
		}
		return domain.LiveReadinessRun{}, domain.NotFound()
	}
	gates, err := readinessGates(ctx, tx, id)
	if err != nil {
		return domain.LiveReadinessRun{}, err
	}
	conclusion := domain.LiveReadinessConclusion(gates)
	if _, err = tx.Exec(ctx, `UPDATE live_readiness_runs SET conclusion=$3,version=version+1,updated_at=now() WHERE id=$1 AND shop_id=$2`, id, shop, conclusion); err != nil {
		return domain.LiveReadinessRun{}, dbError(err)
	}
	r, err := readinessRun(ctx, tx, shop, id)
	if err != nil {
		return r, err
	}
	if err = tx.Commit(ctx); err != nil {
		return r, dbError(err)
	}
	return r, nil
}
