package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
)

type identityProvider interface {
	TTSIdentity(context.Context) (string, error)
}
type cacheMetadata struct {
	EngineID string `json:"engine_id"`
	SHA256   string `json:"sha256"`
}

func (s *Service) ttsIdentity(ctx context.Context) (string, bool, error) {
	p, ok := s.Media.(identityProvider)
	if !ok {
		return "", false, nil
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	id, err := p.TTSIdentity(ctx)
	if err != nil || len(id) != 64 {
		return "", true, domain.Unavailable("tts_identity_unavailable", "无法核验真实语音引擎身份，请检查已加载的本地TTS服务。")
	}
	b, err := hex.DecodeString(id)
	if err != nil || len(b) != 32 {
		return "", true, domain.Unavailable("tts_identity_unavailable", "本地TTS未提供有效的真实引擎身份。")
	}
	return strings.ToLower(id), true, nil
}
func audioCacheKey(j domain.Job, engine string) string {
	data, _ := json.Marshal(struct {
		Engine, Shop, Product, Text, Business            string
		ProductVersion, PersonaVersion, KnowledgeVersion int64
	}{engine, j.ShopID, j.ProductID, j.Text, j.BusinessFingerprint, j.ProductVersion, j.PersonaVersion, j.KnowledgeVersion})
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
func (s *Service) synthesizeAudio(ctx context.Context, j domain.Job) ([]byte, string, error) {
	engine, _, err := s.ttsIdentity(ctx)
	if err != nil {
		return nil, "", err
	}
	key := ""
	if engine != "" {
		key = audioCacheKey(j, engine)
		if cached, ok := s.cachedAudio(key, engine); ok {
			current, _, err := s.ttsIdentity(ctx)
			if err != nil {
				return nil, "", err
			}
			if current != engine {
				return nil, "", domain.Conflict("tts_engine_changed", "语音引擎已改变，旧音频已丢弃，请重新生成和审核。")
			}
			return cached, engine, nil
		}
	}
	wav, err := s.Media.Synthesize(ctx, j.Text)
	if err != nil {
		return nil, "", err
	}
	if engine != "" {
		current, _, err := s.ttsIdentity(ctx)
		if err != nil {
			return nil, "", err
		}
		if current != engine {
			return nil, "", domain.Conflict("tts_engine_changed", "合成期间真实语音引擎已改变，本次音频已丢弃。")
		}
		if ctx.Err() == nil {
			s.saveCachedAudio(key, engine, wav)
		}
	}
	return wav, engine, nil
}
func (s *Service) cachedAudio(key, engine string) ([]byte, bool) {
	dir := filepath.Join(s.AudioDir, "cache")
	metaFile, err := os.Open(filepath.Join(dir, key+".json"))
	if err != nil {
		return nil, false
	}
	meta, err := io.ReadAll(io.LimitReader(metaFile, 4097))
	_ = metaFile.Close()
	if err != nil || len(meta) > 4096 {
		return nil, false
	}
	var m cacheMetadata
	if json.Unmarshal(meta, &m) != nil || m.EngineID != engine || len(m.SHA256) != 64 {
		return nil, false
	}
	f, err := os.Open(filepath.Join(dir, key+".wav"))
	if err != nil {
		return nil, false
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > media.MaxAudioBytes {
		return nil, false
	}
	b, err := io.ReadAll(io.LimitReader(f, media.MaxAudioBytes+1))
	if err != nil || len(b) == 0 || len(b) > media.MaxAudioBytes {
		return nil, false
	}
	hash := sha256.Sum256(b)
	if hex.EncodeToString(hash[:]) != m.SHA256 {
		return nil, false
	}
	return b, true
}
func (s *Service) saveCachedAudio(key, engine string, wav []byte) {
	if len(wav) == 0 || len(wav) > media.MaxAudioBytes {
		return
	}
	dir := filepath.Join(s.AudioDir, "cache")
	if os.MkdirAll(dir, 0750) != nil {
		return
	}
	hash := sha256.Sum256(wav)
	meta, _ := json.Marshal(cacheMetadata{EngineID: engine, SHA256: hex.EncodeToString(hash[:])})
	if atomicCacheFile(dir, key+".wav", wav) != nil {
		return
	}
	if atomicCacheFile(dir, key+".json", meta) != nil {
		return
	}
	pruneAudioCache(dir)
}
func atomicCacheFile(dir, name string, b []byte) error {
	f, err := os.CreateTemp(dir, ".cache-*.tmp")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err = f.Write(b); err != nil {
		_ = f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		_ = f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(dir, name))
}
func pruneAudioCache(dir string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	type entry struct {
		name     string
		bytes    int64
		modified time.Time
	}
	files := []entry{}
	total := int64(0)
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".wav") || len(e.Name()) != 68 {
			continue
		}
		if _, err := hex.DecodeString(strings.TrimSuffix(e.Name(), ".wav")); err != nil {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		files = append(files, entry{e.Name(), info.Size(), info.ModTime()})
		total += info.Size()
	}
	sort.Slice(files, func(i, j int) bool { return files[i].modified.Before(files[j].modified) })
	count := len(files)
	for _, f := range files {
		if total <= 512<<20 && count <= 256 {
			break
		}
		if os.Remove(filepath.Join(dir, f.name)) == nil {
			_ = os.Remove(filepath.Join(dir, strings.TrimSuffix(f.name, ".wav")+".json"))
			total -= f.bytes
			count--
		}
	}
}
