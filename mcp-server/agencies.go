package main

import (
	"context"
	"net/http"
	"strings"
)

type AgencyOut struct {
	ID              string           `json:"id"`
	Name            string           `json:"name"`
	Status          string           `json:"status"`
	Description     string           `json:"description"`
	ConnectionType  string           `json:"connection_type"`
	DataScope       []string         `json:"data_scope"`
	EndpointURL     string           `json:"endpoint_url"`
	ExpectedPayload map[string]any   `json:"expected_payload"`
	APIHeaders      []map[string]any `json:"api_headers"`
}

// buildAgencyOutput shapes agencies for the caller: redacts the Authorization
// header for non-admins, rewrites API endpoints through the agent proxy, and
// templates __user_id__/__conversation_id__ in top-level expected_payload
// values. Mirrors _fetch_agencies post-processing in server.py.
func buildAgencyOutput(ctx context.Context, h http.Header, agencies []Agency, id Identity, userID, conversationID string) []AgencyOut {
	out := make([]AgencyOut, 0, len(agencies))
	for _, a := range agencies {
		headers := a.APIHeaders
		if headers == nil {
			headers = []map[string]any{}
		}
		if !id.IsAdmin {
			kept := headers[:0:0]
			for _, hd := range headers {
				name, _ := hd["name"].(string)
				if strings.EqualFold(name, "authorization") {
					continue
				}
				kept = append(kept, hd)
			}
			headers = kept
		}

		endpoint := a.EndpointURL
		if a.ConnectionType == "API" {
			endpoint = agentProxyEndpoint(ctx, h, a.ID)
		}

		payload := make(map[string]any, len(a.ExpectedPayload))
		for k, v := range a.ExpectedPayload {
			if s, ok := v.(string); ok {
				s = strings.ReplaceAll(s, "__user_id__", userID)
				s = strings.ReplaceAll(s, "__conversation_id__", conversationID)
				payload[k] = s
				continue
			}
			payload[k] = v
		}

		out = append(out, AgencyOut{
			ID: a.ID, Name: a.Name, Status: a.Status, Description: a.Description,
			ConnectionType: a.ConnectionType, DataScope: a.DataScope,
			EndpointURL: endpoint, ExpectedPayload: payload, APIHeaders: headers,
		})
	}
	return out
}
