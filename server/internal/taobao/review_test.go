package taobao

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestDuplicateSuccessCannotOverrideFailureAndGenericRemoteErrorsStayUnknown(t *testing.T) {
	for _, body := range []string{`{"live_virtualanchor_push_item_card_response":{"business_success":false,"business_success":true}}`, `{"live_virtualanchor_push_item_card_response":{"business_success":false},"live_virtualanchor_push_item_card_response":{"business_success":true}}`, `{"error_response":{"code":50,"msg":"Remote service error"}}`} {
		u := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(body)) }))
		c, e := New(Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: u.URL})
		if e != nil {
			t.Fatal(e)
		}
		err := c.PushItem(context.Background(), "1", "2")
		u.Close()
		var typed *Error
		if !errors.As(err, &typed) || typed.Definitive {
			t.Fatal("ambiguous malformed/remote response accepted as definitive", err)
		}
	}
}
func TestConsumeDistinguishesExplicitEmptyFromUnverifiedMissingPayload(t *testing.T) {
	for _, tc := range []struct {
		body  string
		valid bool
	}{{`{"tmc_messages_consume_response":{"messages":{"tmc_message":[]}}}`, true}, {`{"tmc_messages_consume_response":{}}`, false}, {`{"tmc_messages_consume_response":{"messages":null}}`, false}, {`{"tmc_messages_consume_response":{"messages":{"tmc_message":null}}}`, false}} {
		u := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(tc.body)) }))
		c, _ := New(Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: u.URL})
		out, e := c.Consume(context.Background())
		u.Close()
		if tc.valid && (e != nil || len(out) != 0) {
			t.Fatal(out, e)
		}
		if !tc.valid && e == nil {
			t.Fatal("missing payload reported successful empty poll")
		}
	}
}
func TestMissingItemFactsCannotBecomeZeroStockOrEmptyCatalogue(t *testing.T) {
	for _, body := range []string{`{"items_onsale_get_response":{}}`, `{"items_onsale_get_response":{"total_results":1,"items":{"item":[{"num_iid":1,"title":"item","price":"5.00","approve_status":"onsale"}]}}}`, `{"items_onsale_get_response":{"total_results":1,"items":{"item":[{"num_iid":1,"title":"item","price":"NaN","num":5,"approve_status":"onsale"}]}}}`} {
		u := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(body)) }))
		c, _ := New(Config{AppKey: "test-key", AppSecret: "test-secret", Session: "test-session", Gateway: u.URL})
		_, e := c.Items(context.Background(), 1, 20)
		u.Close()
		if e == nil {
			t.Fatal("missing/malformed requested product facts accepted")
		}
	}
}
