import { describe, expect, it } from "vitest";

import { mapRowToAgency, type AgencyRow } from "./agency";

const baseRow: AgencyRow = {
  id: "a1",
  name: "กรมสรรพากร",
  short_name: "RD",
  logo: "🏛️",
  connection_type: "API",
  status: "active",
  description: "ภาษีอากร",
  data_scope: ["ภาษี"],
  total_calls: 10,
  color: "hsl(213 70% 45%)",
  endpoint_url: "https://rd.example/chat",
  api_key_name: null,
  auth_method: "api_key",
  auth_header: "",
  base_path: "",
  request_format: "json",
  api_endpoints: [],
  response_schema: [],
  api_spec_raw: null,
  expected_payload: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  api_headers: [],
};

describe("mapRowToAgency", () => {
  it("maps new contract fields", () => {
    const agency = mapRowToAgency({
      ...baseRow,
      priority: 1,
      router_hint: "คำถามภาษีเงินได้",
      dispatch_timeout_s: 30,
      mcp_tool_name: "chat_with_rd",
      rating_up: 5,
      rating_down: 1,
      health: {
        state: "up",
        uptime_24h: 99.2,
        avg_latency_ms_24h: 320,
        last_check_at: "2026-06-11T08:00:00Z",
      },
    });
    expect(agency.priority).toBe(1);
    expect(agency.routerHint).toBe("คำถามภาษีเงินได้");
    expect(agency.dispatchTimeoutS).toBe(30);
    expect(agency.mcpToolName).toBe("chat_with_rd");
    expect(agency.ratingUp).toBe(5);
    expect(agency.ratingDown).toBe(1);
    expect(agency.health).toEqual({
      state: "up",
      uptime24h: 99.2,
      avgLatencyMs24h: 320,
      lastCheckAt: "2026-06-11T08:00:00Z",
    });
  });

  it("defaults health to unknown and new fields to null/empty when absent", () => {
    const agency = mapRowToAgency(baseRow);
    expect(agency.health).toEqual({
      state: "unknown",
      uptime24h: null,
      avgLatencyMs24h: null,
      lastCheckAt: null,
    });
    expect(agency.priority).toBeNull();
    expect(agency.routerHint).toBe("");
    expect(agency.dispatchTimeoutS).toBeNull();
    expect(agency.mcpToolName).toBeNull();
    expect(agency.ratingUp).toBe(0);
    expect(agency.ratingDown).toBe(0);
  });

  it("normalizes legacy and unknown statuses to disabled", () => {
    expect(mapRowToAgency({ ...baseRow, status: "inactive" }).status).toBe("disabled");
    expect(mapRowToAgency({ ...baseRow, status: "garbage" }).status).toBe("disabled");
    expect(mapRowToAgency({ ...baseRow, status: "maintenance" }).status).toBe("maintenance");
    expect(mapRowToAgency({ ...baseRow, status: "draft" }).status).toBe("draft");
  });
});
