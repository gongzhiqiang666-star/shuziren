// Package media connects the local TTS worker and LiveTalking. Successful audio
// submission means that LiveTalking accepted the upload, never that it was aired.
package media

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"net"
	"net/http"
	"net/textproto"
	"net/url"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

var (
	ErrNotConfigured   = errors.New("media service is not configured")
	ErrInvalidConfig   = errors.New("invalid media configuration")
	ErrInvalidInput    = errors.New("invalid media input")
	ErrUpstream        = errors.New("media upstream request failed")
	ErrInvalidResponse = errors.New("invalid media upstream response")
	// ErrSessionNotFound is returned only when Interrupt receives the verified
	// LiveTalking code=-1/msg="session not found" JSON response over HTTP 200.
	// It says nothing about downstream audio already buffered by the platform.
	ErrSessionNotFound = errors.New("LiveTalking session no longer exists")
)

const (
	MaxAudioBytes = 32 << 20
	MaxTextRunes  = 2000
	maxJSONBytes  = 1 << 20
	maxSDPBytes   = 512 << 10
)

type Config struct {
	TTSBaseURL, TTSAPIKey, LiveTalkingBaseURL string
}

type Offer struct {
	SDP  string `json:"sdp"`
	Type string `json:"type"`
}

type Answer struct {
	SDP       string `json:"sdp"`
	Type      string `json:"type"`
	SessionID string `json:"sessionid"`
}

type Client struct {
	ttsURL    *url.URL
	liveURL   *url.URL
	ttsAPIKey string
	http      *http.Client
}

