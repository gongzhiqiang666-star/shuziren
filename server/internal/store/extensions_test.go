package store_test

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
)

func TestBusinessHistoryRestoresNewVersionsAndPreservesTenantBoundaries(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, _ := fixture(t, s)
	other, _, _ := fixture(t, s)
	persona, err := s.GetPersona(ctx, shop.ID)
	if err != nil {
		t.Fatal(err)
	}
	original := persona.Tone
	persona.Tone = "稳重"
	persona, err = s.SavePersona(ctx, persona)
	if err != nil {
		t.Fatal(err)
	}
	h, err := s.BusinessHistory(ctx, shop.ID, "persona", shop.ID)
	if err != nil || len(h) != 2 {
		t.Fatalf("persona history: %d %v", len(h), err)
	}
	restored, err := s.RestorePersona(ctx, shop.ID, persona.Version, 1)
	if err != nil || restored.Version != 3 || restored.Tone != original {
		t.Fatalf("persona restore: %+v %v", restored, err)
	}
	_, err = s.RestorePersona(ctx, shop.ID, 2, 1)
	wantCode(t, err, "stale_version")
	p.PriceCents = 18800
	p, err = s.SaveProduct(ctx, p, false)
	if err != nil {
		t.Fatal(err)
	}
	restoredProduct, err := s.RestoreProduct(ctx, shop.ID, p.ID, p.Version, 1)
	if err != nil || restoredProduct.Version != 3 || restoredProduct.PriceCents != 9900 {
		t.Fatalf("product restore: %+v %v", restoredProduct, err)
	}
	if _, err = s.BusinessHistory(ctx, other.ID, "product", p.ID); err == nil {
		t.Fatal("cross-shop product history exposed")
	}
}

func TestKnowledgeVersionsScopesExpiryDeletionAndRestoration(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	other, otherProduct, _ := fixture(t, s)
	k, err := s.SaveKnowledgeRecord(ctx, domain.KnowledgeRecord{Knowledge: domain.Knowledge{ShopID: shop.ID, Title: "记忆", Content: "讲解采用简短句子", Kind: "memory"}, Source: "店主确认", Scope: "shop"}, true)
	if err != nil {
		t.Fatal(err)
	}
	if k.Version != 1 {
		t.Fatal("initial knowledge version")
	}
	j := draft(t, s, shop, p, session)
	k.Content = "讲解先说规格"
	updated, err := s.SaveKnowledgeRecord(ctx, k, false)
	if err != nil || updated.Version != 2 {
		t.Fatalf("knowledge update %v", err)
	}
	_, err = s.SaveKnowledgeRecord(ctx, k, false)
	wantCode(t, err, "stale_version")
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_knowledge")
	if err = s.DeleteKnowledgeRecord(ctx, other.ID, k.ID, updated.Version); err == nil {
		t.Fatal("cross shop delete")
	}
	if err = s.DeleteKnowledgeRecord(ctx, shop.ID, k.ID, updated.Version); err != nil {
		t.Fatal(err)
	}
	snap, err := s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	if err != nil || len(snap.Knowledge) != 0 {
		t.Fatal("deleted memory entered snapshot")
	}
	restored, err := s.RestoreKnowledgeRecord(ctx, shop.ID, k.ID, 3, 1)
	if err != nil || restored.Version != 4 || restored.DeletedAt != nil || restored.Content != k.Content && restored.Content != "讲解采用简短句子" {
		t.Fatalf("restore %+v %v", restored, err)
	}
	// Legacy CRUD is archived by triggers too, and physically deleted rows can
	// still be restored without recycling their prior version numbers.
	legacy, err := s.SaveKnowledge(ctx, domain.Knowledge{ShopID: shop.ID, Title: "legacy", Content: "fact", Kind: "faq"}, true)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.DeleteKnowledge(ctx, shop.ID, legacy.ID); err != nil {
		t.Fatal(err)
	}
	legacyRestored, err := s.RestoreKnowledgeRecord(ctx, shop.ID, legacy.ID, 2, 1)
	if err != nil || legacyRestored.Version != 3 {
		t.Fatalf("legacy restore %+v %v", legacyRestored, err)
	}
	bad := domain.KnowledgeRecord{Knowledge: domain.Knowledge{ShopID: shop.ID, Title: "foreign", Content: "cannot reference foreign product", Kind: "faq"}, Source: "test", Scope: "product", ScopeID: &otherProduct.ID}
	if _, err = s.SaveKnowledgeRecord(ctx, bad, true); err == nil {
		t.Fatal("foreign scoped product accepted")
	}
	past := time.Now().Add(-time.Second)
	expired, err := s.SaveKnowledgeRecord(ctx, domain.KnowledgeRecord{Knowledge: domain.Knowledge{ShopID: shop.ID, Title: "expired", Content: "must not enter prompt", Kind: "memory"}, Source: "test", Scope: "shop", ExpiresAt: &past}, true)
	if err != nil {
		t.Fatal(err)
	}
	second, err := s.CreateSession(ctx, shop.ID, "另场")
	if err != nil {
		t.Fatal(err)
	}
	scoped, err := s.SaveKnowledgeRecord(ctx, domain.KnowledgeRecord{Knowledge: domain.Knowledge{ShopID: shop.ID, Title: "scoped", Content: "only second session", Kind: "memory"}, Source: "test", Scope: "session", ScopeID: &second.ID}, true)
	if err != nil {
		t.Fatal(err)
	}
	snap, err = s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	if err != nil {
		t.Fatal(err)
	}
	for _, v := range snap.Knowledge {
		if v.ID == expired.ID || v.ID == scoped.ID {
			t.Fatal("expired or wrong-scope record entered prompt")
		}
	}
	h, err := s.BusinessHistory(ctx, shop.ID, "knowledge", k.ID)
	if err != nil || len(h) != 4 {
		t.Fatalf("history %d %v", len(h), err)
	}
}

