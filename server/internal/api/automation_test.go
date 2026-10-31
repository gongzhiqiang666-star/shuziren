package api

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
)

func TestPostgresGenerationGateAndUnknownUsageReservation(t *testing.T) {
	s, _, shop, p, session := outputFixture(t, &fakeMedia{})
	ctx := context.Background()
	g := &blockedGenerator{started: make(chan struct{}), release: make(chan struct{})}
	s.Generator = g
	if _, err := s.Store.SaveGenerationLimits(ctx, domain.GenerationLimits{ShopID: shop.ID, RequestsPerMinute: 10, DailyTokenLimit: 100000}); err != nil {
		t.Fatal(err)
	}
	completed := make(chan error, 1)
	go func() { _, err := s.Generate(ctx, shop.ID, session.ID, p.ID, "多少钱？"); completed <- err }()
	<-g.started
	var e *domain.Error
	if _, err := s.Generate(ctx, shop.ID, session.ID, p.ID, "再次问价格"); !errors.As(err, &e) || e.Code != "generation_busy" {
		t.Fatalf("global concurrent limit not enforced: %v", err)
	}
	close(g.release)
	if err := <-completed; err != nil {
		t.Fatal(err)
	}
	u, err := s.Store.GenerationUsage(ctx, shop.ID)
	if err != nil || u.RequestsToday != 1 || u.UnknownRequestsToday != 1 || u.ChargedTokensToday != 100000 {
		t.Fatalf("missing-usage completion assumed free: %+v %v", u, err)
	}
	if _, err = s.Generate(ctx, shop.ID, session.ID, p.ID, "超出余额"); !errors.As(err, &e) || e.Code != "generation_budget_exceeded" {
		t.Fatalf("unknown reservation did not block next call: %v", err)
	}
}
func TestPostgresScheduledDispatchRequiresLiveOutputAndDoesNotReplay(t *testing.T) {
	m := &fakeMedia{live: true}
	s, db, shop, p, session := outputFixture(t, m)
	ctx := context.Background()
	_, a := issuedOutput(t, s, shop, session)
	connectedOutput(t, s, a, domain.NewID())
	j := outputReadyJob(t, s, shop, p, session)
	run := time.Now().Add(time.Minute)
	sc, err := s.Store.CreateSchedule(ctx, shop.ID, j.ID, run, run.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(ctx, "UPDATE speech_schedules SET run_at=now()-interval '1 second',expires_at=now()+interval '1 minute' WHERE id=$1", sc.ID); err != nil {
		t.Fatal(err)
	}
	claimed, err := s.Store.ClaimSchedule(ctx)
	if err != nil || claimed.ID != sc.ID {
		t.Fatalf("ready due schedule not claimed: %v", err)
	}
	s.dispatchScheduled(ctx, claimed)
	all, err := s.Store.ListSchedules(ctx, shop.ID, session.ID)
	if err != nil || len(all) != 1 || all[0].Status != "sent" || m.sendCount.Load() != 1 {
		t.Fatal("scheduled media was not accepted once")
	}
	if _, err = s.Store.ClaimSchedule(ctx); !errors.Is(err, store.ErrNoWork) {
		t.Fatal("completed schedule replayable")
	}
	j = outputReadyJob(t, s, shop, p, session)
	sc, err = s.Store.CreateSchedule(ctx, shop.ID, j.ID, run, run.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(ctx, "UPDATE session_outputs SET lease_expires_at=now()-interval '1 second' WHERE session_id=$1", session.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(ctx, "UPDATE speech_schedules SET run_at=now()-interval '1 second',expires_at=now()+interval '1 minute' WHERE id=$1", sc.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.ClaimSchedule(ctx); !errors.Is(err, store.ErrNoWork) {
		t.Fatal("offline receiver permitted automatic send")
	}
	all, err = s.Store.ListSchedules(ctx, shop.ID, session.ID)
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range all {
		if p.ID == sc.ID && (p.Status != "failed" || p.ErrorCode != "output_offline") {
			t.Fatal("offline schedule was not failed conservatively")
		}
	}
	if m.sendCount.Load() != 1 {
		t.Fatal("offline media was submitted")
	}
}

type cacheMedia struct {
	*fakeMedia
	engine string
	flip   bool
}

func (m *cacheMedia) TTSIdentity(context.Context) (string, error) {
	if m.engine == "" {
		return "", errors.New("identity unavailable")
	}
	return m.engine, nil
}
func (m *cacheMedia) Synthesize(ctx context.Context, text string) ([]byte, error) {
	b, e := m.fakeMedia.Synthesize(ctx, text)
	if m.flip {
		m.engine = strings.Repeat("b", 64)
	}
	return b, e
}
func TestAudioCacheUsesActualEngineVersionsAndChecksIntegrity(t *testing.T) {
	m := &cacheMedia{fakeMedia: &fakeMedia{tts: true}, engine: strings.Repeat("a", 64)}
	s, err := New(nil, m, nil, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	j := domain.Job{ShopID: domain.NewID(), ProductID: domain.NewID(), Text: "保温杯99元", ProductVersion: 1, PersonaVersion: 1, KnowledgeVersion: 1, BusinessFingerprint: "business-v1"}
	ctx := context.Background()
	for i := 0; i < 2; i++ {
		b, _, e := s.synthesizeAudio(ctx, j)
		if e != nil || !bytes.Equal(b, testWAV()) {
			t.Fatal("cached audio bytes changed")
		}
	}
	if m.synthCount.Load() != 1 {
		t.Fatal("verified identical request did not use cache")
	}
	key := audioCacheKey(j, m.engine)
	if err = os.WriteFile(filepath.Join(s.AudioDir, "cache", key+".wav"), []byte("corrupted audio"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err = s.synthesizeAudio(ctx, j); err != nil || m.synthCount.Load() != 2 {
		t.Fatal("cache corruption did not trigger real local synthesis")
	}
	j.PersonaVersion++
	if _, _, err = s.synthesizeAudio(ctx, j); err != nil || m.synthCount.Load() != 3 {
		t.Fatal("persona version reused incompatible cache")
	}
	m.engine = strings.Repeat("c", 64)
	if _, _, err = s.synthesizeAudio(ctx, j); err != nil || m.synthCount.Load() != 4 {
		t.Fatal("actual engine identity did not partition cache")
	}
	m.engine = ""
	if _, _, err = s.synthesizeAudio(ctx, j); err == nil || m.synthCount.Load() != 4 {
		t.Fatal("identity-capable provider with failed identity did not fail closed")
	}
	plain := &fakeMedia{tts: true}
	unverified, err := New(nil, plain, nil, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		_, id, e := unverified.synthesizeAudio(ctx, j)
		if e != nil || id != "" {
			t.Fatal("explicit identity-less test adapter should remain unverified")
		}
	}
	if plain.synthCount.Load() != 2 {
		t.Fatal("unverified test adapter reused cross-job cache")
	}
	m.engine = strings.Repeat("d", 64)
	m.flip = true
	oldEngine := m.engine
	if _, _, err = s.synthesizeAudio(ctx, j); err == nil {
		t.Fatal("engine change during synthesis returned usable audio")
	}
	if _, ok := s.cachedAudio(audioCacheKey(j, oldEngine), oldEngine); ok {
		t.Fatal("engine changed during synthesis but result was cached as old identity")
	}
}

func TestPostgresReadyAudioRemainsBoundToActualTTSEngine(t *testing.T) {
	m := &cacheMedia{fakeMedia: &fakeMedia{tts: true, live: true}, engine: strings.Repeat("a", 64)}
	s, _, shop, p, session := outputFixture(t, m)
	ctx := context.Background()
	j, err := s.Manual(ctx, shop.ID, session.ID, p.ID, "保温杯99元")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.Approve(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.QueueSynthesis(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	claimed, err := s.Store.ClaimNext(ctx)
	if err != nil {
		t.Fatal(err)
	}
	s.synthesize(ctx, claimed)
	j, err = s.Store.GetJob(ctx, shop.ID, j.ID)
	if err != nil || j.Status != "ready" || j.AudioEngineID != m.engine {
		t.Fatalf("ready audio lost its actual engine binding: %+v %v", j, err)
	}
	if _, err = s.Store.BindMedia(ctx, shop.ID, session.ID, session.Epoch, "verified-media-id"); err != nil {
		t.Fatal(err)
	}
	m.engine = strings.Repeat("b", 64)
	if _, err = s.Send(ctx, shop.ID, j.ID); err == nil || m.sendCount.Load() != 0 {
		t.Fatal("changed engine permitted old audio")
	}
	m.engine = ""
	if _, err = s.Send(ctx, shop.ID, j.ID); err == nil || m.sendCount.Load() != 0 {
		t.Fatal("unavailable engine identity permitted audio")
	}
	m.engine = strings.Repeat("a", 64)
	result, err := s.Send(ctx, shop.ID, j.ID)
	if err != nil || result.Status != "sent" || m.sendCount.Load() != 1 {
		t.Fatalf("original verified engine was not usable: %v", err)
	}
}
