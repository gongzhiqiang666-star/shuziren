package store_test

import (
	"context"
	"strings"
	"testing"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/retrieval"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
)

func TestEmbeddingRejectsForeignAndLateStaleContent(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, _, _ := fixture(t, s)
	other, _, _ := fixture(t, s)
	k, e := s.SaveKnowledge(ctx, domain.Knowledge{ShopID: shop.ID, Title: "清洗", Content: "用温水", Kind: "faq"}, true)
	if e != nil {
		t.Fatal(e)
	}
	v := make([]float32, retrieval.Dimensions)
	v[0] = 1
	revision := strings.Repeat("a", 64)
	hash := store.ContentHash(k.Title + "\n" + k.Content)
	if e = s.SaveEmbedding(ctx, other.ID, k.ID, hash, revision, v); e == nil {
		t.Fatal("cross-shop embedding falsely succeeded")
	}
	if e = s.SaveEmbedding(ctx, shop.ID, k.ID, hash, revision, v); e != nil {
		t.Fatal(e)
	}
	k.Content = "用清水清洗"
	if _, e = s.SaveKnowledge(ctx, k, false); e != nil {
		t.Fatal(e)
	}
	if e = s.SaveEmbedding(ctx, shop.ID, k.ID, hash, revision, v); e == nil {
		t.Fatal("late vector overwrote current knowledge cache")
	}
	if e = s.SaveEmbedding(ctx, shop.ID, k.ID, store.ContentHash(k.Title+"\n"+k.Content), revision, v); e != nil {
		t.Fatal(e)
	}
}

func TestTaobaoActionRetainsUnknownAcrossEpochAndCannotRewriteFinalState(t *testing.T) {
	s, _ := testutil.Postgres(t)
	ctx := context.Background()
	shop, _, session := fixture(t, s)
	id := domain.NewID()
	hash := store.ContentHash("same-payload")
	a, fresh, e := s.BeginTaobaoAction(ctx, shop.ID, session.ID, id, "push_item", hash)
	if e != nil || !fresh || a.Status != "pending" {
		t.Fatal(a, fresh, e)
	}
	if _, e = s.ChangeSession(ctx, shop.ID, session.ID, "takeover"); e != nil {
		t.Fatal(e)
	}
	a, e = s.FinishTaobaoAction(ctx, shop.ID, id, "succeeded", "")
	if e != nil || a.Status != "delivery_unknown" || a.ErrorCode != "session_interrupted" {
		t.Fatalf("late success survived takeover: %+v %v", a, e)
	}
	a, e = s.FinishTaobaoAction(ctx, shop.ID, id, "succeeded", "")
	if e != nil || a.Status != "delivery_unknown" {
		t.Fatal("final state rewritten", a, e)
	}
	a, fresh, e = s.BeginTaobaoAction(ctx, shop.ID, session.ID, id, "push_item", hash)
	if e != nil || fresh || a.Status != "delivery_unknown" {
		t.Fatal("repeat after pause cannot read prior result", a, e)
	}
	_, _, e = s.BeginTaobaoAction(ctx, shop.ID, session.ID, id, "push_item", store.ContentHash("different"))
	wantCode(t, e, "idempotency_conflict")
	_, _, e = s.BeginTaobaoAction(ctx, shop.ID, session.ID, domain.NewID(), "push_item", hash)
	wantCode(t, e, "session_inactive")
}
