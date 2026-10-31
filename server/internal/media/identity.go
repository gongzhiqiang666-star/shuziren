package media

import (
	"context"
	"encoding/hex"
	"net/http"
	"strings"
	"time"
)

// TTSIdentity obtains the authenticated identity of the loaded local engine.
// It is suitable for cache isolation only when health actually reports ready.
// It never returns configured URLs, credentials, model paths or reference text.
func (c *Client) TTSIdentity(ctx context.Context) (string, error) {
	if !c.TTSConfigured() {
		return "", ErrNotConfigured
	}
	if ctx == nil {
		return "", ErrInvalidInput
	}
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	u := *c.ttsURL
	u.Path = strings.TrimSuffix(u.Path, "/") + "/healthz"
	u.RawPath = ""
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return "", ErrInvalidInput
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.ttsAPIKey)
	res, err := c.http.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return "", ctx.Err()
		}
		return "", ErrUpstream
	}
	defer res.Body.Close()
	raw, err := readJSONResponse(ctx, res)
	if err != nil {
		return "", err
	}
	var payload struct {
		Status   string `json:"status"`
		Loaded   bool   `json:"model_loaded"`
		Engine   string `json:"engine"`
		Reason   string `json:"reason"`
		EngineID string `json:"engine_id"`
	}
	if err = decodeJSON(raw, &payload); err != nil {
		return "", err
	}
	hash, err := hex.DecodeString(payload.EngineID)
	if payload.Status != "ready" || !payload.Loaded || payload.Engine != "cosyvoice3" || payload.Reason != "ready" || err != nil || len(hash) != 32 || payload.EngineID != strings.ToLower(payload.EngineID) {
		return "", ErrInvalidResponse
	}
	return payload.EngineID, nil
}
