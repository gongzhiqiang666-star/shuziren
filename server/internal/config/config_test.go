package config

import "testing"

func TestConfigurationFailsClosed(t *testing.T) {
	env := map[string]string{"DATABASE_URL": "postgres://local/test", "APP_TOKEN": "test-token-01234567890123456789"}
	get := func(k string) string { return env[k] }
	c, err := FromEnv(get)
	if err != nil || c.Addr != "127.0.0.1:8080" {
		t.Fatalf("bad default: %v", err)
	}
	for _, token := range []string{"", "short", "twentyfourCharactersBut HasSpace", "twentyfourCharactersBut\nHasNewline"} {
		env["APP_TOKEN"] = token
		if _, err := FromEnv(get); err == nil {
			t.Fatal("unsafe token accepted")
		}
	}
	env["APP_TOKEN"] = "test-token-01234567890123456789"
	env["APP_ADDR"] = "localhost:not-port"
	if _, err := FromEnv(get); err == nil {
		t.Fatal("invalid port accepted")
	}
}
