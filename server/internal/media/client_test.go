package media

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const testToken = "test-only-token-32-characters-long"
const testSessionID = "cb0c223c-e902-423d-8c5b-94e2c30f3d31"
const testSDP = "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"

func testWAV() []byte {
	data := make([]byte, 44+32)
	copy(data, "RIFF")
	binary.LittleEndian.PutUint32(data[4:], uint32(len(data)-8))
	copy(data[8:], "WAVEfmt ")
	binary.LittleEndian.PutUint32(data[16:], 16)
	binary.LittleEndian.PutUint16(data[20:], 1)
	binary.LittleEndian.PutUint16(data[22:], 1)
	binary.LittleEndian.PutUint32(data[24:], 24000)
	binary.LittleEndian.PutUint32(data[28:], 48000)
	binary.LittleEndian.PutUint16(data[32:], 2)
	binary.LittleEndian.PutUint16(data[34:], 16)
	copy(data[36:], "data")
	binary.LittleEndian.PutUint32(data[40:], 32)
	binary.LittleEndian.PutUint16(data[44:], 8000)
	return data
}

func mustClient(t *testing.T, config Config) *Client {
	t.Helper()
	c, err := New(config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.http.CloseIdleConnections)
	return c
}

func TestMissingAndInvalidConfiguration(t *testing.T) {
	c := mustClient(t, Config{})
	if c.TTSConfigured() || c.LiveConfigured() {
		t.Fatal("disabled service reported configured")
	}
	_, err := c.Synthesize(context.Background(), "hello")
	if !errors.Is(err, ErrNotConfigured) {
		t.Fatalf("synthesize: %v", err)
	}
	_, err = c.Negotiate(context.Background(), Offer{SDP: testSDP, Type: "offer"})
	if !errors.Is(err, ErrNotConfigured) {
		t.Fatalf("offer: %v", err)
	}
	if !errors.Is(c.SendAudio(context.Background(), testSessionID, testWAV()), ErrNotConfigured) ||
		!errors.Is(c.Interrupt(context.Background(), testSessionID), ErrNotConfigured) {
		t.Fatal("disabled live service did not report ErrNotConfigured")
	}
	configs := []Config{
		{TTSBaseURL: "http://localhost:8080"},
		{TTSAPIKey: testToken},
		{TTSBaseURL: "http://localhost:8080", TTSAPIKey: "short"},
		{TTSBaseURL: "http://localhost:8080", TTSAPIKey: testToken + "\r\n"},
		{LiveTalkingBaseURL: "file:///tmp/audio"},
		{LiveTalkingBaseURL: "http://user:never-expose-this@localhost"},
		{LiveTalkingBaseURL: "http://localhost?key=never-expose-this"},
		{LiveTalkingBaseURL: "http://localhost#secret"},
		{LiveTalkingBaseURL: "http://localhost/base/../escape"},
		{LiveTalkingBaseURL: " http://localhost"},
		{LiveTalkingBaseURL: "http://localhost/%2fescape"},
		{LiveTalkingBaseURL: "http://localhost:65536"},
		{LiveTalkingBaseURL: "http://localhost:0"},
	}
	for _, cfg := range configs {
		_, err := New(cfg)
		if !errors.Is(err, ErrInvalidConfig) {
			t.Errorf("expected invalid config, got %v", err)
		}
		if err != nil && strings.Contains(err.Error(), "never-expose-this") {
			t.Fatal("configuration error exposed credentials")
		}
	}
}

