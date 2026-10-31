// Package testutil creates throwaway PostgreSQL schemas only when an explicit
// TEST_DATABASE_URL is provided. It never truncates existing application data.
package testutil

import (
	"context"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/domain"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
	"github.com/jackc/pgx/v5"
)

func Postgres(t testing.TB) (*store.Store, *pgx.Conn) {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL is unset; real PostgreSQL integration test skipped")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal("cannot connect to explicit TEST_DATABASE_URL")
	}
	// Each schema is isolated; this dedicated test lock additionally serializes
	// packages because the production single-instance lock is database-scoped.
	if _, err = admin.Exec(ctx, "SELECT pg_advisory_lock($1)", int64(837462019405)); err != nil {
		_ = admin.Close(context.Background())
		t.Fatal("cannot acquire integration test lock")
	}
	schema := "test_" + strings.ReplaceAll(domain.NewID(), "-", "")
	if _, err = admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); err != nil {
		_ = admin.Close(context.Background())
		t.Fatal("cannot create isolated test schema")
	}
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		t.Fatal("TEST_DATABASE_URL must be a PostgreSQL URL")
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	st, err := store.Open(ctx, u.String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		st.Close()
		cleanup, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_, _ = admin.Exec(cleanup, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE")
		_ = admin.Close(cleanup)
	})
	if err = st.AcquireInstance(ctx); err != nil {
		t.Fatal(err)
	}
	if err = st.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err = admin.Exec(ctx, "SET search_path TO "+pgx.Identifier{schema}.Sanitize()); err != nil {
		t.Fatal("cannot select test schema")
	}
	return st, admin
}
