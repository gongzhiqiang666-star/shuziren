package api

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/deepseek"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
)

const testToken = "local-test-token-01234567890123456789"

func request(r http.Handler, method, path, body, token string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	out := httptest.NewRecorder()
	r.ServeHTTP(out, req)
	return out
}
func TestAllAPIRoutesFailClosedAndDoNotEnableCORS(t *testing.T) {
	r := Router(&Service{}, testToken, "")
	for _, path := range []string{"/api/v1/status", "/api/v1/shops", "/api/v1/missing", "/api/v1", "/api/v1/jobs/anything/audio"} {
		for _, method := range []string{"GET", "POST", "OPTIONS", "DELETE"} {
			out := request(r, method, path, "{}", "")
			if out.Code != 401 || strings.Contains(out.Body.String(), testToken) {
				t.Fatalf("unauthenticated %s %s returned %d", method, path, out.Code)
			}
			if out.Header().Get("Access-Control-Allow-Origin") != "" {
				t.Fatal("broad CORS enabled")
			}
		}
	}
	if out := request(r, "GET", "/healthz", "", ""); out.Code != 200 || strings.Contains(out.Body.String(), "postgres") {
		t.Fatal("liveness leaks configuration")
	}
	if out := request(r, "GET", "/api/v1/missing", "", testToken); out.Code != 404 {
		t.Fatalf("authenticated unknown route: %d", out.Code)
	}
	if out := request(r, "DELETE", "/api/v1/shops", "", testToken); out.Code != 405 {
		t.Fatalf("authenticated unsupported method: %d", out.Code)
	}
	if out := request(r, "GET", "/api/v1/shops", "", testToken+"bad"); out.Code != 401 {
		t.Fatal("invalid bearer accepted")
	}
}
func TestHTTPValidationPrecedesDatabaseAccess(t *testing.T) {
	r := Router(&Service{}, testToken, "")
	for _, tc := range []struct{ method, path, body string }{{"POST", "/api/v1/shops", `{"name":"x","admin":true}`}, {"POST", "/api/v1/shops", `{"name":"x"} {}`}, {"POST", "/api/v1/shops", `{"name":123}`}, {"GET", "/api/v1/products?shop_id=../secret", ""}, {"POST", "/api/v1/jobs/manual", `{"shop_id":"bad","session_id":"bad","product_id":"bad","text":"hi"}`}} {
		if out := request(r, tc.method, tc.path, tc.body, testToken); out.Code != 400 {
			t.Fatalf("validation failed: %s %d %s", tc.path, out.Code, out.Body.String())
		}
	}
}

type fakeMedia struct {
	tts, live                                    bool
	started, release                             chan struct{}
	sendCount, stopCount, synthCount, offerCount atomic.Int32
	stopErr, errorSend                           error
	mu                                           sync.Mutex
	lastAudio                                    []byte
}