func TestSynthesizeAndUploadExactSameAudio(t *testing.T) {
	wav := testWAV()
	var synthesized, uploaded atomic.Int32
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method %s", r.Method)
		}
		switch r.URL.Path {
		case "/tts/synthesize":
			synthesized.Add(1)
			if r.Header.Get("Authorization") != "Bearer "+testToken {
				t.Error("missing TTS authentication")
			}
			var req struct{ Text string }
			if json.NewDecoder(r.Body).Decode(&req) != nil || req.Text != "这款商品有两种规格。" {
				t.Error("incorrect synthesis text")
			}
			w.Header().Set("Content-Type", "audio/wav")
			_, _ = w.Write(wav)
		case "/live/humanaudio":
			uploaded.Add(1)
			if r.Header.Get("Authorization") != "" {
				t.Error("TTS credential leaked to LiveTalking")
			}
			if err := r.ParseMultipartForm(MaxAudioBytes + 1024); err != nil {
				t.Errorf("invalid multipart: %v", err)
				w.WriteHeader(400)
				return
			}
			defer r.MultipartForm.RemoveAll()
			if r.FormValue("sessionid") != testSessionID {
				t.Error("wrong string session ID")
			}
			file, header, err := r.FormFile("file")
			if err != nil {
				t.Error("missing file part")
				w.WriteHeader(400)
				return
			}
			defer file.Close()
			if header.Filename != "speech.wav" || header.Header.Get("Content-Type") != "audio/wav" {
				t.Error("wrong file metadata")
			}
			received, _ := io.ReadAll(file)
			if !bytes.Equal(received, wav) {
				t.Error("lip-driving upload changed the reviewed audio")
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = io.WriteString(w, `{"code":0,"msg":"ok"}`)
		default:
			w.WriteHeader(404)
		}
	}))
	defer upstream.Close()
	c := mustClient(t, Config{TTSBaseURL: upstream.URL + "/tts/", TTSAPIKey: testToken, LiveTalkingBaseURL: upstream.URL + "/live"})
	actual, err := c.Synthesize(context.Background(), "这款商品有两种规格。")
	if err != nil {
		t.Fatal(err)
	}
	if err := c.SendAudio(context.Background(), testSessionID, actual); err != nil {
		t.Fatal(err)
	}
	if synthesized.Load() != 1 || uploaded.Load() != 1 {
		t.Fatal("unexpected extra synthesis or upload")
	}
}

func TestNegotiateAndInterruptStringSession(t *testing.T) {
	var stopped atomic.Bool
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/offer":
			var offer Offer
			if json.NewDecoder(r.Body).Decode(&offer) != nil || offer.Type != "offer" || offer.SDP != testSDP {
				t.Error("wrong offer")
			}
			_ = json.NewEncoder(w).Encode(Answer{SDP: testSDP, Type: "answer", SessionID: testSessionID})
		case "/interrupt_talk":
			var req map[string]any
			if r.Header.Get("Content-Type") != "application/json" || json.NewDecoder(r.Body).Decode(&req) != nil || req["sessionid"] != testSessionID {
				t.Error("wrong interruption contract")
			}
			stopped.Store(true)
			_, _ = io.WriteString(w, `{"code":0}`)
		default:
			t.Errorf("unexpected endpoint %s", r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	defer upstream.Close()
	c := mustClient(t, Config{LiveTalkingBaseURL: upstream.URL})
	answer, err := c.Negotiate(context.Background(), Offer{SDP: testSDP, Type: "offer"})
	if err != nil || answer.SessionID != testSessionID || answer.Type != "answer" {
		t.Fatalf("answer %+v, err %v", answer, err)
	}
	if err := c.Interrupt(context.Background(), answer.SessionID); err != nil || !stopped.Load() {
		t.Fatalf("interrupt: %v", err)
	}
}

func TestUploadRejectsFailuresAndAmbiguousAcknowledgements(t *testing.T) {
	cases := []struct {
		name, body, contentType string
		status                  int
		want                    error
	}{
		{"upstream rejection", `{"code":-1,"msg":"token=secret"}`, "application/json", 200, ErrUpstream},
		{"http failure", `secret upstream body`, "text/plain", 503, ErrUpstream},
		{"missing code", `{"msg":"ok"}`, "application/json", 200, ErrInvalidResponse},
		{"null code", `{"code":null}`, "application/json", 200, ErrInvalidResponse},
		{"string code", `{"code":"0"}`, "application/json", 200, ErrInvalidResponse},
		{"extra JSON", `{"code":0}{"code":-1}`, "application/json", 200, ErrInvalidResponse},
		{"duplicate code", `{"code":-1,"code":0}`, "application/json", 200, ErrInvalidResponse},
		{"HTML success", `<html>ok</html>`, "text/html", 200, ErrInvalidResponse},
		{"empty", ``, "application/json", 200, ErrInvalidResponse},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = io.Copy(io.Discard, r.Body)
				w.Header().Set("Content-Type", tc.contentType)
				w.WriteHeader(tc.status)
				_, _ = io.WriteString(w, tc.body)
			}))
			defer upstream.Close()
			c := mustClient(t, Config{LiveTalkingBaseURL: upstream.URL})
			err := c.SendAudio(context.Background(), testSessionID, testWAV())
			if !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
			if strings.Contains(err.Error(), "secret") {
				t.Fatal("upstream body leaked in error")
			}
		})
	}
}

