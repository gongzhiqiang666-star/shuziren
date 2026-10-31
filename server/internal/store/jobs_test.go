package store_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
)

func fixture(t *testing.T, s *store.Store) (domain.Shop, domain.Product, domain.Session) {
	t.Helper()
	ctx := context.Background()
	shop, e := s.CreateShop(ctx, "集成测试店")
	if e != nil {
		t.Fatal(e)
	}
	p, e := s.SaveProduct(ctx, domain.Product{ShopID: shop.ID, Title: "保温杯", SKU: domain.NewID(), PriceCents: 9900, Stock: 10, Active: true}, true)
	if e != nil {
		t.Fatal(e)
	}
	session, e := s.CreateSession(ctx, shop.ID, "本地场次")
	if e != nil {
		t.Fatal(e)
	}
	return shop, p, session
}
func draft(t *testing.T, s *store.Store, shop domain.Shop, p domain.Product, session domain.Session) domain.Job {
	t.Helper()
	snap, e := s.Snapshot(context.Background(), shop.ID, session.ID, p.ID)
	if e != nil {
		t.Fatal(e)
	}
	j, e := s.CreateJob(context.Background(), snap, domain.Job{Source: "manual", Status: "draft", Text: "这款保温杯99元。"})
	if e != nil {
		t.Fatal(e)
	}
	return j
}
func wantCode(t *testing.T, err error, code string) {
	t.Helper()
	var e *domain.Error
	if !errors.As(err, &e) || e.Code != code {
		t.Fatalf("want error %s, got %v", code, err)
	}
}

func TestPostgresOwnershipVersionsAndKnowledge(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	other, _, _ := fixture(t, s)
	if _, err := s.GetSession(ctx, other.ID, session.ID); err == nil {
		t.Fatal("cross-shop session exposed")
	}
	if _, err := s.Snapshot(ctx, other.ID, session.ID, p.ID); err == nil {
		t.Fatal("cross-shop snapshot exposed")
	}
	j := draft(t, s, shop, p, session)
	p.PriceCents = 10900
	next, err := s.SaveProduct(ctx, p, false)
	if err != nil || next.Version != 2 {
		t.Fatalf("version update failed: %v", err)
	}
	_, err = s.SaveProduct(ctx, p, false)
	wantCode(t, err, "stale_version")
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_product")
	j = draft(t, s, shop, next, session)
	persona, err := s.GetPersona(ctx, shop.ID)
	if err != nil {
		t.Fatal(err)
	}
	persona.Tone = "温和"
	if _, err = s.SavePersona(ctx, persona); err != nil {
		t.Fatal(err)
	}
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_persona")
	j = draft(t, s, shop, next, session)
	k, err := s.SaveKnowledge(ctx, domain.Knowledge{ShopID: shop.ID, Title: "清洁", Content: "温水清洁", Kind: "faq"}, true)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_knowledge")
	if err = s.DeleteKnowledge(ctx, other.ID, k.ID); err == nil {
		t.Fatal("cross-shop delete succeeded")
	}
	q, err := s.GetQuality(ctx, shop.ID)
	if err != nil || !q.UpdatedAt.IsZero() {
		t.Fatal("unsaved quality timestamp should be zero")
	}
	for _, c := range q.Checks {
		if c.Passed {
			t.Fatal("unmeasured check marked passed")
		}
	}
}

