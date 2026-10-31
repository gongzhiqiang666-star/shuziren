package domain

import "time"

const OutputHeartbeatMS = 3000
const OutputLeaseMS = 15000
const OutputNegotiationSeconds = 120

type OutputConfig struct {
	Width      int    `json:"width"`
	Height     int    `json:"height"`
	Fit        string `json:"fit"`
	Background string `json:"background"`
}

func DefaultOutputConfig() OutputConfig {
	return OutputConfig{Width: 1280, Height: 720, Fit: "contain", Background: "#000000"}
}

type OutputStatus struct {
	SessionID           string       `json:"session_id"`
	Enabled             bool         `json:"enabled"`
	Generation          int64        `json:"generation"`
	SessionStatus       string       `json:"session_status"`
	Epoch               int64        `json:"epoch"`
	Config              OutputConfig `json:"config"`
	State               string       `json:"state"`
	Online              bool         `json:"online"`
	PeerState           string       `json:"peer_state"`
	VideoReady          bool         `json:"video_ready"`
	AudioReady          bool         `json:"audio_ready"`
	LastHeartbeatAt     *time.Time   `json:"last_heartbeat_at"`
	LeaseExpiresAt      *time.Time   `json:"lease_expires_at"`
	LeaseOwned          bool         `json:"lease_owned"`
	LeaseID             *string      `json:"lease_id"`
	HeartbeatIntervalMS int          `json:"heartbeat_interval_ms"`
	LeaseTTLMS          int          `json:"lease_ttl_ms"`
}

// OutputAuth stays internal. A scoped credential never carries operator rights.
type OutputAuth struct {
	ShopID, SessionID string
	Generation        int64
	TokenHash         []byte
}
type OutputLease struct {
	ID, ReceiverID string
	Epoch          int64
	OldMediaID     *string
}
type OutputHeartbeat struct {
	ReceiverID string `json:"receiver_id"`
	LeaseID    string `json:"lease_id"`
	PeerState  string `json:"peer_state"`
	VideoReady bool   `json:"video_ready"`
	AudioReady bool   `json:"audio_ready"`
}

func OutputUnauthorized() *Error {
	return &Error{Status: 401, Code: "output_unauthorized", Message: "独立输出令牌无效、已撤销或已结束。请在工作台重新签发链接。"}
}
