package domain

import (
	"math"
	"testing"
	"time"
)

func TestBusinessFingerprintStableButSensitiveToExpiryAndVersions(t *testing.T) {
	now := time.Date(2026, 10, 31, 8, 0, 0, 0, time.UTC)
	end := now.Add(time.Hour)
	b := BusinessSnapshot{Promotions: []Promotion{{ID: "b", Active: true, Version: 1, StartsAt: now.Add(-time.Hour), EndsAt: end}, {ID: "a", Active: true, Version: 1, StartsAt: now.Add(-time.Hour), EndsAt: end}}, KnowledgeRefs: []KnowledgeRef{{ID: "memory", Version: 1, ExpiresAt: &end}}}
	b.Boundary(&end, now)
	b.Seal()
	first := b.Fingerprint
	b.Seal()
	if b.Fingerprint != first {
		t.Fatal("fingerprint depends on previous fingerprint")
	}
	b.Promotions[0], b.Promotions[1] = b.Promotions[1], b.Promotions[0]
	b.Seal()
	if b.Fingerprint != first {
		t.Fatal("query order changed business fingerprint")
	}
	if err := ValidateBusinessSnapshot(b, end); err == nil {
		t.Fatal("an unchanged snapshot survived its expiry boundary")
	}
	b.KnowledgeRefs[0].Version++
	b.Seal()
	if b.Fingerprint == first {
		t.Fatal("changed memory version preserved fingerprint")
	}
	j := Job{BusinessFingerprint: first}
	s := Snapshot{Business: b}
	if err := ValidateBusinessJob(j, s, now); err == nil {
		t.Fatal("stale business job validated")
	}
	if err := ValidateBusinessSnapshot(b, now); err != nil {
		t.Fatal(err)
	}
}

func TestCostSettingsRejectNonFiniteAndDoNotInventRates(t *testing.T) {
	if !ValidCostSettings(CostSettings{}) {
		t.Fatal("unset rates must be valid")
	}
	for _, f := range []float64{math.NaN(), math.Inf(1), -1, 10000001} {
		if ValidCostSettings(CostSettings{InputCNYPerMillion: &f}) {
			t.Fatal("invalid rate accepted")
		}
	}
}
