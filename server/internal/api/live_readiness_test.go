package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"testing"
)

func TestLiveReadinessFlowStopsAtLocalProof(t *testing.T) {
	svc, shop, _, _ := serviceFixture(t, &fakeMedia{})
	r := Router(svc, testToken, "")
	out := request(r, http.MethodPost, "/api/v1/live-readiness/runs", `{"shop_id":"`+shop.ID+`","title":"首次验证","output_mode":"virtual_camera"}`, testToken)
	if out.Code != 200 {
		t.Fatalf("create: %d %s", out.Code, out.Body.String())
	}
	var envelope struct {
		Data struct {
			ID      string                          `json:"id"`
			Version int64                           `json:"version"`
			Gates   []struct{ Name, Status string } `json:"gates"`
		} `json:"data"`
	}
	if json.Unmarshal(out.Body.Bytes(), &envelope) != nil || len(envelope.Data.Gates) != 5 {
		t.Fatal("missing default gates")
	}
	version := envelope.Data.Version
	updates := []struct{ gate, evidence string }{
		{"install", `{"preflight_report":"preflight-01","nvidia":true,"assets":true,"operator_confirmed":true}`},
		{"generation", `{"new_text":true,"wav_sha256":"` + strings.Repeat("a", 64) + `","listened":true,"same_wav":true}`},
		{"obs", `{"output_mode":"virtual_camera","video":"recording-01","audio":"recording-01","reviewed":true}`},
	}
	for _, update := range updates {
		body := `{"shop_id":"` + shop.ID + `","version":` + itoa(version) + `,"status":"passed","evidence":` + update.evidence + `,"note":"人工记录"}`
		out = request(r, http.MethodPut, "/api/v1/live-readiness/runs/"+envelope.Data.ID+"/gates/"+update.gate, body, testToken)
		if out.Code != 200 {
			t.Fatalf("update %s: %d %s", update.gate, out.Code, out.Body.String())
		}
		var changed struct {
			Data struct {
				Version    int64  `json:"version"`
				Conclusion string `json:"conclusion"`
			} `json:"data"`
		}
		_ = json.Unmarshal(out.Body.Bytes(), &changed)
		version = changed.Data.Version
		if update.gate == "obs" && changed.Data.Conclusion != "local_chain_passed_platform_blocked" {
			t.Fatalf("conclusion %q", changed.Data.Conclusion)
		}
	}
	out = request(r, http.MethodGet, "/api/v1/live-readiness/runs/"+envelope.Data.ID+"/export?shop_id="+shop.ID, "", testToken)
	if out.Code != 200 || strings.Contains(strings.ToLower(out.Body.String()), "token") || strings.Contains(out.Body.String(), `C:\`) {
		t.Fatalf("unsafe export: %d %s", out.Code, out.Body.String())
	}
}

func TestLiveReadinessRejectsIncompleteEvidenceBeforeStore(t *testing.T) {
	r := Router(&Service{}, testToken, "")
	id := "abcdef01-2345-6789-abcd-ef0123456789"
	body := `{"shop_id":"` + id + `","version":1,"status":"passed","evidence":{"video":"only"},"note":""}`
	out := request(r, http.MethodPut, "/api/v1/live-readiness/runs/"+id+"/gates/obs", body, testToken)
	if out.Code != 400 {
		t.Fatalf("got %d %s", out.Code, out.Body.String())
	}
}

func itoa(v int64) string { return fmt.Sprintf("%d", v) }
