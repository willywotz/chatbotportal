package main

import (
	"context"
	"errors"
	"log/slog"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Agency struct {
	ID              string
	Name            string
	Status          string
	Description     string
	ConnectionType  string
	DataScope       []string
	EndpointURL     string
	ExpectedPayload map[string]any
	APIHeaders      []map[string]any
}

func getAgencies(ctx context.Context, pool *pgxpool.Pool) ([]Agency, error) {
	const q = `select id, name, status, coalesce(description, '') as description, connection_type,
	                  data_scope, coalesce(endpoint_url, '') as endpoint_url, expected_payload, api_headers
	           from agencies`
	rows, err := pool.Query(ctx, q)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Agency
	for rows.Next() {
		var a Agency
		if err := rows.Scan(&a.ID, &a.Name, &a.Status, &a.Description,
			&a.ConnectionType, &a.DataScope, &a.EndpointURL,
			&a.ExpectedPayload, &a.APIHeaders); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

type Identity struct {
	UserID  string
	IsAdmin bool
}

// authenticateAPIKey resolves a usable API key to an active user and bumps
// last_used_at. Mirrors AuthMiddleware + UserAPIKey.is_usable() in server.py.
func authenticateAPIKey(ctx context.Context, pool *pgxpool.Pool, keyHash string) (Identity, bool, error) {
	const q = `
	    select u.id, u.role
	    from user_api_keys k
	    join users u on u.id = k.user_id
	    where k.key_hash = $1
	      and k.revoked_at is null
	      and (k.expires_at is null or k.expires_at > now())
	      and u.is_active = true
	    limit 1`
	var id, role string
	err := pool.QueryRow(ctx, q, keyHash).Scan(&id, &role)
	if errors.Is(err, pgx.ErrNoRows) {
		return Identity{}, false, nil
	}
	if err != nil {
		return Identity{}, false, err
	}
	if _, err := pool.Exec(ctx,
		`update user_api_keys set last_used_at = now() where key_hash = $1`, keyHash); err != nil {
		slog.Warn("bump last_used_at", slog.Any("error", err))
	}
	return Identity{UserID: id, IsAdmin: role == "admin"}, true, nil
}