func TestPostgresSynthesisRevalidatesAndTakeoverCancels(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	j := draft(t, s, shop, p, session)
	if _, err := s.QueueSynthesis(ctx, shop.ID, j.ID); err == nil {
		t.Fatal("unapproved job queued")
	}
	if _, err := s.Approve(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.QueueSynthesis(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	claimed, err := s.ClaimNext(ctx)
	if err != nil || claimed.ID != j.ID || claimed.Status != "synthesizing" {
		t.Fatalf("claim failed: %v", err)
	}
	p.PriceCents++
	p, err = s.SaveProduct(ctx, p, false)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.FinishSynthesis(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_product")
	j, err = s.GetJob(ctx, shop.ID, j.ID)
	if err != nil || j.Status != "cancelled" || j.AudioReady {
		t.Fatal("late audio became usable")
	}
	j = draft(t, s, shop, p, session)
	if _, err = s.Approve(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.QueueSynthesis(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	paused, err := s.ChangeSession(ctx, shop.ID, session.ID, "takeover")
	if err != nil || paused.Epoch != session.Epoch+1 || paused.Status != "paused" {
		t.Fatalf("takeover failed: %v", err)
	}
	if _, err = s.ClaimNext(ctx); !errors.Is(err, store.ErrNoWork) {
		t.Fatal("cancelled job re-entered queue")
	}
	if _, err = s.ChangeSession(ctx, shop.ID, session.ID, "resume"); err != nil {
		t.Fatal(err)
	}
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_epoch")
}

func TestPostgresRecoveryAndAmbiguousDeliveryCannotReplay(t *testing.T) {
	s, db := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	if _, err := s.BindMedia(ctx, shop.ID, session.ID, session.Epoch, "test-media-session"); err != nil {
		t.Fatal(err)
	}
	ready := draft(t, s, shop, p, session)
	if _, err := s.Approve(ctx, shop.ID, ready.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.QueueSynthesis(ctx, shop.ID, ready.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.ClaimNext(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := s.FinishSynthesis(ctx, shop.ID, ready.ID); err != nil {
		t.Fatal(err)
	}
	if _, _, err := s.StartSend(ctx, shop.ID, ready.ID); err != nil {
		t.Fatal(err)
	}
	synth := draft(t, s, shop, p, session)
	if _, err := s.Approve(ctx, shop.ID, synth.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.QueueSynthesis(ctx, shop.ID, synth.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.ClaimNext(ctx); err != nil {
		t.Fatal(err)
	}
	if err := s.Recover(ctx); err != nil {
		t.Fatal(err)
	}
	ready, err := s.GetJob(ctx, shop.ID, ready.ID)
	if err != nil || ready.Status != "delivery_unknown" {
		t.Fatal("sending was incorrectly replayable after restart")
	}
	if _, err = s.QueueSynthesis(ctx, shop.ID, ready.ID); err == nil {
		t.Fatal("ambiguous delivery requeued")
	}
	if _, _, err = s.StartSend(ctx, shop.ID, ready.ID); err == nil {
		t.Fatal("ambiguous delivery resent")
	}
	synth, err = s.GetJob(ctx, shop.ID, synth.ID)
	if err != nil || synth.Status != "failed" {
		t.Fatal("interrupted synthesis must require explicit retry")
	}
	if _, err = s.QueueSynthesis(ctx, shop.ID, synth.ID); err != nil {
		t.Fatal("explicit synthesis retry failed")
	}
	var count int
	if err = db.QueryRow(ctx, "SELECT count(*) FROM audit_events WHERE event='job_approved'").Scan(&count); err != nil || count != 2 {
		t.Fatal("approval audit missing")
	}
	// A second independent connection cannot obtain the backend's session lock.
	var held bool
	if err = db.QueryRow(ctx, "SELECT pg_try_advisory_lock($1)", int64(837462019305)).Scan(&held); err != nil || held {
		t.Fatal("instance lock was not pinned to a dedicated connection")
	}
	if err = s.CheckInstance(ctx); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresGenerationCompletionRejectsEditedContext(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	snap, err := s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	if err != nil {
		t.Fatal(err)
	}
	expires := time.Now().Add(-time.Second)
	p.ExpiresAt = &expires
	if _, err = s.SaveProduct(ctx, p, false); err != nil {
		t.Fatal(err)
	}
	_, err = s.CreateJob(ctx, snap, domain.Job{Source: "deepseek", Text: "迟到回复", Status: "draft"})
	wantCode(t, err, "product_expired")
	jobs, err := s.ListJobs(ctx, shop.ID, session.ID)
	if err != nil || len(jobs) != 0 {
		t.Fatal("stale generated job was persisted")
	}
}