func (m *fakeMedia) TTSConfigured() bool  { return m.tts }
func (m *fakeMedia) LiveConfigured() bool { return m.live }
func (m *fakeMedia) Synthesize(ctx context.Context, text string) ([]byte, error) {
	m.synthCount.Add(1)
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	return testWAV(), nil
}
func (m *fakeMedia) Negotiate(ctx context.Context, o media.Offer) (media.Answer, error) {
	m.offerCount.Add(1)
	return media.Answer{SDP: "v=0\r\nmock", Type: "answer", SessionID: "verified-media-id"}, nil
}
func (m *fakeMedia) SendAudio(ctx context.Context, id string, wav []byte) error {
	m.sendCount.Add(1)
	m.mu.Lock()
	m.lastAudio = append([]byte(nil), wav...)
	m.mu.Unlock()
	if m.started != nil {
		select {
		case m.started <- struct{}{}:
		default:
		}
	}
	if m.release != nil {
		select {
		case <-m.release:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	return m.errorSend
}
func (m *fakeMedia) Interrupt(context.Context, string) error { m.stopCount.Add(1); return m.stopErr }
func testWAV() []byte {
	var b bytes.Buffer
	b.WriteString("RIFF")
	_ = binary.Write(&b, binary.LittleEndian, uint32(36+320))
	b.WriteString("WAVEfmt ")
	_ = binary.Write(&b, binary.LittleEndian, uint32(16))
	_ = binary.Write(&b, binary.LittleEndian, uint16(1))
	_ = binary.Write(&b, binary.LittleEndian, uint16(1))
	_ = binary.Write(&b, binary.LittleEndian, uint32(16000))
	_ = binary.Write(&b, binary.LittleEndian, uint32(32000))
	_ = binary.Write(&b, binary.LittleEndian, uint16(2))
	_ = binary.Write(&b, binary.LittleEndian, uint16(16))
	b.WriteString("data")
	_ = binary.Write(&b, binary.LittleEndian, uint32(320))
	b.Write(make([]byte, 320))
	return b.Bytes()
}

func serviceFixture(t *testing.T, m *fakeMedia) (*Service, domain.Shop, domain.Product, domain.Session) {
	t.Helper()
	st, _ := testutil.Postgres(t)
	svc, err := New(st, m, nil, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	shop, err := st.CreateShop(ctx, "本地测试店")
	if err != nil {
		t.Fatal(err)
	}
	p, err := st.SaveProduct(ctx, domain.Product{ShopID: shop.ID, Title: "保温杯", SKU: "TEST-SKU", PriceCents: 9900, Stock: 10, Active: true}, true)
	if err != nil {
		t.Fatal(err)
	}
	session, err := st.CreateSession(ctx, shop.ID, "测试场次")
	if err != nil {
		t.Fatal(err)
	}
	return svc, shop, p, session
}
func readyJob(t *testing.T, s *Service, shop domain.Shop, p domain.Product, session domain.Session) domain.Job {
	t.Helper()
	ctx := context.Background()
	j, err := s.Manual(ctx, shop.ID, session.ID, p.ID, "这款杯子99元。")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.Approve(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.QueueSynthesis(ctx, shop.ID, j.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.ClaimNext(ctx); err != nil {
		t.Fatal(err)
	}
	if err = s.writeAudio(j.ID, testWAV()); err != nil {
		t.Fatal(err)
	}
	j, err = s.Store.FinishSynthesis(ctx, shop.ID, j.ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.BindMedia(ctx, shop.ID, session.ID, session.Epoch, "verified-media-id"); err != nil {
		t.Fatal(err)
	}
	return j
}
func waitFor(t *testing.T, predicate func() bool) {
	t.Helper()
	deadline := time.NewTimer(5 * time.Second)
	defer deadline.Stop()
	ticker := time.NewTicker(5 * time.Millisecond)
	defer ticker.Stop()
	for {
		if predicate() {
			return
		}
		select {
		case <-deadline.C:
			t.Fatal("timed out waiting for state")
		case <-ticker.C:
		}
	}
}

func TestPostgresWorkerPersistsRealBytesAndAuthenticatedAudio(t *testing.T) {
	m := &fakeMedia{tts: true, live: true}
	s, shop, p, session := serviceFixture(t, m)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { defer close(done); s.RunWorker(ctx) }()
	defer func() { cancel(); <-done }()
	j, err := s.Manual(ctx, shop.ID, session.ID, p.ID, "这款杯子99元。")
	if err != nil {
		t.Fatal(err)
	}
	r := Router(s, testToken, "")
	body := `{"shop_id":"` + shop.ID + `"}`
	if out := request(r, "POST", "/api/v1/jobs/"+j.ID+"/approve", body, testToken); out.Code != 200 {
		t.Fatal(out.Body.String())
	}
	if out := request(r, "POST", "/api/v1/jobs/"+j.ID+"/synthesize", body, testToken); out.Code != 200 {
		t.Fatal(out.Body.String())
	}
	waitFor(t, func() bool {
		current, e := s.Store.GetJob(ctx, shop.ID, j.ID)
		return e == nil && current.Status == "ready"
	})
	path := "/api/v1/jobs/" + j.ID + "/audio?shop_id=" + shop.ID
	if out := request(r, "GET", path, "", ""); out.Code != 401 {
		t.Fatal("audio accessible without bearer")
	}
	if out := request(r, "GET", path, "", testToken); out.Code != 200 || !bytes.Equal(out.Body.Bytes(), testWAV()) {
		t.Fatal("preview bytes differ from persisted synthesis")
	}
	if _, err = s.Store.BindMedia(ctx, shop.ID, session.ID, session.Epoch, "verified-media-id"); err != nil {
		t.Fatal(err)
	}
	if out := request(r, "POST", "/api/v1/jobs/"+j.ID+"/send", body, testToken); out.Code != 200 || !strings.Contains(out.Body.String(), `"status":"sent"`) {
		t.Fatal(out.Body.String())
	}
	if out := request(r, "POST", "/api/v1/jobs/"+j.ID+"/send", body, testToken); out.Code != 409 {
		t.Fatal("already sent audio was replayed")
	}
	m.mu.Lock()
	same := bytes.Equal(m.lastAudio, testWAV())
	m.mu.Unlock()
	if !same || m.synthCount.Load() != 1 || m.sendCount.Load() != 1 {
		t.Fatal("TTS output was regenerated or replayed")
	}
	other, err := s.Store.CreateShop(ctx, "其他店")
	if err != nil {
		t.Fatal(err)
	}
	if out := request(r, "GET", "/api/v1/jobs/"+j.ID+"/audio?shop_id="+other.ID, "", testToken); out.Code != 404 {
		t.Fatal("cross-shop audio exposed")
	}
}

func TestPostgresTakeoverOrdersLateSendBeforeStopAndRejectsReplay(t *testing.T) {
	m := &fakeMedia{tts: true, live: true, started: make(chan struct{}, 1), release: make(chan struct{})}
	s, shop, p, session := serviceFixture(t, m)
	j := readyJob(t, s, shop, p, session)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	first := make(chan domain.Job, 1)
	errs := make(chan error, 3)
	go func() { job, e := s.Send(ctx, shop.ID, j.ID); first <- job; errs <- e }()
	select {
	case <-m.started:
	case <-ctx.Done():
		t.Fatal("send did not start")
	}
	stopped := make(chan TakeoverResult, 1)
	go func() { result, e := s.Takeover(ctx, shop.ID, session.ID, "takeover"); stopped <- result; errs <- e }()
	waitFor(t, func() bool {
		p, e := s.Store.GetSession(ctx, shop.ID, session.ID)
		return e == nil && p.Status == "paused" && p.Epoch == 2
	})
	retry := make(chan error, 1)
	go func() { _, e := s.Send(ctx, shop.ID, j.ID); retry <- e }()
	close(m.release)
	if err := <-errs; err != nil {
		t.Fatal(err)
	}
	if err := <-errs; err != nil {
		t.Fatal(err)
	}
	result := <-stopped
	if result.MediaStopStatus != "sent" || result.Session.Status != "paused" {
		t.Fatal("takeover did not stop the correct local session")
	}
	if job := <-first; job.Status != "delivery_unknown" {
		t.Fatalf("late success overwrote takeover: %s", job.Status)
	}
	if err := <-retry; err == nil {
		t.Fatal("late retry was dispatched")
	}
	if m.sendCount.Load() != 1 || m.stopCount.Load() != 1 {
		t.Fatal("unexpected duplicate dispatch or stop")
	}
}

func TestPostgresEndExposesFailedMediaStopAndPersistsEnded(t *testing.T) {
	m := &fakeMedia{live: true, stopErr: errors.New("upstream private error must not leak")}
	s, shop, _, session := serviceFixture(t, m)
	if _, err := s.Store.BindMedia(context.Background(), shop.ID, session.ID, session.Epoch, "verified-media-id"); err != nil {
		t.Fatal(err)
	}
	out := request(Router(s, testToken, ""), "POST", "/api/v1/sessions/"+session.ID+"/end", `{"shop_id":"`+shop.ID+`"}`, testToken)
	var body struct {
		Data TakeoverResult `json:"data"`
	}
	if out.Code != 200 || json.Unmarshal(out.Body.Bytes(), &body) != nil || body.Data.Session.Status != "ended" || body.Data.MediaStopStatus != "failed" {
		t.Fatalf("stop failure hidden: %d %s", out.Code, out.Body.String())
	}
	if strings.Contains(out.Body.String(), "private error") {
		t.Fatal("upstream error leaked")
	}
	current, err := s.Store.GetSession(context.Background(), shop.ID, session.ID)
	if err != nil || current.Status != "ended" || current.Epoch != 2 {
		t.Fatal("local end was not committed")
	}
}

func TestPostgresReconnectOnlyIgnoresDefiniteMissingUpstreamSession(t *testing.T) {
	m := &fakeMedia{live: true, stopErr: media.ErrSessionNotFound}
	s, shop, _, session := serviceFixture(t, m)
	ctx := context.Background()
	if _, err := s.Store.BindMedia(ctx, shop.ID, session.ID, session.Epoch, "old-closed-session"); err != nil {
		t.Fatal(err)
	}
	answer, err := s.Negotiate(ctx, shop.ID, session.ID, media.Offer{SDP: "v=0\r\nmock", Type: "offer"})
	if err != nil || answer.SessionID != "verified-media-id" || m.offerCount.Load() != 1 {
		t.Fatalf("definite missing session blocked reconnect: %v", err)
	}
	current, err := s.Store.GetSession(ctx, shop.ID, session.ID)
	if err != nil || current.MediaSessionID == nil || *current.MediaSessionID != "verified-media-id" {
		t.Fatal("new media session was not persisted")
	}
	m.stopErr = media.ErrUpstream
	if _, err = s.Negotiate(ctx, shop.ID, session.ID, media.Offer{SDP: "v=0\r\nmock", Type: "offer"}); err == nil || m.offerCount.Load() != 1 {
		t.Fatal("ambiguous stop was incorrectly ignored")
	}
	m.stopErr = media.ErrSessionNotFound
	result, err := s.Takeover(ctx, shop.ID, session.ID, "end")
	if err != nil || result.Session.Status != "ended" || result.MediaStopStatus != "not_connected" {
		t.Fatalf("nonexistent media was falsely marked as stop sent: %v", err)
	}
}

type blockedGenerator struct{ started, release chan struct{} }

func (g *blockedGenerator) Configured() bool { return true }
func (g *blockedGenerator) Model() string    { return "test-only" }
func (g *blockedGenerator) Generate(ctx context.Context, s domain.Snapshot, q string) (deepseek.Result, error) {
	close(g.started)
	select {
	case <-g.release:
		return deepseek.Result{Answer: "99元"}, nil
	case <-ctx.Done():
		return deepseek.Result{}, ctx.Err()
	}
}
func TestPostgresLateGenerationRechecksProductVersion(t *testing.T) {
	s, shop, p, session := serviceFixture(t, &fakeMedia{})
	g := &blockedGenerator{make(chan struct{}), make(chan struct{})}
	s.Generator = g
	ctx := context.Background()
	result := make(chan error, 1)
	go func() { _, err := s.Generate(ctx, shop.ID, session.ID, p.ID, "多少钱？"); result <- err }()
	<-g.started
	p.PriceCents = 10900
	if _, err := s.Store.SaveProduct(ctx, p, false); err != nil {
		t.Fatal(err)
	}
	close(g.release)
	var d *domain.Error
	if err := <-result; !errors.As(err, &d) || d.Code != "stale_product" {
		t.Fatalf("late completion accepted: %v", err)
	}
	jobs, err := s.Store.ListJobs(ctx, shop.ID, session.ID)
	if err != nil || len(jobs) != 0 {
		t.Fatal("stale model reply saved")
	}
}

func TestPostgresAmbiguousSendRemainsUnknownAndCannotRetry(t *testing.T) {
	m := &fakeMedia{live: true, errorSend: context.DeadlineExceeded}
	s, shop, p, session := serviceFixture(t, m)
	j := readyJob(t, s, shop, p, session)
	result, err := s.Send(context.Background(), shop.ID, j.ID)
	if err != nil || result.Status != "delivery_unknown" {
		t.Fatalf("ambiguous send was not persisted: %v", err)
	}
	if _, err = s.Send(context.Background(), shop.ID, j.ID); err == nil {
		t.Fatal("ambiguous media delivery retried")
	}
	if m.sendCount.Load() != 1 {
		t.Fatal("duplicate outbound request")
	}
}

func TestPostgresUnconfirmedSynthesisWriteKeepsCommittedAudio(t *testing.T) {
	s, shop, p, session := serviceFixture(t, &fakeMedia{})
	ready := readyJob(t, s, shop, p, session)
	// Emulate a subsequent writeback attempt whose request context has already
	// failed. The earlier ready commit must not be overwritten or lose its WAV.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	s.completeSynthesis(ctx, ready)
	current, err := s.Store.GetJob(context.Background(), shop.ID, ready.ID)
	if err != nil || current.Status != "ready" || !current.AudioReady {
		t.Fatal("unconfirmed writeback damaged committed ready state")
	}
	wav, err := s.readAudio(ready.ID)
	if err != nil || !bytes.Equal(wav, testWAV()) {
		t.Fatal("unconfirmed writeback deleted committed WAV")
	}
	// If the commit never happened, only the still-synthesizing row is failed;
	// no synthesis or delivery is repeated and the diagnostic WAV is retained.
	pending, err := s.Manual(context.Background(), shop.ID, session.ID, p.ID, "另一个草稿")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.Approve(context.Background(), shop.ID, pending.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.QueueSynthesis(context.Background(), shop.ID, pending.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Store.ClaimNext(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err = s.writeAudio(pending.ID, testWAV()); err != nil {
		t.Fatal(err)
	}
	s.completeSynthesis(ctx, pending)
	current, err = s.Store.GetJob(context.Background(), shop.ID, pending.ID)
	if err != nil || current.Status != "failed" || current.AudioReady {
		t.Fatal("unfinished synthesis did not converge to explicit-retry failure")
	}
	if _, err = s.readAudio(pending.ID); err != nil {
		t.Fatal("ambiguous WAV unexpectedly removed")
	}
}

// Compile-time checks keep mocks and the actual adapter on one frozen contract.
var _ Media = (*media.Client)(nil)
