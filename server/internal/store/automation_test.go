package store_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
)

func TestPostgresQuotaReservesBeforeCallsAndKeepsUnknown(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, _, session := fixture(t, s)
	l, err := s.SaveGenerationLimits(ctx, domain.GenerationLimits{ShopID: shop.ID, RequestsPerMinute: 10, DailyTokenLimit: 100000})
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	results := make(chan domain.UsageEvent, 2)
	errs := make(chan error, 2)
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			u, e := s.StartLimitedUsage(ctx, shop.ID, session.ID, "test-model", 100000)
			results <- u
			errs <- e
		}()
	}
	wg.Wait()
	close(results)
	close(errs)
	good := 0
	for e := range errs {
		if e == nil {
			good++
		} else {
			wantCode(t, e, "generation_budget_exceeded")
		}
	}
	if good != 1 {
		t.Fatal("concurrent reservations exceeded daily budget")
	}
	u, err := s.GenerationUsage(ctx, shop.ID)
	if err != nil || u.RequestsToday != 1 || u.ChargedTokensToday != 100000 || u.PendingRequestsToday != 1 {
		t.Fatalf("missing pre-call reservation: %+v %v", u, err)
	}
	if err = s.Recover(ctx); err != nil {
		t.Fatal(err)
	}
	u, err = s.GenerationUsage(ctx, shop.ID)
	if err != nil || u.UnknownRequestsToday != 1 || u.ChargedTokensToday != 100000 {
		t.Fatal("restart freed unknown remote usage")
	}
	if _, err = s.StartLimitedUsage(ctx, shop.ID, session.ID, "test-model", 100000); err == nil {
		t.Fatal("unknown reservation allowed another billed call")
	}
	l.DailyTokenLimit = 200000
	if _, err = s.SaveGenerationLimits(ctx, l); err != nil {
		t.Fatal(err)
	}
	event, err := s.StartLimitedUsage(ctx, shop.ID, session.ID, "test-model", 100000)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.FinishUsage(ctx, shop.ID, event.ID, "complete", 12, 8, nil, "model_invalid_answer"); err != nil {
		t.Fatal(err)
	}
	u, err = s.GenerationUsage(ctx, shop.ID)
	if err != nil || u.ChargedTokensToday != 100020 || u.UnknownRequestsToday != 1 || u.RequestsToday != 2 {
		t.Fatal("trusted usage did not settle reservation accurately")
	}
}

func TestPostgresTTSUsesPriorityAndExpiredJobCannotRevive(t *testing.T) {
	s, db := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	low := draft(t, s, shop, p, session)
	high := draft(t, s, shop, p, session)
	for _, j := range []domain.Job{low, high} {
		if _, err := s.Approve(ctx, shop.ID, j.ID); err != nil {
			t.Fatal(err)
		}
		if _, err := s.QueueSynthesis(ctx, shop.ID, j.ID); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := s.SetDispatchPolicy(ctx, shop.ID, low.ID, 10, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := s.SetDispatchPolicy(ctx, shop.ID, high.ID, 90, nil); err != nil {
		t.Fatal(err)
	}
	claimed, err := s.ClaimNext(ctx)
	if err != nil || claimed.ID != high.ID {
		t.Fatal("priority did not affect serial TTS claim")
	}
	if _, err = db.Exec(ctx, "UPDATE speech_jobs SET expires_at=now()-interval '1 second' WHERE id=$1", low.ID); err != nil {
		t.Fatal(err)
	}
	_, err = s.Approve(ctx, shop.ID, low.ID)
	wantCode(t, err, "job_expired")
	future := time.Now().Add(time.Hour)
	_, err = s.SetDispatchPolicy(ctx, shop.ID, low.ID, 99, &future)
	wantCode(t, err, "job_expired")
	if _, err = s.ClaimNext(ctx); !errors.Is(err, store.ErrNoWork) {
		t.Fatal("expired task entered TTS")
	}
	low, err = s.GetJob(ctx, shop.ID, low.ID)
	if err != nil || low.Status != "cancelled" {
		t.Fatal("expired queue item did not become unusable")
	}
}

func TestPostgresSchedulesRequireApprovalAndNeverCatchUpAfterRestart(t *testing.T) {
	s, db := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	run := time.Now().Add(time.Hour)
	expires := run.Add(time.Minute)
	j := draft(t, s, shop, p, session)
	if _, err := s.CreateSchedule(ctx, shop.ID, j.ID, run, expires); err == nil {
		t.Fatal("unapproved text scheduled")
	}
	create := func() domain.SpeechSchedule {
		j := draft(t, s, shop, p, session)
		if _, err := s.Approve(ctx, shop.ID, j.ID); err != nil {
			t.Fatal(err)
		}
		sc, err := s.CreateSchedule(ctx, shop.ID, j.ID, run, expires)
		if err != nil {
			t.Fatal(err)
		}
		return sc
	}
	future, past, inflight := create(), create(), create()
	if _, err := db.Exec(ctx, "UPDATE speech_schedules SET run_at=now()-interval '5 seconds',expires_at=now()+interval '1 minute' WHERE id=$1", past.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, "UPDATE speech_schedules SET status='dispatching' WHERE id=$1", inflight.ID); err != nil {
		t.Fatal(err)
	}
	if err := s.Recover(ctx); err != nil {
		t.Fatal(err)
	}
	schedules, err := s.ListSchedules(ctx, shop.ID, session.ID)
	if err != nil {
		t.Fatal(err)
	}
	states := map[string]string{}
	for _, p := range schedules {
		states[p.ID] = p.Status
	}
	if states[future.ID] != "scheduled" || states[past.ID] != "failed" || states[inflight.ID] != "delivery_unknown" {
		t.Fatalf("unsafe restart schedules: %#v", states)
	}
	if _, err = s.ChangeSession(ctx, shop.ID, session.ID, "takeover"); err != nil {
		t.Fatal(err)
	}
	schedules, err = s.ListSchedules(ctx, shop.ID, session.ID)
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range schedules {
		if p.ID == future.ID && p.Status != "cancelled" {
			t.Fatal("takeover left old schedule eligible")
		}
	}
}
