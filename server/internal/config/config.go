package config

import (
	"errors"
	"net"
	"os"
	"strconv"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/deepseek"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
)

type Config struct {
	Addr, Token, DatabaseURL, WebDist, AudioDir string
	DeepSeek                                    deepseek.Config
	Media                                       media.Config
}

func Load() (Config, error) { return FromEnv(os.Getenv) }
func FromEnv(get func(string) string) (Config, error) {
	c := Config{Addr: get("APP_ADDR"), Token: get("APP_TOKEN"), DatabaseURL: get("DATABASE_URL"), WebDist: get("WEB_DIST"), AudioDir: get("AUDIO_DIR"), DeepSeek: deepseek.Config{APIKey: get("DEEPSEEK_API_KEY"), BaseURL: get("DEEPSEEK_BASE_URL"), Model: get("DEEPSEEK_MODEL")}, Media: media.Config{TTSBaseURL: get("TTS_BASE_URL"), TTSAPIKey: get("TTS_API_KEY"), LiveTalkingBaseURL: get("LIVETALKING_BASE_URL")}}
	if c.Addr == "" {
		c.Addr = "127.0.0.1:8080"
	}
	if c.AudioDir == "" {
		c.AudioDir = "./data/audio"
	}
	if len(c.Token) < 24 || len(c.Token) > 512 {
		return c, errors.New("APP_TOKEN must contain 24-512 ASCII characters")
	}
	for _, r := range c.Token {
		if r < 33 || r > 126 {
			return c, errors.New("APP_TOKEN must be a printable ASCII bearer token without spaces")
		}
	}
	if c.DatabaseURL == "" {
		return c, errors.New("DATABASE_URL is required")
	}
	_, port, err := net.SplitHostPort(c.Addr)
	if err != nil {
		return c, errors.New("APP_ADDR must be host:port")
	}
	p, err := strconv.Atoi(port)
	if err != nil || p < 1 || p > 65535 {
		return c, errors.New("APP_ADDR port is invalid")
	}
	return c, nil
}
