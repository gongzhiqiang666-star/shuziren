package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/config"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/retrieval"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
)

func TestRetrievalFlowKeepsQuestionScopedFactsAndContentCacheSeparate(t *testing.T) {
	s, shop, product, session := serviceFixture(t, &fakeMedia{})
	ctx := context.Background()
	question := "买了不合适可以退吗？"
	create := func(title, content, scope string, scopeID *string, expires *time.Time) domain.KnowledgeRecord {
		t.Helper()
		k, err := s.Store.SaveKnowledgeRecord(ctx, domain.KnowledgeRecord{
			Knowledge: domain.Knowledge{ShopID: shop.ID, Title: title, Content: content, Kind: "faq"},
			Source:    "测试店主确认", Scope: scope, ScopeID: scopeID, ExpiresAt: expires,
		}, true)
		if err != nil {
			t.Fatal(err)
		}
		return k
	}
	faq := create("退货说明", "未使用且包装完整时，可联系客服确认退货。", "product", &product.ID, nil)
	spec := create("保温杯规格", "容量为500毫升。", "shop", nil, nil)
	past := time.Now().Add(-time.Hour)
	create("过期退货政策", "过期内容不得进入检索。", "shop", nil, &past)
	otherSession, err := s.Store.CreateSession(ctx, shop.ID, "其他测试场次")
	if err != nil {
		t.Fatal(err)
	}
	create("其他场次政策", "其他场次内容不得进入检索。", "session", &otherSession.ID, nil)

	oldText := faq.Title + "\n" + faq.Content
	newContent := "请先联系客服确认退货条件与寄回地址。"
	newText := faq.Title + "\n" + newContent
	specText := spec.Title + "\n" + spec.Content
	revision := strings.Repeat("a", 64)
	token := strings.Repeat("b", 32)
	type embeddingRequest struct {
		Texts []string `json:"texts"`
		Query bool     `json:"query"`
	}
	var mu sync.Mutex
	var calls []embeddingRequest
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/embed" || r.Header.Get("Authorization") != "Bearer "+token {
			t.Errorf("unexpected embedding request: %s %s", r.Method, r.URL.Path)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		var in embeddingRequest
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			t.Errorf("decode embedding request: %v", err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		mu.Lock()
		calls = append(calls, in)
		mu.Unlock()
		vectors := make([][]float32, len(in.Texts))
		for i, text := range in.Texts {
			v := make([]float32, retrieval.Dimensions)
			switch {
			case in.Query, text == oldText:
				v[0] = 1
			case text == newText:
				v[0], v[1] = 0.6, 0.8
			case text == specText:
				v[1] = 1
			default:
				t.Errorf("out-of-scope or unexpected document sent to embedding: %q", text)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			vectors[i] = v
		}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(retrieval.Result{Model: retrieval.Model, Revision: revision, Vectors: vectors}); err != nil {
			t.Errorf("encode embedding response: %v", err)
		}
	}))
	defer upstream.Close()
	if err := s.ConfigureIntegrations(config.Integrations{Retrieval: retrieval.Config{BaseURL: upstream.URL, APIKey: token}}); err != nil {
		t.Fatal(err)
	}
	router := Router(s, testToken, "")
	body, err := json.Marshal(map[string]string{"shop_id": shop.ID, "session_id": session.ID, "product_id": product.ID, "question": question})
	if err != nil {
		t.Fatal(err)
	}
	search := func(wantContent string) {
		t.Helper()
		response := request(router, http.MethodPost, "/api/v1/retrieval/search", string(body), testToken)
		if response.Code != http.StatusOK {
			t.Fatalf("retrieval failed: %d %s", response.Code, response.Body.String())
		}
		var result struct {
			Data struct {
				Mode    string             `json:"mode"`
				Matches []domain.Knowledge `json:"matches"`
			} `json:"data"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		matches := result.Data.Matches
		if result.Data.Mode != "bge" || len(matches) != 1 || matches[0].ID != faq.ID || matches[0].Content != wantContent {
			t.Fatalf("expected current in-scope return FAQ only: %+v", result.Data)
		}
	}
	assertCalls := func(wantQueries, wantBatches int, wantDocuments map[string]int) {
		t.Helper()
		mu.Lock()
		observed := append([]embeddingRequest(nil), calls...)
		mu.Unlock()
		queries, batches := 0, 0
		documents := map[string]int{}
		for _, call := range observed {
			if call.Query {
				queries++
				// Real BGE smoke testing exposed product-title contamination of a
				// return question. Product/session scope is already applied in SQL;
				// structured product facts must not be appended to query embeddings.
				if len(call.Texts) != 1 || call.Texts[0] != question {
					t.Errorf("query must contain only the original question: %#v", call.Texts)
				}
				continue
			}
			batches++
			for _, text := range call.Texts {
				documents[text]++
			}
		}
		if queries != wantQueries || batches != wantBatches || len(documents) != len(wantDocuments) {
			t.Fatalf("unexpected embedding calls: queries=%d batches=%d documents=%v", queries, batches, documents)
		}
		for text, want := range wantDocuments {
			if documents[text] != want {
				t.Errorf("document embedded %d times, want %d: %q", documents[text], want, text)
			}
		}
	}

	search(faq.Content)
	assertCalls(1, 1, map[string]int{oldText: 1, specText: 1})
	search(faq.Content)
	assertCalls(2, 1, map[string]int{oldText: 1, specText: 1})

	faq.Content = newContent
	faq, err = s.Store.SaveKnowledgeRecord(ctx, faq, false)
	if err != nil {
		t.Fatal(err)
	}
	search(newContent)
	assertCalls(3, 2, map[string]int{oldText: 1, newText: 1, specText: 1})
	oldVector, err := s.Store.Embedding(ctx, shop.ID, faq.ID, store.ContentHash(oldText), revision)
	if err != nil || len(oldVector) != 0 {
		t.Fatalf("old content hash still reusable: %v, error=%v", oldVector, err)
	}
	newVector, err := s.Store.Embedding(ctx, shop.ID, faq.ID, store.ContentHash(newText), revision)
	if err != nil || !retrieval.Valid(newVector) || newVector[0] != float32(0.6) || newVector[1] != float32(0.8) {
		t.Fatalf("new content did not persist its new embedding: %v, error=%v", newVector, err)
	}
}
