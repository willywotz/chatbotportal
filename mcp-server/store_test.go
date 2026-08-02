package main

import (
	"context"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

func testPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		t.Skip("DATABASE_URL not set")
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestGetAgencies_ReturnsSlice(t *testing.T) {
	pool := testPool(t)
	got, err := getAgencies(context.Background(), pool)
	if err != nil {
		t.Fatalf("getAgencies: %v", err)
	}
	for _, a := range got {
		if a.ID == "" {
			t.Fatalf("agency with empty id: %+v", a)
		}
	}
}

func TestAuthenticateAPIKey_BogusKey(t *testing.T) {
	pool := testPool(t)
	_, ok, err := authenticateAPIKey(context.Background(), pool, hashAPIKey("tcg_totallybogus"))
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if ok {
		t.Fatalf("bogus key should not authenticate")
	}
}
