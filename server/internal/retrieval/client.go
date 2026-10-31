// Package retrieval calls a fixed local BGE worker, never a remote embedding API.
package retrieval

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const Model = "BAAI/bge-small-zh-v1.5"
const Dimensions = 512

type Config struct{ BaseURL, APIKey string }
type Client struct {
	endpoint, key string
	http          *http.Client
}
type Result struct {
	Model    string      `json:"model"`
	Revision string      `json:"revision"`
	Vectors  [][]float32 `json:"vectors"`
}

func New(cfg Config) (*Client, error) {
	c := &Client{key: cfg.APIKey, http: &http.Client{Timeout: 45 * time.Second, Transport: &http.Transport{Proxy: nil}, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}
	if cfg.BaseURL == "" {
		if cfg.APIKey != "" {
			return nil, errors.New("BGE_BASE_URL is required with BGE_API_KEY")
		}
		return c, nil
	}
	u, e := url.Parse(cfg.BaseURL)
	if e != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("invalid BGE_BASE_URL")
	}
	ip := net.ParseIP(u.Hostname())
	local := u.Hostname() == "localhost" || u.Hostname() == "host.docker.internal" || u.Hostname() == "bge" || (ip != nil && (ip.IsLoopback() || ip.IsPrivate()))
	if !local || u.Scheme != "http" {
		return nil, errors.New("BGE_BASE_URL must be a fixed local HTTP endpoint")
	}
	if len(c.key) < 24 || len(c.key) > 512 {
		return nil, errors.New("BGE_API_KEY must contain 24-512 non-space ASCII characters")
	}
	for _, r := range c.key {
		if r < 33 || r > 126 {
			return nil, errors.New("invalid BGE_API_KEY")
		}
	}
	c.endpoint = strings.TrimRight(u.String(), "/")
	return c, nil
}
func (c *Client) Configured() bool { return c != nil && c.endpoint != "" }
func (c *Client) Health(ctx context.Context) (string, error) {
	if !c.Configured() {
		return "", errors.New("bge_unconfigured")
	}
	var h struct {
		Ready    bool   `json:"ready"`
		Model    string `json:"model"`
		Revision string `json:"revision"`
	}
	if e := c.call(ctx, http.MethodGet, "/health", nil, &h); e != nil {
		return "", e
	}
	if !h.Ready || h.Model != Model || !ValidRevision(h.Revision) {
		return "", errors.New("bge_not_ready")
	}
	return h.Revision, nil
}
func (c *Client) Embed(ctx context.Context, texts []string, query bool) (Result, error) {
	var r Result
	if len(texts) < 1 || len(texts) > 32 {
		return r, errors.New("invalid embedding batch")
	}
	e := c.call(ctx, http.MethodPost, "/embed", map[string]any{"texts": texts, "query": query}, &r)
	if e != nil {
		return r, e
	}
	if r.Model != Model || !ValidRevision(r.Revision) || len(r.Vectors) != len(texts) {
		return Result{}, errors.New("invalid embedding response")
	}
	for _, v := range r.Vectors {
		if !Valid(v) {
			return Result{}, errors.New("invalid embedding response")
		}
	}
	return r, nil
}
func (c *Client) call(ctx context.Context, method, path string, in, out any) error {
	if !c.Configured() {
		return errors.New("bge_unconfigured")
	}
	var body []byte
	var e error
	if in != nil {
		body, e = json.Marshal(in)
		if e != nil {
			return e
		}
	}
	req, e := http.NewRequestWithContext(ctx, method, c.endpoint+path, bytes.NewReader(body))
	if e != nil {
		return errors.New("bge_request_failed")
	}
	req.Header.Set("Authorization", "Bearer "+c.key)
	req.Header.Set("Content-Type", "application/json")
	resp, e := c.http.Do(req)
	if e != nil {
		return errors.New("bge_request_failed")
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return errors.New("bge_unavailable")
	}
	b, e := io.ReadAll(io.LimitReader(resp.Body, (2<<20)+1))
	if e != nil || len(b) > 2<<20 {
		return errors.New("invalid embedding response")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	if d.Decode(out) != nil {
		return errors.New("invalid embedding response")
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return errors.New("invalid embedding response")
	}
	return nil
}
func Valid(v []float32) bool {
	if len(v) != Dimensions {
		return false
	}
	var sum float64
	for _, x := range v {
		f := float64(x)
		if math.IsNaN(f) || math.IsInf(f, 0) {
			return false
		}
		sum += f * f
	}
	return sum > 0.99 && sum < 1.01
}
func ValidRevision(s string) bool {
	b, e := hex.DecodeString(s)
	return e == nil && len(b) == 32 && s == strings.ToLower(s)
}
func Cosine(a, b []float32) float64 {
	if len(a) != Dimensions || len(b) != Dimensions {
		return -1
	}
	var s float64
	for i, x := range a {
		s += float64(x) * float64(b[i])
	}
	return s
}
