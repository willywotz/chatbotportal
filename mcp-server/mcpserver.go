package main

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const instructions = "This server exposes Thai government agency data for the AI " +
	"Chatbot Portal. Available tool:\n- list_agency: Returns a JSON object with an " +
	"`agencies` array and `total` count. Always call list_agency before answering " +
	"questions about available agencies. Never fabricate agency data."

type listAgencyOut struct {
	Agencies []AgencyOut `json:"agencies"`
	Total    int         `json:"total"`
}

func newMCPServer(pool *pgxpool.Pool) *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{
		Name: "AI Chatbot Portal MCP", Version: "2",
	}, &mcp.ServerOptions{Instructions: instructions})

	mcp.AddTool(srv, &mcp.Tool{
		Name:        "list_agency",
		Description: "Return a JSON array of all active government agencies.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, listAgencyOut, error) {
		agencies, err := loadShaped(ctx, pool, req.Extra.Header)
		if err != nil {
			return nil, listAgencyOut{}, err
		}
		return nil, listAgencyOut{Agencies: agencies, Total: len(agencies)}, nil
	})

	srv.AddResource(&mcp.Resource{
		URI: "agencies://list", Name: "agencies", MIMEType: "application/json",
	}, func(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		agencies, err := loadShaped(ctx, pool, req.Extra.Header)
		if err != nil {
			return nil, err
		}
		b, err := json.MarshalIndent(agencies, "", "  ")
		if err != nil {
			return nil, err
		}
		return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
			URI: "agencies://list", MIMEType: "application/json", Text: string(b),
		}}}, nil
	})

	return srv
}

func newStreamableHandler(srv *mcp.Server) http.Handler {
	return mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true},
	)
}

// loadShaped resolves identity from headers and returns the shaped agency list.
func loadShaped(ctx context.Context, pool *pgxpool.Pool, h http.Header) ([]AgencyOut, error) {
	id, userID, conversationID, err := resolveRequest(ctx, pool, h)
	if err != nil {
		return nil, err
	}
	agencies, err := getAgencies(ctx, pool)
	if err != nil {
		return nil, err
	}
	return buildAgencyOutput(ctx, h, agencies, id, userID, conversationID), nil
}

func resolveRequest(ctx context.Context, pool *pgxpool.Pool, h http.Header) (Identity, string, string, error) {
	conversationID, err := uuidV7()
	if err != nil {
		return Identity{}, "", "", err
	}
	var id Identity
	if token := parseBearerToken(h); token != "" && token != "anonymous" && pool != nil {
		resolved, ok, aerr := authenticateAPIKey(ctx, pool, hashAPIKey(token))
		if aerr != nil {
			return Identity{}, "", "", aerr
		}
		if ok {
			id = resolved
		}
	}
	userID := id.UserID
	if userID == "" {
		if userID, err = uuidV7(); err != nil {
			return Identity{}, "", "", err
		}
	}
	return id, userID, conversationID, nil
}
