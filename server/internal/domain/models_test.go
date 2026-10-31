package domain

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestContextVersionsAndOwnership(t *testing.T) {
	now := time.Now()
	future := now.Add(time.Hour)
	s := Snapshot{Shop: Shop{ID: NewID()}, KnowledgeVersion: 4}
	s.Product = Product{ID: NewID(), ShopID: s.Shop.ID, Active: true, Version: 3, ExpiresAt: &future}
	s.Persona = Persona{ShopID: s.Shop.ID, Version: 2}
	s.Session = Session{ID: NewID(), ShopID: s.Shop.ID, Status: "active", Epoch: 5}
	j := Job{ShopID: s.Shop.ID, SessionID: s.Session.ID, ProductID: s.Product.ID, ProductVersion: 3, PersonaVersion: 2, KnowledgeVersion: 4, Epoch: 5}
	if err := ValidateJob(j, s, now); err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name, code string
		change     func(*Snapshot, *Job)
	}{
		{"epoch", "stale_epoch", func(_ *Snapshot, j *Job) { j.Epoch-- }},
		{"product", "stale_product", func(s *Snapshot, _ *Job) { s.Product.Version++ }},
		{"persona", "stale_persona", func(s *Snapshot, _ *Job) { s.Persona.Version++ }},
		{"knowledge", "stale_knowledge", func(s *Snapshot, _ *Job) { s.KnowledgeVersion++ }},
		{"paused", "session_inactive", func(s *Snapshot, _ *Job) { s.Session.Status = "paused" }},
		{"inactive", "product_inactive", func(s *Snapshot, _ *Job) { s.Product.Active = false }},
		{"expired", "product_expired", func(s *Snapshot, _ *Job) { s.Product.ExpiresAt = &now }},
		{"wrong shop", "not_found", func(s *Snapshot, _ *Job) { s.Product.ShopID = NewID() }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			ss, jj := s, j
			tc.change(&ss, &jj)
			err := ValidateJob(jj, ss, now)
			var e *Error
			if !errors.As(err, &e) || e.Code != tc.code {
				t.Fatalf("want %s, got %v", tc.code, err)
			}
		})
	}
}
func TestIDAndQualityDefaults(t *testing.T) {
	for i := 0; i < 100; i++ {
		if !ValidID(NewID()) {
			t.Fatal("invalid random UUID")
		}
	}
	for _, id := range []string{"", "../../secret", "12345678-1234-1234-1234-1234567890--", strings.Repeat("g", 36)} {
		if ValidID(id) {
			t.Fatalf("accepted invalid ID %q", id)
		}
	}
	p := DefaultQuality(NewID(), time.Time{})
	if p.FPS != 25 || p.SyncTargetMS != 80 || !p.UpdatedAt.IsZero() {
		t.Fatal("unexpected default profile")
	}
	for _, c := range p.Checks {
		if c.Passed {
			t.Fatal("quality must never pass by default")
		}
	}
}
func TestKeywordSelectionIsRelevantBoundedAndDeterministic(t *testing.T) {
	records := []Knowledge{{ID: "b", Title: "保温杯清洁", Content: "使用温水清洁保温杯。", Kind: "faq"}, {ID: "a", Title: "保温杯清洁", Content: "使用温水清洁保温杯。", Kind: "faq"}, {ID: "c", Title: "订单个人信息", Content: "无关顾客地址，绝不能作为整个数据库发出", Kind: "memory"}, {ID: "d", Title: "保温杯", Content: strings.Repeat("杯", 7000), Kind: "faq"}}
	out := SelectKnowledge(records, "保温杯如何清洁", "保温杯")
	if len(out) != 2 || out[0].ID != "a" || out[1].ID != "b" {
		t.Fatalf("unexpected relevant selection: %#v", out)
	}
	if len(SelectKnowledge(records, "完全不匹配问题", "其他商品")) != 0 {
		t.Fatal("irrelevant knowledge leaked")
	}
}
