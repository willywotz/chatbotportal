package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)

func init() {
	slog.SetLogLoggerLevel(slog.LevelDebug)
}

func main() {
	ctx := context.Background()

	slog.Info("Connecting to PostgreSQL database")
	cfg := mustPanic(pgxpool.ParseConfig(os.Getenv("DATABASE_URL")))
	cfg.AfterConnect = func(ctx context.Context, conn *pgx.Conn) error {
		_, err := conn.Exec(ctx, "SET TIMEZONE TO 'Asia/Bangkok'")
		return err
	}
	pool := mustPanic(pgxpool.NewWithConfig(ctx, cfg))
	defer pool.Close()

	tp, err := initTracer(ctx)
	if err != nil {
		slog.Error("Failed to initialize tracer", slog.Any("error", err))
		return
	}
	defer func() {
		if err := tp.Shutdown(ctx); err != nil {
			slog.Error("Error shutting down tracer provider", slog.Any("error", err))
		}
	}()

	http.Handle("/agent-proxy/", &handler{
		pool:   pool,
		tracer: otel.Tracer("agent-proxy"),
		load: func(ctx context.Context, id string) (agency, error) {
			return getAgency(ctx, pool, id)
		},
	})
	http.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok\n"))
	})

	slog.Info("Starting HTTP server on http://localhost:8080")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		slog.Error("HTTP server error", slog.Any("error", err))
		os.Exit(1)
	}
}

func mustPanic[T any](v T, err error) T {
	if err != nil {
		panic(err)
	}
	return v
}

func initTracer(ctx context.Context) (*sdktrace.TracerProvider, error) {
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint("jaeger:4317"),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("agent-proxy"),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
	)
	otel.SetTracerProvider(tp)
	return tp, nil
}
