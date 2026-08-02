package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func newRouter(srv *mcp.Server) *http.ServeMux {
	mux := http.NewServeMux()
	h := withTracing(newStreamableHandler(srv))
	mux.Handle("/mcp-v2", h)
	mux.Handle("/mcp-v2/", h) // tolerate trailing slash / subpaths
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"healthy","service":"mcp-server"}`))
	})
	return mux
}

func main() {
	ctx := context.Background()

	cfg := mustPanic(pgxpool.ParseConfig(os.Getenv("DATABASE_URL")))
	cfg.AfterConnect = func(ctx context.Context, conn *pgx.Conn) error {
		_, err := conn.Exec(ctx, "SET TIMEZONE TO 'Asia/Bangkok'")
		return err
	}
	pool := mustPanic(pgxpool.NewWithConfig(ctx, cfg))
	defer pool.Close()

	tp, err := initTracer(ctx)
	if err != nil {
		slog.Error("init tracer", slog.Any("error", err))
		return
	}
	defer func() { _ = tp.Shutdown(ctx) }()

	slog.Info("mcp-server listening on :8080 at /mcp-v2")
	if err := http.ListenAndServe(":8080", newRouter(newMCPServer(pool))); err != nil {
		slog.Error("http server", slog.Any("error", err))
		os.Exit(1)
	}
}

func mustPanic[T any](v T, err error) T {
	if err != nil {
		panic(err)
	}
	return v
}
