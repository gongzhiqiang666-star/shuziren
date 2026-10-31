package media

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTTSIdentityRequiresAuthenticatedReadyContentFingerprint(t *testing.T) {
	id := strings.Repeat("a", 64)
	for _, tc := range []struct {
		body   string
		status int
		valid  bool
	}{
		{fmt.Sprintf(`{"status":"ready","model_loaded":true,"engine":"cosyvoice3","reason":"ready","engine_id":%q}`, id), 200, true},
		{`{"status":"ready","model_loaded":true,"engine":"cosyvoice3","reason":"ready"}`, 200, false},
		{fmt.Sprintf(`{"status":"unavailable","model_loaded":false,"engine":"cosyvoice3","reason":"model_missing","engine_id":%q}`, id), 503, false},
		{fmt.Sprintf(`{"status":"ready","model_loaded":true,"engine":"cosyvoice3","reason":"ready","engine_id":%q}`, strings.Repeat("A", 64)), 200, false},
	} {
		u := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "GET" || r.URL.Path != "/prefix/healthz" || r.Header.Get("Authorization") != "Bearer "+testToken {
				t.Error("identity request violated auth or endpoint contract")
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(tc.status)
			fmt.Fprint(w, tc.body)
		}))
		c := mustClient(t, Config{TTSBaseURL: u.URL + "/prefix", TTSAPIKey: testToken})
		got, err := c.TTSIdentity(context.Background())
		u.Close()
		if tc.valid && (err != nil || got != id) {
			t.Fatalf("expected identity: %q %v", got, err)
		}
		if !tc.valid && (err == nil || got != "") {
			t.Fatal("invalid or unavailable model supplied cache identity")
		}
	}
}