// New allows completely disabled services, but rejects partial or unsafe
// configurations. URLs and credentials are deliberately omitted from errors.
func New(cfg Config) (*Client, error) {
	tts, err := parseBaseURL(cfg.TTSBaseURL)
	if err != nil {
		return nil, fmt.Errorf("TTS_BASE_URL: %w", err)
	}
	live, err := parseBaseURL(cfg.LiveTalkingBaseURL)
	if err != nil {
		return nil, fmt.Errorf("LIVETALKING_BASE_URL: %w", err)
	}
	if (tts == nil) != (cfg.TTSAPIKey == "") {
		return nil, fmt.Errorf("TTS_BASE_URL and TTS_API_KEY must be configured together: %w", ErrInvalidConfig)
	}
	if cfg.TTSAPIKey != "" && !validToken(cfg.TTSAPIKey) {
		return nil, fmt.Errorf("TTS_API_KEY must be a 24-512 character ASCII bearer token: %w", ErrInvalidConfig)
	}
	transport := &http.Transport{
		// Services are explicitly configured local endpoints. Do not silently send
		// their bearer credentials through a process-wide HTTP_PROXY.
		Proxy:                 nil,
		DialContext:           (&net.Dialer{Timeout: 10 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		ForceAttemptHTTP2:     true,
		MaxIdleConns:          8,
		MaxIdleConnsPerHost:   4,
		IdleConnTimeout:       60 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: time.Second,
		DisableCompression:    true,
	}
	return &Client{
		ttsURL: tts, liveURL: live, ttsAPIKey: cfg.TTSAPIKey,
		http: &http.Client{
			Transport: transport,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}, nil
}

func (c *Client) TTSConfigured() bool  { return c != nil && c.ttsURL != nil }
func (c *Client) LiveConfigured() bool { return c != nil && c.liveURL != nil }

// Synthesize obtains the actual PCM WAV to be previewed, stored, and passed
// unchanged to SendAudio. No second synthesis is performed for lip motion.
func (c *Client) Synthesize(ctx context.Context, text string) ([]byte, error) {
	if !c.TTSConfigured() {
		return nil, ErrNotConfigured
	}
	if ctx == nil || !utf8.ValidString(text) || strings.ContainsRune(text, '\x00') || strings.TrimSpace(text) == "" || utf8.RuneCountInString(text) > MaxTextRunes {
		return nil, ErrInvalidInput
	}
	ctx, cancel := context.WithTimeout(ctx, 180*time.Second)
	defer cancel()
	payload, _ := json.Marshal(struct {
		Text string `json:"text"`
	}{Text: text})
	response, err := c.request(ctx, c.ttsURL, "/synthesize", "application/json", "audio/wav", c.ttsAPIKey, bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, statusError(response.StatusCode)
	}
	kind, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || (kind != "audio/wav" && kind != "audio/x-wav" && kind != "audio/wave") {
		return nil, fmt.Errorf("expected WAV content type: %w", ErrInvalidResponse)
	}
	wav, err := readBounded(ctx, response.Body, MaxAudioBytes)
	if err != nil {
		return nil, err
	}
	if err := validateWAV(wav); err != nil {
		return nil, fmt.Errorf("expected valid mono PCM16 WAV: %w", ErrInvalidResponse)
	}
	return wav, nil
}

// Negotiate implements the string session IDs in the verified LiveTalking
// revision. Numeric JSON IDs are rejected, not partially coerced to strings.
func (c *Client) Negotiate(ctx context.Context, offer Offer) (Answer, error) {
	if !c.LiveConfigured() {
		return Answer{}, ErrNotConfigured
	}
	if ctx == nil || offer.Type != "offer" || !validSDP(offer.SDP) {
		return Answer{}, ErrInvalidInput
	}
	ctx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	payload, _ := json.Marshal(offer)
	body, err := c.jsonRequest(ctx, "/offer", bytes.NewReader(payload))
	if err != nil {
		return Answer{}, err
	}
	var envelope struct {
		SDP       string `json:"sdp"`
		Type      string `json:"type"`
		SessionID string `json:"sessionid"`
		Code      *int   `json:"code"`
	}
	if err := decodeJSON(body, &envelope); err != nil {
		return Answer{}, err
	}
	if envelope.Code != nil && *envelope.Code != 0 {
		return Answer{}, ErrUpstream
	}
	if envelope.Type != "answer" || !validSDP(envelope.SDP) || !validSessionID(envelope.SessionID) {
		return Answer{}, ErrInvalidResponse
	}
	return Answer{SDP: envelope.SDP, Type: envelope.Type, SessionID: envelope.SessionID}, nil
}

// SendAudio uploads the caller's validated WAV bytes. A nil error only proves
// an HTTP 200/code=0 acknowledgement. Never retry a timed-out send automatically:
// the upstream may have queued the audio before its response was lost.
func (c *Client) SendAudio(ctx context.Context, sessionID string, wav []byte) error {
	if !c.LiveConfigured() {
		return ErrNotConfigured
	}
	if ctx == nil || !validSessionID(sessionID) || validateWAV(wav) != nil {
		return ErrInvalidInput
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	if err := writer.WriteField("sessionid", sessionID); err != nil {
		return ErrInvalidInput
	}
	header := make(textproto.MIMEHeader)
	header.Set("Content-Disposition", `form-data; name="file"; filename="speech.wav"`)
	header.Set("Content-Type", "audio/wav")
	part, err := writer.CreatePart(header)
	if err != nil {
		return ErrInvalidInput
	}
	if _, err := part.Write(wav); err != nil {
		return ErrInvalidInput
	}
	if err := writer.Close(); err != nil {
		return ErrInvalidInput
	}
	response, err := c.request(ctx, c.liveURL, "/humanaudio", writer.FormDataContentType(), "application/json", "", &body)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	result, err := readJSONResponse(ctx, response)
	if err != nil {
		return err
	}
	return acknowledge(result, false)
}

// Interrupt requests flush_talk for this exact upstream session. It cannot
// retract audio already buffered downstream by WebRTC, OBS, or the platform.
func (c *Client) Interrupt(ctx context.Context, sessionID string) error {
	if !c.LiveConfigured() {
		return ErrNotConfigured
	}
	if ctx == nil || !validSessionID(sessionID) {
		return ErrInvalidInput
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	payload, _ := json.Marshal(struct {
		SessionID string `json:"sessionid"`
	}{sessionID})
	result, err := c.jsonRequest(ctx, "/interrupt_talk", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	return acknowledge(result, true)
}

func (c *Client) jsonRequest(ctx context.Context, path string, body io.Reader) ([]byte, error) {
	response, err := c.request(ctx, c.liveURL, path, "application/json", "application/json", "", body)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	return readJSONResponse(ctx, response)
}

func (c *Client) request(ctx context.Context, base *url.URL, path, contentType, accept, token string, body io.Reader) (*http.Response, error) {
	u := *base
	u.Path = strings.TrimSuffix(u.Path, "/") + path
	u.RawPath = ""
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), body)
	if err != nil {
		return nil, ErrInvalidInput
	}
	req.Header.Set("Content-Type", contentType)
	req.Header.Set("Accept", accept)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	response, err := c.http.Do(req)
	if err != nil {
		// net/url errors can include credentials, URLs, or proxy diagnostics. Only
		// expose safe sentinel errors; preserve cancellation/deadline semantics.
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, ErrUpstream
	}
	return response, nil
}

func parseBaseURL(raw string) (*url.URL, error) {
	if raw == "" {
		return nil, nil
	}
	u, err := url.Parse(raw)
	if err != nil || strings.TrimSpace(raw) != raw || u == nil ||
		(u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" ||
		u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" ||
		u.Opaque != "" || strings.ContainsAny(u.Path, "\r\n\\") || u.RawPath != "" {
		return nil, ErrInvalidConfig
	}
	for _, segment := range strings.Split(u.Path, "/") {
		if segment == "." || segment == ".." {
			return nil, ErrInvalidConfig
		}
	}
	if port := u.Port(); port != "" {
		number, err := strconv.Atoi(port)
		if err != nil || number < 1 || number > 65535 {
			return nil, ErrInvalidConfig
		}
	}
	return u, nil
}

func validToken(token string) bool {
	if len(token) < 24 || len(token) > 512 {
		return false
	}
	for _, c := range []byte(token) {
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || strings.ContainsRune("-._~+/=", rune(c)) {
			continue
		}
		return false
	}
	return true
}

func validSessionID(id string) bool {
	if len(id) == 0 || len(id) > 128 {
		return false
	}
	for _, c := range []byte(id) {
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' {
			continue
		}
		return false
	}
	return true
}

func validSDP(sdp string) bool {
	return len(sdp) <= maxSDPBytes && utf8.ValidString(sdp) && !strings.ContainsRune(sdp, '\x00') &&
		(strings.HasPrefix(sdp, "v=0\r\n") || strings.HasPrefix(sdp, "v=0\n")) && strings.Contains(sdp, "\nm=")
}

func readBounded(ctx context.Context, body io.Reader, max int64) ([]byte, error) {
	data, err := io.ReadAll(io.LimitReader(body, max+1))
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, ErrUpstream
	}
	if len(data) > int(max) {
		return nil, ErrInvalidResponse
	}
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	return data, nil
}

func readJSONResponse(ctx context.Context, response *http.Response) ([]byte, error) {
	if response.StatusCode != http.StatusOK {
		return nil, statusError(response.StatusCode)
	}
	kind, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || kind != "application/json" {
		return nil, ErrInvalidResponse
	}
	return readBounded(ctx, response.Body, maxJSONBytes)
}

func statusError(status int) error {
	return fmt.Errorf("upstream HTTP %d: %w", status, ErrUpstream)
}

func decodeJSON(body []byte, value any) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	first, err := decoder.Token()
	if err != nil || first != json.Delim('{') {
		return ErrInvalidResponse
	}
	// Reject duplicate top-level fields rather than allowing a later code:0 or
	// sessionid to overwrite an earlier rejection/identity in the response.
	seen := make(map[string]bool)
	for decoder.More() {
		token, err := decoder.Token()
		key, ok := token.(string)
		if err != nil || !ok || seen[key] {
			return ErrInvalidResponse
		}
		seen[key] = true
		var raw json.RawMessage
		if decoder.Decode(&raw) != nil {
			return ErrInvalidResponse
		}
	}
	if last, err := decoder.Token(); err != nil || last != json.Delim('}') {
		return ErrInvalidResponse
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		return ErrInvalidResponse
	}
	if json.Unmarshal(body, value) != nil {
		return ErrInvalidResponse
	}
	return nil
}

func acknowledge(body []byte, allowMissingSession bool) error {
	var result struct {
		Code    *int   `json:"code"`
		Message string `json:"msg"`
	}
	if err := decodeJSON(body, &result); err != nil {
		return err
	}
	if result.Code == nil {
		return ErrInvalidResponse
	}
	if *result.Code != 0 {
		if allowMissingSession && *result.Code == -1 && result.Message == "session not found" {
			return ErrSessionNotFound
		}
		return ErrUpstream
	}
	return nil
}
