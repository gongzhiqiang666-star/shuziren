package api

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/testutil"
	"github.com/jackc/pgx/v5"
)

func outputFixture(t *testing.T, m Media) (*Service, *pgx.Conn, domain.Shop, domain.Product, domain.Session) {
	t.Helper()
	st, db := testutil.Postgres(t)
	s, err := New(st, m, nil, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	shop, err := st.CreateShop(ctx, "独立输出测试")
	if err != nil {
		t.Fatal(err)
	}
	p, err := st.SaveProduct(ctx, domain.Product{ShopID: shop.ID, Title: "保温杯", SKU: "OUTPUT-1", Active: true, PriceCents: 9900, Stock: 10}, true)
	if err != nil {
		t.Fatal(err)
	}
	session, err := st.CreateSession(ctx, shop.ID, "输出场次")
	if err != nil {
		t.Fatal(err)
	}
	return s, db, shop, p, session
}
func issuedOutput(t *testing.T, s *Service, shop domain.Shop, session domain.Session) (OutputIssueResult, domain.OutputAuth) {
	t.Helper()
	issued, err := s.IssueOutput(context.Background(), shop.ID, session.ID)
	if err != nil {
		t.Fatal(err)
	}
	hash, valid := outputTokenHash(issued.Token)
	if !valid {
		t.Fatal("invalid token encoding")
	}
	auth, err := s.Store.AuthenticateOutput(context.Background(), hash)
	if err != nil {
		t.Fatal(err)
	}
	return issued, auth
}
func outputReadyJob(t *testing.T, s *Service, shop domain.Shop, p domain.Product, session domain.Session) domain.Job {
	t.Helper()
	ctx := context.Background()
	j, err := s.Manual(ctx, shop.ID, session.ID, p.ID, "保温杯99元。")
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
	return j
}
func connectedOutput(t *testing.T, s *Service, a domain.OutputAuth, receiver string) OutputOfferResult {
	t.Helper()
	r, err := s.OfferOutput(context.Background(), a, receiver, media.Offer{SDP: "v=0\r\nmock", Type: "offer"})
	if err != nil {
		t.Fatal(err)
	}
	status, err := s.Store.HeartbeatOutput(context.Background(), a, domain.OutputHeartbeat{ReceiverID: receiver, LeaseID: r.LeaseID, PeerState: "connected", VideoReady: true, AudioReady: true})
	if err != nil || !status.Online {
		t.Fatalf("heartbeat did not establish reported readiness: %v", err)
	}
	return r
}

func TestPostgresOutputTokenScopeAndSingleReceiver(t *testing.T) {
	m := &fakeMedia{live: true}
	s, _, shop, _, session := outputFixture(t, m)
	ctx := context.Background()
	issued, a := issuedOutput(t, s, shop, session)
	if strings.Contains(issued.OutputPath, testToken) || !strings.HasPrefix(issued.OutputPath, "/output#token=out_") || strings.Contains(issued.OutputPath, "?") {
		t.Fatal("unsafe output link")
	}
	r := Router(s, testToken, "")
	receiver := domain.NewID()
	for _, tc := range []struct {
		path, token string
		code        int
	}{{"/api/v1/shops", issued.Token, 401}, {"/output-api/v1/status?receiver_id=" + receiver, testToken, 401}, {"/output-api/v1/status?receiver_id=" + receiver + "&token=" + issued.Token, "", 401}, {"/output-api/v1/shops", issued.Token, 404}, {"/output-api/v1/status?receiver_id=" + receiver, issued.Token, 200}} {
		out := request(r, "GET", tc.path, "", tc.token)
		if out.Code != tc.code {
			t.Fatalf("scope %s: %d %s", tc.path, out.Code, out.Body.String())
		}
	}
	offer, err := s.OfferOutput(ctx, a, receiver, media.Offer{SDP: "v=0\r\nmock", Type: "offer"})
	if err != nil || offer.Output.Online {
		t.Fatal("offer alone incorrectly establishes online")
	}
	for _, other := range []string{receiver, domain.NewID()} {
		if _, err = s.OfferOutput(ctx, a, other, media.Offer{SDP: "v=0\r\nmock", Type: "offer"}); err == nil {
			t.Fatal("second receiver replaced live lease")
		}
	}
	if m.offerCount.Load() != 1 {
		t.Fatal("second upstream peer was created")
	}
	owned, err := s.Store.GetScopedOutput(ctx, a, receiver)
	if err != nil || owned.LeaseID == nil || *owned.LeaseID != offer.LeaseID {
		t.Fatal("lost-answer owner cannot discover its own lease")
	}
	other, err := s.Store.GetScopedOutput(ctx, a, domain.NewID())
	if err != nil || other.LeaseID != nil || other.LeaseOwned {
		t.Fatal("lease owner identity leaked to another page")
	}
	if _, err = s.Store.BindMedia(ctx, shop.ID, session.ID, session.Epoch, "management-preview"); err == nil {
		t.Fatal("legacy preview replaced independent output")
	}
	if _, _, err = s.Store.ReleaseOutput(ctx, a, domain.NewID(), offer.LeaseID); err == nil {
		t.Fatal("another receiver released the current lease")
	}
}

func TestPostgresOutputSendRequiresActualReadyHeartbeatAndExpires(t *testing.T) {
	m := &fakeMedia{live: true}
	s, db, shop, p, session := outputFixture(t, m)
	ctx := context.Background()
	j := outputReadyJob(t, s, shop, p, session)
	_, a := issuedOutput(t, s, shop, session)
	receiver := domain.NewID()
	off, err := s.OfferOutput(ctx, a, receiver, media.Offer{SDP: "v=0\r\nmock", Type: "offer"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Send(ctx, shop.ID, j.ID); err == nil {
		t.Fatal("offer without connected heartbeat permitted send")
	}
	h := domain.OutputHeartbeat{ReceiverID: receiver, LeaseID: off.LeaseID, PeerState: "connected", VideoReady: true}
	status, err := s.Store.HeartbeatOutput(ctx, a, h)
	if err != nil || status.Online {
		t.Fatal("blocked audio autoplay was called online")
	}
	if _, err = s.Send(ctx, shop.ID, j.ID); err == nil {
		t.Fatal("muted or autoplay-blocked output permitted send")
	}
	h.AudioReady = true
	status, err = s.Store.HeartbeatOutput(ctx, a, h)
	if err != nil || !status.Online {
		t.Fatal("valid connected heartbeat rejected")
	}
	result, err := s.Send(ctx, shop.ID, j.ID)
	if err != nil || result.Status != "sent" || m.sendCount.Load() != 1 {
		t.Fatalf("connected lease cannot send: %v", err)
	}
	j = outputReadyJob(t, s, shop, p, session)
	if _, err = db.Exec(ctx, "UPDATE session_outputs SET lease_expires_at=now()-interval '1 second' WHERE session_id=$1", session.ID); err != nil {
		t.Fatal(err)
	}
	status, err = s.Store.GetScopedOutput(ctx, a, receiver)
	if err != nil || status.Online || status.LeaseID != nil {
		t.Fatal("expired receiver remained online")
	}
	if _, err = s.Store.HeartbeatOutput(ctx, a, h); err == nil {
		t.Fatal("late heartbeat resurrected expired lease")
	}
	if _, err = s.Send(ctx, shop.ID, j.ID); err == nil || m.sendCount.Load() != 1 {
		t.Fatal("expired receiver accepted media dispatch")
	}
}

func TestPostgresOutputRestartTakeoverAndRevocation(t *testing.T) {
	m := &fakeMedia{live: true}
	s, _, shop, _, session := outputFixture(t, m)
	ctx := context.Background()
	issued, a := issuedOutput(t, s, shop, session)
	receiver := domain.NewID()
	off := connectedOutput(t, s, a, receiver)
	if _, err := s.Store.SaveOutputConfig(ctx, shop.ID, session.ID, domain.OutputConfig{Width: 1920, Height: 1080, Fit: "cover", Background: "#000000"}); err != nil {
		t.Fatal(err)
	}
	if err := s.Store.Recover(ctx); err != nil {
		t.Fatal(err)
	}
	after, err := s.Store.GetScopedOutput(ctx, a, receiver)
	if err != nil || after.Online || after.LeaseID != nil || after.Config.Width != 1920 {
		t.Fatal("restart restored a stale online state or lost config")
	}
	if _, err = s.Store.HeartbeatOutput(ctx, a, domain.OutputHeartbeat{ReceiverID: receiver, LeaseID: off.LeaseID, PeerState: "connected", VideoReady: true, AudioReady: true}); err == nil {
		t.Fatal("pre-restart lease was renewed")
	}
	off = connectedOutput(t, s, a, receiver)
	paused, err := s.Takeover(ctx, shop.ID, session.ID, "takeover")
	if err != nil || paused.Session.Status != "paused" {
		t.Fatal(err)
	}
	after, err = s.Store.GetScopedOutput(ctx, a, receiver)
	if err != nil || after.State != "paused" || after.Online || after.LeaseID != nil {
		t.Fatal("takeover did not invalidate output lease")
	}
	if _, err = s.OfferOutput(ctx, a, receiver, media.Offer{SDP: "v=0\r\nmock", Type: "offer"}); err == nil {
		t.Fatal("paused output could reconnect")
	}
	if _, err = s.Resume(ctx, shop.ID, session.ID); err != nil {
		t.Fatal(err)
	}
	connectedOutput(t, s, a, receiver)
	m.stopErr = errors.New("private upstream failure")
	revoked, err := s.RevokeOutput(ctx, shop.ID, session.ID)
	if err != nil || revoked.Output.Enabled || revoked.MediaStopStatus != "failed" || revoked.Output.SessionStatus != "paused" {
		t.Fatal("revoke hid stop failure")
	}
	hash, _ := outputTokenHash(issued.Token)
	if _, err = s.Store.AuthenticateOutput(ctx, hash); err == nil {
		t.Fatal("revoked token remained authorized")
	}
	current, err := s.Store.GetSession(ctx, shop.ID, session.ID)
	if err != nil || current.MediaSessionID != nil {
		t.Fatal("revoked media binding remained usable after resume")
	}
}

type delayedOfferMedia struct {
	*fakeMedia
	entered, release chan struct{}
}

func (m *delayedOfferMedia) Negotiate(ctx context.Context, o media.Offer) (media.Answer, error) {
	m.offerCount.Add(1)
	close(m.entered)
	<-m.release
	return media.Answer{SDP: "v=0\r\nlate", Type: "answer", SessionID: "late-upstream-session"}, nil
}
func TestPostgresRevokeFencesAnInflightOutputOffer(t *testing.T) {
	m := &delayedOfferMedia{fakeMedia: &fakeMedia{live: true}, entered: make(chan struct{}), release: make(chan struct{})}
	s, _, shop, _, session := outputFixture(t, m)
	_, a := issuedOutput(t, s, shop, session)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	offerErr := make(chan error, 1)
	go func() {
		_, err := s.OfferOutput(ctx, a, domain.NewID(), media.Offer{SDP: "v=0\r\nmock", Type: "offer"})
		offerErr <- err
	}()
	<-m.entered
	revoked := make(chan error, 1)
	go func() { _, err := s.RevokeOutput(ctx, shop.ID, session.ID); revoked <- err }()
	waitFor(t, func() bool {
		v, e := s.Store.GetOutput(ctx, shop.ID, session.ID, "")
		return e == nil && !v.Enabled && v.SessionStatus == "paused"
	})
	close(m.release)
	if err := <-offerErr; err == nil {
		t.Fatal("late offer was bound after revoke")
	}
	if err := <-revoked; err != nil {
		t.Fatal(err)
	}
	p, err := s.Store.GetSession(ctx, shop.ID, session.ID)
	if err != nil || p.MediaSessionID != nil || m.stopCount.Load() == 0 {
		t.Fatal("late upstream peer was not fenced and cleaned up")
	}
}

func TestPostgresIssueFencesAnInflightManagementPreview(t *testing.T) {
	m := &delayedOfferMedia{fakeMedia: &fakeMedia{live: true}, entered: make(chan struct{}), release: make(chan struct{})}
	s, _, shop, _, session := outputFixture(t, m)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	preview := make(chan error, 1)
	go func() {
		_, err := s.Negotiate(ctx, shop.ID, session.ID, media.Offer{SDP: "v=0\r\nmock", Type: "offer"})
		preview <- err
	}()
	<-m.entered
	issued := make(chan error, 1)
	go func() { _, err := s.IssueOutput(ctx, shop.ID, session.ID); issued <- err }()
	waitFor(t, func() bool { v, e := s.Store.GetOutput(ctx, shop.ID, session.ID, ""); return e == nil && v.Enabled })
	close(m.release)
	if err := <-preview; err == nil {
		t.Fatal("in-flight preview replaced the new output owner")
	}
	if err := <-issued; err != nil {
		t.Fatal(err)
	}
	p, err := s.Store.GetSession(ctx, shop.ID, session.ID)
	if err != nil || p.MediaSessionID != nil {
		t.Fatal("management preview bound after output enable")
	}
}

func TestOutputHTTPShapeDoesNotReturnTokenAgain(t *testing.T) {
	s, _, shop, _, session := outputFixture(t, &fakeMedia{live: true})
	r := Router(s, testToken, "")
	body := `{"shop_id":"` + shop.ID + `"}`
	out := request(r, "POST", "/api/v1/sessions/"+session.ID+"/output/issue", body, testToken)
	var v struct {
		Data OutputIssueResult `json:"data"`
	}
	if out.Code != 200 || json.Unmarshal(out.Body.Bytes(), &v) != nil || v.Data.Token == "" {
		t.Fatal(out.Body.String())
	}
	out = request(r, "GET", "/api/v1/sessions/"+session.ID+"/output?shop_id="+shop.ID, "", testToken)
	if out.Code != 200 || strings.Contains(out.Body.String(), v.Data.Token) || strings.Contains(out.Body.String(), "token_hash") {
		t.Fatal("status exposed output credential")
	}
}
