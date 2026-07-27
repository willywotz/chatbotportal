package main

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

type agency struct {
	endpointURL     string
	apiHeaders      []map[string]string
	expectedPayload map[string]any
}

func getAgency(ctx context.Context, pool *pgxpool.Pool, id string) (agency, error) {
	const q = "select endpoint_url, api_headers, expected_payload from agencies where id = $1"
	var a agency
	err := pool.QueryRow(ctx, q, id).Scan(&a.endpointURL, &a.apiHeaders, &a.expectedPayload)
	return a, err
}

func insertConnectionLog(ctx context.Context, pool *pgxpool.Pool, agencyID, status string, latency int64, detail, requestBody, responseBody string) error {
	id, err := uuidV7()
	if err != nil {
		return fmt.Errorf("generate log id: %w", err)
	}
	const q = "insert into connection_logs (id, action, connection_type, status, latency_ms, detail, created_at, agency_id, request_body, response_body) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)"
	_, err = pool.Exec(ctx, q, id, "proxy", "API", status, latency, detail, now(), agencyID, requestBody, responseBody)
	return err
}

func incrementTotalCalls(ctx context.Context, pool *pgxpool.Pool, id string) error {
	const q = "update agencies set total_calls = total_calls + 1 where id = $1"
	_, err := pool.Exec(ctx, q, id)
	return err
}
