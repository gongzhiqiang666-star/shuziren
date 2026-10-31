package retrieval

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestEmbeddingProtocolAndInvalidVectors(t *testing.T) {
	v := make([]float32, Dimensions)
	v[0] = 1
	malformed := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer local-only-test-embedding-key" {
			t.Error("missing auth")
		}
		var input struct {
			Texts []string `json:"texts"`
			Query bool     `json:"query"`
		}
		if json.NewDecoder(r.Body).Decode(&input) != nil || !input.Query || len(input.Texts) != 1 {
			t.Error("invalid input")
		}
		vector := v
		if malformed {
			vector = []float32{1}
		}
		json.NewEncoder(w).Encode(Result{Model: Model, Revision: strings.Repeat("a", 64), Vectors: [][]float32{vector}})
	}))
	defer server.Close()
	c, e := New(Config{BaseURL: server.URL, APIKey: "local-only-test-embedding-key"})
	if e != nil {
		t.Fatal(e)
	}
	if _, e = c.Embed(context.Background(), []string{"如何退货"}, true); e != nil {
		t.Fatal(e)
	}
	malformed = true
	if _, e = c.Embed(context.Background(), []string{"如何退货"}, true); e == nil {
		t.Fatal("invalid dimension accepted")
	}
}
func TestEmbeddingCannotUseRemoteProvider(t *testing.T) {
	for _, u := range []string{"https://api.example.com", "http://public.example.com", "http://127.0.0.1:1000?key=secret"} {
		if _, e := New(Config{BaseURL: u, APIKey: strings.Repeat("a", 30)}); e == nil {
			t.Fatal("remote embedding accepted")
		}
	}
}