func TestRedirectNeverLeaksTextAudioOrCredentials(t *testing.T) {
	var leaked atomic.Int32
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { leaked.Add(1) }))
	defer target.Close()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, target.URL+"/collect", http.StatusTemporaryRedirect)
	}))
	defer upstream.Close()
	c := mustClient(t, Config{TTSBaseURL: upstream.URL, TTSAPIKey: testToken, LiveTalkingBaseURL: upstream.URL})
	if _, err := c.Synthesize(context.Background(), "private text"); !errors.Is(err, ErrUpstream) {
		t.Fatalf("synthesize: %v", err)
	}
	if err := c.SendAudio(context.Background(), testSessionID, testWAV()); !errors.Is(err, ErrUpstream) {
		t.Fatalf("upload: %v", err)
	}
	if leaked.Load() != 0 {
		t.Fatal("redirect target was contacted")
	}
}

func TestInterruptOnlyRecognizesVerifiedMissingSession(t *testing.T) {
	cases := []struct {
		name, body string
		status     int
		want       error
	}{
		{"explicit missing session", `{"code":-1,"msg":"session not found"}`, 200, ErrSessionNotFound},
		{"HTTP not found is not proof", `{"code":-1,"msg":"session not found"}`, 404, ErrUpstream},
		{"unknown code is not proof", `{"code":-2,"msg":"session not found"}`, 200, ErrUpstream},
		{"similar message is not proof", `{"code":-1,"msg":"Session not found"}`, 200, ErrUpstream},
		{"missing code is invalid", `{"msg":"session not found"}`, 200, ErrInvalidResponse},
		{"duplicate message is invalid", `{"code":-1,"msg":"failed","msg":"session not found"}`, 200, ErrInvalidResponse},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = io.Copy(io.Discard, r.Body)
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(tc.status)
				_, _ = io.WriteString(w, tc.body)
			}))
			defer upstream.Close()
			c := mustClient(t, Config{LiveTalkingBaseURL: upstream.URL})
			if err := c.Interrupt(context.Background(), testSessionID); !errors.Is(err, tc.want) {
				t.Fatalf("interrupt got %v, want %v", err, tc.want)
			}
			// Do not silently treat a rejected audio upload as an idempotent stop.
			if tc.want == ErrSessionNotFound {
				if err := c.SendAudio(context.Background(), testSessionID, testWAV()); !errors.Is(err, ErrUpstream) || errors.Is(err, ErrSessionNotFound) {
					t.Fatalf("upload misclassified: %v", err)
				}
			}
		})
	}
}

