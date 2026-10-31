package deepseek

import (
	"context"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
)

type knowledgeKey struct{}

// WithKnowledge carries already scoped, version-checked local retrieval results.
// It is not supplied by an HTTP caller and cannot insert cross-shop records.
func WithKnowledge(ctx context.Context, records []domain.Knowledge) context.Context {
	return context.WithValue(ctx, knowledgeKey{}, records)
}