func TestPromotionsAndAssetsInvalidatePreviouslyApprovedJobs(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	other, otherProduct, _ := fixture(t, s)
	_ = other
	j := draft(t, s, shop, p, session)
	now := time.Now()
	price := int64(8800)
	promo, err := s.SavePromotion(ctx, domain.Promotion{ShopID: shop.ID, ProductID: &p.ID, Title: "本场活动", OfferPriceCents: &price, StartsAt: now.Add(-time.Hour), EndsAt: now.Add(time.Hour), Active: true}, true)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_business")
	snap, err := s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	if err != nil || len(snap.Business.Promotions) != 1 || snap.Business.ValidUntil == nil {
		t.Fatalf("promotion snapshot %+v %v", snap.Business, err)
	}
	if err = domain.ValidateBusinessSnapshot(snap.Business, promo.EndsAt); err == nil {
		t.Fatal("clock expiry did not invalidate unchanged activity")
	}
	promo.Version = 1
	promo.ProductID = &otherProduct.ID
	if _, err = s.SavePromotion(ctx, promo, false); err == nil {
		t.Fatal("foreign promotion target")
	}
	promo.ProductID = &p.ID
	promo.Active = false
	promo, err = s.SavePromotion(ctx, promo, false)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.SavePromotion(ctx, domain.Promotion{ID: promo.ID, ShopID: shop.ID, Version: 1, StartsAt: now, EndsAt: now.Add(time.Hour)}, false)
	wantCode(t, err, "stale_version")
	j = draft(t, s, shop, p, session)
	a, err := s.SaveAsset(ctx, domain.Asset{ShopID: shop.ID, Kind: "voice", Name: "授权音色", Identifier: "voice-001", SHA256: strings.Repeat("a", 64), Authorized: true, Active: true}, true)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.Approve(ctx, shop.ID, j.ID)
	wantCode(t, err, "stale_business")
	if a.BindingStatus != "record_only" {
		t.Fatal("asset incorrectly claimed engine binding")
	}
	b, err := s.SaveAsset(ctx, domain.Asset{ShopID: shop.ID, Kind: "voice", Name: "音色2", Identifier: "voice-002", SHA256: strings.Repeat("b", 64), Authorized: true, Active: true}, true)
	if err != nil {
		t.Fatal(err)
	}
	assets, err := s.ListAssets(ctx, shop.ID)
	if err != nil {
		t.Fatal(err)
	}
	active := 0
	for _, v := range assets {
		if v.Active {
			active++
			if v.ID != b.ID {
				t.Fatal("old voice remained active")
			}
		}
	}
	if active != 1 {
		t.Fatal("multiple active voice records")
	}
	h, err := s.BusinessHistory(ctx, shop.ID, "asset", a.ID)
	if err != nil || len(h) != 2 {
		t.Fatal("automatic deactivation history missing")
	}
}