func TestCancellationAndDeadlinePreserved(t *testing.T) {
	started := make(chan struct{}, 2)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.Copy(io.Discard, r.Body)
		started <- struct{}{}
		<-r.Context().Done()
	}))
	defer upstream.Close()
	c := mustClient(t, Config{TTSBaseURL: upstream.URL, TTSAPIKey: testToken, LiveTalkingBaseURL: upstream.URL})
	ctx, cancel := context.WithCancel(context.Background())
	result := make(chan error, 1)
	go func() { result <- c.SendAudio(ctx, testSessionID, testWAV()) }()
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("upload did not start")
	}
	cancel()
	if err := <-result; !errors.Is(err, context.Canceled) {
		t.Fatalf("upload cancellation: %v", err)
	}
	deadline, end := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer end()
	if _, err := c.Synthesize(deadline, "hello"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("synthesis timeout: %v", err)
	}
}

func TestInvalidInputsNeverContactUpstream(t *testing.T) {
	var requests atomic.Int32
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { requests.Add(1) }))
	defer upstream.Close()
	c := mustClient(t, Config{TTSBaseURL: upstream.URL, TTSAPIKey: testToken, LiveTalkingBaseURL: upstream.URL})
	for _, text := range []string{"", "  \n", "bad\x00text", strings.Repeat("字", MaxTextRunes+1), string([]byte{0xff})} {
		if _, err := c.Synthesize(context.Background(), text); !errors.Is(err, ErrInvalidInput) {
			t.Fatalf("invalid text accepted: %v", err)
		}
	}
	if err := c.SendAudio(context.Background(), testSessionID, []byte("not a wave")); !errors.Is(err, ErrInvalidInput) {
		t.Fatal(err)
	}
	if err := c.Interrupt(context.Background(), "../bad\r\n"); !errors.Is(err, ErrInvalidInput) {
		t.Fatal(err)
	}
	if _, err := c.Negotiate(context.Background(), Offer{SDP: testSDP, Type: "answer"}); !errors.Is(err, ErrInvalidInput) {
		t.Fatal(err)
	}
	if requests.Load() != 0 {
		t.Fatal("invalid input sent upstream")
	}
}

func TestRejectMalformedOrOversizedWAV(t *testing.T) {
	cases := map[string][]byte{"JSON with wav type": []byte(`{"error":"not loaded"}`), "truncated": testWAV()[:50], "oversized": make([]byte, MaxAudioBytes+1)}
	badRate := testWAV()
	binary.LittleEndian.PutUint32(badRate[28:], 1)
	cases["invalid byte rate"] = badRate
	stereo := testWAV()
	binary.LittleEndian.PutUint16(stereo[22:], 2)
	cases["unexpected stereo"] = stereo
	badChunk := testWAV()
	binary.LittleEndian.PutUint32(badChunk[40:], ^uint32(0))
	cases["overflow chunk size"] = badChunk
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "audio/wav")
				_, _ = w.Write(body)
			}))
			defer upstream.Close()
			c := mustClient(t, Config{TTSBaseURL: upstream.URL, TTSAPIKey: testToken})
			if _, err := c.Synthesize(context.Background(), "hello"); !errors.Is(err, ErrInvalidResponse) {
				t.Fatalf("invalid WAV accepted: %v", err)
			}
		})
	}
}

func TestOfferRejectsNumericOrIncompleteSession(t *testing.T) {
	for _, body := range []string{
		`{"sdp":"v=0\r\nm=audio 9 RTP/AVP 0\r\n","type":"answer","sessionid":123456}`,
		`{"sdp":"v=0\r\nm=audio 9 RTP/AVP 0\r\n","type":"answer","sessionid":""}`,
		`{"sdp":"garbage","type":"answer","sessionid":"abc"}`,
		`{"code":-1,"msg":"session limit"}`,
	} {
		upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			_, _ = io.WriteString(w, body)
		}))
		c := mustClient(t, Config{LiveTalkingBaseURL: upstream.URL})
		_, err := c.Negotiate(context.Background(), Offer{SDP: testSDP, Type: "offer"})
		upstream.Close()
		if err == nil {
			t.Fatal("invalid offer response accepted")
		}
	}
}
