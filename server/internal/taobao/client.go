// Package taobao implements the documented TOP HTTP protocol. No scraping,
// browser session extraction, or unapproved generic API proxy is provided.
package taobao

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

const CommentTopic = "taobao_liveaigc_CommentSend"

type Config struct{ AppKey, AppSecret, Session, Gateway, Group string }
type Client struct {
	cfg  Config
	http *http.Client
	now  func() time.Time
}
type Error struct {
	Code       string
	Definitive bool
}

func (e *Error) Error() string { return e.Code }

var digits = regexp.MustCompile(`^[1-9][0-9]{0,18}$`)

func ValidNumber(s string) bool {
	if !digits.MatchString(s) {
		return false
	}
	_, e := strconv.ParseInt(s, 10, 64)
	return e == nil
}

// ID retains exact 64-bit IDs across JSON/JavaScript boundaries.
type ID string

func (i *ID) UnmarshalJSON(b []byte) error {
	var s string
	if len(b) > 0 && b[0] == '"' {
		if e := json.Unmarshal(b, &s); e != nil {
			return e
		}
	} else {
		s = string(b)
	}
	if !ValidNumber(s) {
		return errors.New("invalid numeric ID")
	}
	*i = ID(s)
	return nil
}
func New(cfg Config) (*Client, error) {
	if cfg.Gateway == "" {
		cfg.Gateway = "https://gw.api.taobao.com/router/rest"
	}
	if cfg.Group == "" {
		cfg.Group = "default"
	}
	u, e := url.Parse(cfg.Gateway)
	if e != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("invalid TAOBAO_GATEWAY")
	}
	ip := net.ParseIP(u.Hostname())
	local := u.Hostname() == "localhost" || (ip != nil && ip.IsLoopback())
	official := u.Hostname() == "gw.api.taobao.com" || u.Hostname() == "eco.taobao.com" || u.Hostname() == "api.taobao.com"
	if !(official && u.Scheme == "https" && u.Path == "/router/rest" && u.Port() == "") && !(local && u.Scheme == "http") {
		return nil, errors.New("TAOBAO_GATEWAY requires an official HTTPS gateway (loopback HTTP for tests)")
	}
	enabled := cfg.AppKey != "" || cfg.AppSecret != "" || cfg.Session != ""
	if enabled && (cfg.AppKey == "" || cfg.AppSecret == "" || cfg.Session == "") {
		return nil, errors.New("TAOBAO_APP_KEY, TAOBAO_APP_SECRET and TAOBAO_SESSION must be configured together")
	}
	for _, s := range []string{cfg.AppKey, cfg.AppSecret, cfg.Session, cfg.Group} {
		if len(s) > 1024 {
			return nil, errors.New("Taobao configuration too long")
		}
		for _, r := range s {
			if r < 33 || r > 126 {
				return nil, errors.New("invalid Taobao credential or group")
			}
		}
	}
	return &Client{cfg: cfg, now: time.Now, http: &http.Client{Timeout: 20 * time.Second, Transport: &http.Transport{Proxy: nil}, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}
func (c *Client) Configured() bool { return c != nil && c.cfg.AppKey != "" }
func Sign(params url.Values, secret string) string {
	keys := make([]string, 0, len(params))
	for k := range params {
		if k != "sign" {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		b.WriteString(k)
		b.WriteString(params.Get(k))
	}
	hash := hmac.New(sha256.New, []byte(secret))
	_, _ = hash.Write([]byte(b.String()))
	return strings.ToUpper(hex.EncodeToString(hash.Sum(nil)))
}
func (c *Client) call(ctx context.Context, method string, params url.Values, session bool, out any) error {
	if !c.Configured() {
		return &Error{"taobao_not_configured", true}
	}
	params.Set("method", method)
	params.Set("app_key", c.cfg.AppKey)
	params.Set("format", "json")
	params.Set("v", "2.0")
	params.Set("sign_method", "hmac-sha256")
	params.Set("timestamp", c.now().In(time.FixedZone("CST", 8*60*60)).Format("2006-01-02 15:04:05"))
	if session {
		params.Set("session", c.cfg.Session)
	}
	params.Set("sign", Sign(params, c.cfg.AppSecret))
	req, e := http.NewRequestWithContext(ctx, http.MethodPost, c.cfg.Gateway, strings.NewReader(params.Encode()))
	if e != nil {
		return &Error{"taobao_request_failed", false}
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
	resp, e := c.http.Do(req)
	if e != nil {
		return &Error{"taobao_request_failed", false}
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return &Error{"taobao_http_error", false}
	}
	b, e := io.ReadAll(io.LimitReader(resp.Body, (2<<20)+1))
	if e != nil || len(b) > 2<<20 {
		return &Error{"taobao_invalid_response", false}
	}
	var envelope map[string]json.RawMessage
	if e = singleJSON(b, &envelope); e != nil {
		return &Error{"taobao_invalid_response", false}
	}
	if raw, ok := envelope["error_response"]; ok {
		var er struct {
			Code json.Number `json:"code"`
		}
		if singleJSON(raw, &er) != nil || er.Code == "" {
			return &Error{"taobao_invalid_response", false}
		}
		// Generic TOP errors include remote-service failures after dispatch. An
		// error envelope alone cannot prove that an external side effect did not
		// happen. Explicit business_success=false remains definitive below.
		return &Error{"taobao_api_error", false}
	}
	key := strings.ReplaceAll(strings.TrimPrefix(method, "taobao."), ".", "_") + "_response"
	raw, ok := envelope[key]
	if !ok || bytes.Equal(raw, []byte("null")) || singleJSON(raw, out) != nil {
		return &Error{"taobao_invalid_response", false}
	}
	return nil
}
func singleJSON(b []byte, out any) error {
	check := json.NewDecoder(bytes.NewReader(b))
	check.UseNumber()
	if e := uniqueJSONValue(check, 0); e != nil {
		return e
	}
	if _, e := check.Token(); e != io.EOF {
		return errors.New("extra JSON")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	if e := d.Decode(out); e != nil {
		return e
	}
	var v any
	if d.Decode(&v) != io.EOF {
		return errors.New("extra JSON")
	}
	return nil
}
func uniqueJSONValue(d *json.Decoder, depth int) error {
	if depth > 64 {
		return errors.New("JSON nesting too deep")
	}
	t, e := d.Token()
	if e != nil {
		return e
	}
	opening, ok := t.(json.Delim)
	if !ok {
		return nil
	}
	switch opening {
	case '{':
		seen := map[string]bool{}
		for d.More() {
			key, e := d.Token()
			if e != nil {
				return e
			}
			name, ok := key.(string)
			if !ok || seen[name] {
				return errors.New("duplicate JSON field")
			}
			seen[name] = true
			if e = uniqueJSONValue(d, depth+1); e != nil {
				return e
			}
		}
		if end, e := d.Token(); e != nil || end != json.Delim('}') {
			return errors.New("invalid JSON object")
		}
	case '[':
		for d.More() {
			if e = uniqueJSONValue(d, depth+1); e != nil {
				return e
			}
		}
		if end, e := d.Token(); e != nil || end != json.Delim(']') {
			return errors.New("invalid JSON array")
		}
	default:
		return errors.New("unexpected JSON delimiter")
	}
	return nil
}
func objectParam(v any) string { b, _ := json.Marshal(v); return string(b) }

type Message struct {
	ID      ID     `json:"id"`
	Topic   string `json:"topic"`
	Content string `json:"content"`
	PubTime string `json:"pub_time"`
}
type Comment struct {
	AnchorID   string `json:"anchorId,omitempty"`
	LiveID     string `json:"liveId"`
	UniqueCode string `json:"uniqueCode,omitempty"`
	Text       string `json:"comment"`
	UserID     string `json:"userId,omitempty"`
	UserNick   string `json:"userNick,omitempty"`
}

func (c *Client) Consume(ctx context.Context) ([]Message, error) {
	var out struct {
		Messages *struct {
			Messages *[]Message `json:"tmc_message"`
		} `json:"messages"`
	}
	e := c.call(ctx, "taobao.tmc.messages.consume", url.Values{"quantity": {"20"}, "group_name": {c.cfg.Group}}, false, &out)
	if e != nil {
		return nil, e
	}
	if out.Messages == nil || out.Messages.Messages == nil {
		return nil, &Error{"taobao_empty_response_unverified", false}
	}
	messages := *out.Messages.Messages
	if len(messages) > 200 {
		return nil, &Error{"taobao_invalid_response", false}
	}
	for _, m := range messages {
		if !ValidNumber(string(m.ID)) || len(m.Content) > 64<<10 || len(m.Topic) > 200 {
			return nil, &Error{"taobao_invalid_response", false}
		}
	}
	return messages, nil
}
func (c *Client) Confirm(ctx context.Context, ids []string) error {
	if len(ids) == 0 {
		return nil
	}
	if len(ids) > 200 {
		return errors.New("too many IDs")
	}
	for _, id := range ids {
		if !ValidNumber(id) {
			return errors.New("invalid message ID")
		}
	}
	var out struct {
		Success *bool `json:"is_success"`
	}
	if e := c.call(ctx, "taobao.tmc.messages.confirm", url.Values{"group_name": {c.cfg.Group}, "s_message_ids": {strings.Join(ids, ",")}}, false, &out); e != nil {
		return e
	}
	if out.Success == nil {
		return &Error{"taobao_invalid_response", false}
	}
	if !*out.Success {
		return &Error{"taobao_confirm_rejected", true}
	}
	return nil
}
func ParseComment(content string) (Comment, error) {
	var c Comment
	if len(content) > 64<<10 || singleJSON([]byte(content), &c) != nil {
		return c, errors.New("invalid comment JSON")
	}
	return c, nil
}

type Item struct {
	ID      ID     `json:"num_iid"`
	Title   string `json:"title"`
	Price   string `json:"price"`
	Stock   int64  `json:"num"`
	OuterID string `json:"outer_id"`
	Status  string `json:"approve_status"`
}

func (i *Item) UnmarshalJSON(raw []byte) error {
	var w struct {
		ID      *ID     `json:"num_iid"`
		Title   *string `json:"title"`
		Price   *string `json:"price"`
		Stock   *int64  `json:"num"`
		OuterID string  `json:"outer_id"`
		Status  *string `json:"approve_status"`
	}
	if e := json.Unmarshal(raw, &w); e != nil {
		return e
	}
	if w.ID == nil || w.Title == nil || w.Price == nil || w.Stock == nil || w.Status == nil {
		return errors.New("missing item facts")
	}
	*i = Item{ID: *w.ID, Title: *w.Title, Price: *w.Price, Stock: *w.Stock, OuterID: w.OuterID, Status: *w.Status}
	return nil
}

type ItemPage struct {
	Items []Item `json:"items"`
	Total int64  `json:"total_results"`
}

func (c *Client) Items(ctx context.Context, page, size int) (ItemPage, error) {
	var result ItemPage
	if page < 1 || size < 1 || size > 200 || page > 20000/size {
		return result, errors.New("invalid pagination")
	}
	var out struct {
		Items struct {
			Item []Item `json:"item"`
		} `json:"items"`
		Total *int64 `json:"total_results"`
	}
	e := c.call(ctx, "taobao.items.onsale.get", url.Values{"fields": {"num_iid,title,price,num,outer_id,approve_status"}, "page_no": {strconv.Itoa(page)}, "page_size": {strconv.Itoa(size)}}, true, &out)
	if e != nil {
		return result, e
	}
	if out.Total == nil || *out.Total < 0 || len(out.Items.Item) > size || int64(len(out.Items.Item)) > *out.Total {
		return result, &Error{"taobao_invalid_response", false}
	}
	for _, item := range out.Items.Item {
		if !ValidNumber(string(item.ID)) || strings.TrimSpace(item.Title) == "" || len(item.Title) > 2000 || !pricePattern.MatchString(item.Price) || item.Stock < 0 || item.Stock > 1000000000000 || item.Status != "onsale" {
			return ItemPage{}, &Error{"taobao_invalid_response", false}
		}
	}
	result.Items = out.Items.Item
	result.Total = *out.Total
	if result.Items == nil {
		result.Items = []Item{}
	}
	return result, e
}

var pricePattern = regexp.MustCompile(`^[0-9]{1,10}(\.[0-9]{1,2})?$`)

func (c *Client) LiveDetail(ctx context.Context, liveID string) (json.RawMessage, error) {
	if !ValidNumber(liveID) {
		return nil, errors.New("invalid live ID")
	}
	var out struct {
		Success *bool           `json:"business_success"`
		Data    json.RawMessage `json:"data"`
	}
	e := c.call(ctx, "taobao.live.virtualanchor.get.live.detail", url.Values{"live_detail_req": {objectParam(map[string]string{"live_id": liveID})}}, true, &out)
	if e != nil {
		return nil, e
	}
	if out.Success == nil {
		return nil, &Error{"taobao_invalid_response", false}
	}
	if !*out.Success {
		return nil, &Error{"taobao_business_rejected", true}
	}
	if len(out.Data) == 0 || bytes.Equal(bytes.TrimSpace(out.Data), []byte("null")) {
		return nil, &Error{"taobao_invalid_response", false}
	}
	return out.Data, nil
}
func (c *Client) PushItem(ctx context.Context, liveID, itemID string) error {
	if !ValidNumber(liveID) || !ValidNumber(itemID) {
		return errors.New("invalid numeric ID")
	}
	var out struct {
		Success *bool `json:"business_success"`
	}
	e := c.call(ctx, "taobao.live.virtualanchor.push.item.card", url.Values{"live_push_item_card_req": {objectParam(map[string]json.Number{"live_id": json.Number(liveID), "item_id": json.Number(itemID)})}}, true, &out)
	if e != nil {
		return e
	}
	if out.Success == nil {
		return &Error{"taobao_invalid_response", false}
	}
	if !*out.Success {
		return &Error{"taobao_business_rejected", true}
	}
	return nil
}

type Report struct {
	Status         int    `json:"status"`
	Avatar         *bool  `json:"avatar"`
	ModelType      int    `json:"model_type"`
	ISVName        string `json:"isv_name"`
	OpenHumanReply *bool  `json:"open_human_reply,omitempty"`
}

func (r Report) Validate() error {
	if r.Status < 1 || r.Status > 3 || r.Avatar == nil || (r.ModelType != 1 && r.ModelType != 2) || len(strings.TrimSpace(r.ISVName)) == 0 || len(r.ISVName) > 500 {
		return errors.New("invalid report")
	}
	return nil
}
func (c *Client) Report(ctx context.Context, liveID string, r Report) error {
	if !ValidNumber(liveID) {
		return errors.New("invalid live ID")
	}
	if e := r.Validate(); e != nil {
		return e
	}
	data := map[string]any{"live_id": json.Number(liveID), "status": r.Status, "avatar": *r.Avatar, "model_type": r.ModelType, "isv_name": r.ISVName}
	if r.OpenHumanReply != nil {
		data["open_human_reply"] = *r.OpenHumanReply
	}
	var out struct {
		Success *bool `json:"success_detail"`
	}
	if e := c.call(ctx, "taobao.live.digitalanchor.get.reportstats", url.Values{"digital_anchor_report_stat_request": {objectParam(data)}}, true, &out); e != nil {
		return e
	}
	if out.Success == nil {
		return &Error{"taobao_invalid_response", false}
	}
	if !*out.Success {
		return &Error{"taobao_business_rejected", true}
	}
	return nil
}
func ErrorCode(err error) string {
	var e *Error
	if errors.As(err, &e) {
		return e.Code
	}
	return fmt.Sprint("taobao_operation_failed")
}