func TestUsageLedgerIncludesDiscardedAndUnknownRequestsWithoutDoubleCounting(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	cs, err := s.CostSummary(ctx, shop.ID, "")
	if err != nil || cs.EstimatedAICNY != nil {
		t.Fatal("unset rates should not claim zero cost")
	}
	snap, err := s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	if err != nil {
		t.Fatal(err)
	}
	job, err := s.CreateJob(ctx, snap, domain.Job{Source: "deepseek", Status: "draft", Text: "已审核资料的草稿", InputTokens: 100, OutputTokens: 50})
	if err != nil {
		t.Fatal(err)
	}
	u, err := s.StartUsage(ctx, shop.ID, session.ID, "deepseek-flash")
	if err != nil {
		t.Fatal(err)
	}
	if err = s.FinishUsage(ctx, shop.ID, u.ID, "complete", 100, 50, &job.ID, ""); err != nil {
		t.Fatal(err)
	}
	if err = s.FinishUsage(ctx, shop.ID, u.ID, "complete", 100, 50, &job.ID, ""); err == nil {
		t.Fatal("finalized usage rewritten")
	}
	discarded, err := s.StartUsage(ctx, shop.ID, session.ID, "deepseek-flash")
	if err != nil {
		t.Fatal(err)
	}
	if err = s.FinishUsage(ctx, shop.ID, discarded.ID, "complete", 70, 20, nil, "stale_context"); err != nil {
		t.Fatal(err)
	}
	unknown, err := s.StartUsage(ctx, shop.ID, session.ID, "deepseek-flash")
	if err != nil {
		t.Fatal(err)
	}
	if err = s.FinishUsage(ctx, shop.ID, unknown.ID, "unknown", 0, 0, nil, "cancelled"); err != nil {
		t.Fatal(err)
	}
	if _, err = s.StartUsage(ctx, shop.ID, session.ID, "deepseek-flash"); err != nil {
		t.Fatal(err)
	} // a crashed in-flight request remains unknown
	in, out, power, watts := 2.0, 8.0, 0.6, 500.0
	settings, err := s.SaveCostSettings(ctx, domain.CostSettings{ShopID: shop.ID, InputCNYPerMillion: &in, OutputCNYPerMillion: &out, ElectricityCNYPerKWH: &power, DeviceWatts: &watts})
	if err != nil || settings.Version != 1 {
		t.Fatal(err)
	}
	cs, err = s.CostSummary(ctx, shop.ID, session.ID)
	if err != nil {
		t.Fatal(err)
	}
	if cs.InputTokens != 170 || cs.OutputTokens != 70 || cs.GeneratedJobs != 1 || cs.UsageEvents != 4 || cs.UnknownUsageEvents != 2 {
		t.Fatalf("incorrect ledger %+v", cs)
	}
	if cs.EstimatedAICNY == nil || *cs.EstimatedAICNY != 0.0009 || cs.EstimatedPowerCNYPerHour == nil || *cs.EstimatedPowerCNYPerHour != 0.3 {
		t.Fatalf("incorrect estimate %+v", cs)
	}
	_, err = s.SaveCostSettings(ctx, domain.CostSettings{ShopID: shop.ID, Version: 0})
	wantCode(t, err, "stale_version")
}

func TestEffectiveContextFiltersBeforeLimitAndNeverSilentlyDropsLiveFacts(t *testing.T) {
	s, db := testutil.Postgres(t)
	ctx := context.Background()
	shop, p, session := fixture(t, s)
	kept, err := s.SaveKnowledgeRecord(ctx, domain.KnowledgeRecord{Knowledge: domain.Knowledge{ShopID: shop.ID, Title: "有效知识", Content: "仍应进入上下文", Kind: "faq"}, Source: "店主确认", Scope: "shop"}, true)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(ctx, `INSERT INTO knowledge(id,shop_id,title,content,kind,expires_at) SELECT gen_random_uuid(),$1,'过期记录','不会挤掉有效事实','faq',now()-interval '1 hour' FROM generate_series(1,1001)`, shop.ID)
	if err != nil {
		t.Fatal(err)
	}
	snap, err := s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	if err != nil || len(snap.Knowledge) != 1 || snap.Knowledge[0].ID != kept.ID {
		t.Fatalf("expired records hid effective fact: %d %v", len(snap.Knowledge), err)
	}
	_, err = db.Exec(ctx, "UPDATE knowledge SET expires_at=NULL WHERE shop_id=$1", shop.ID)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.Snapshot(ctx, shop.ID, session.ID, p.ID)
	wantCode(t, err, "business_context_limit")
}

func TestConcurrentPromotionEditorsCannotSilentlyOverwriteEachOther(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, _, _ := fixture(t, s)
	now := time.Now()
	p, err := s.SavePromotion(ctx, domain.Promotion{ShopID: shop.ID, Title: "活动", StartsAt: now, EndsAt: now.Add(time.Hour)}, true)
	if err != nil {
		t.Fatal(err)
	}
	start := make(chan struct{})
	results := make(chan error, 2)
	var wg sync.WaitGroup
	for _, name := range []string{"A编辑", "B编辑"} {
		wg.Add(1)
		go func(title string) {
			defer wg.Done()
			<-start
			edit := p
			edit.Title = title
			_, e := s.SavePromotion(ctx, edit, false)
			results <- e
		}(name)
	}
	close(start)
	wg.Wait()
	close(results)
	success, rejected := 0, 0
	for e := range results {
		if e == nil {
			success++
		} else {
			wantCode(t, e, "stale_version")
			rejected++
		}
	}
	if success != 1 || rejected != 1 {
		t.Fatalf("lost update protection failed: %d/%d", success, rejected)
	}
	h, err := s.BusinessHistory(ctx, shop.ID, "promotion", p.ID)
	if err != nil || len(h) != 2 {
		t.Fatal("concurrent write history mismatch", len(h), err)
	}
}
