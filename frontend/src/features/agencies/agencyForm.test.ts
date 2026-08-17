import { describe, it, expect } from "vitest";
import {
  DEFAULT_FORM_STATE,
  PROTOCOL_INFO,
  WIZARD_STEPS,
  agencyToFormState,
  buildSavePayload,
  canActivate,
  firstIncompleteStep,
  invalidHeaderIndices,
  isStepConnectionValid,
  isStepGeneralValid,
  isUrlValid,
  parseExpectedPayload,
} from "./agencyForm";
import type { Agency } from "@/shared/types/agency";

const API_AGENCY: Agency = {
  id: "1",
  name: "Test Agency",
  shortName: "TA",
  logo: "🏛️",
  description: "A test agency",
  connectionType: "API",
  status: "active",
  dataScope: ["citizens", "tax"],
  totalCalls: 42,
  color: "hsl(200 60% 50%)",
  endpointUrl: "https://api.test.go.th/v1",
  authMethod: "oauth2",
  authHeader: "Authorization",
  basePath: "/api/v1",
  requestFormat: "json",
  apiEndpoints: [{ method: "GET", path: "/citizens", description: "List citizens" }],
  responseSchema: [{ field: "id", type: "string", description: "Citizen ID" }],
  expectedPayload: { query: "test", limit: 10 },
  apiSpecRaw: "openapi: 3.0.0",
  apiHeaders: [{ name: "X-Source", value: "portal" }],
  priority: null,
  routerHint: "",
  dispatchTimeoutS: null,
  mcpToolName: null,
  ratingUp: 0,
  ratingDown: 0,
  health: { state: "unknown", uptime24h: null, avgLatencyMs24h: null, lastCheckAt: null },
};

const MCP_AGENCY: Agency = {
  id: "2",
  name: "MCP Agency",
  shortName: "MA",
  logo: "🤖",
  description: "An MCP agency",
  connectionType: "MCP",
  status: "disabled",
  dataScope: [],
  totalCalls: 0,
  color: "hsl(140 60% 45%)",
  endpointUrl: "https://mcp.test.go.th",
  priority: null,
  routerHint: "",
  dispatchTimeoutS: null,
  mcpToolName: null,
  ratingUp: 0,
  ratingDown: 0,
  health: { state: "unknown", uptime24h: null, avgLatencyMs24h: null, lastCheckAt: null },
};

describe("DEFAULT_FORM_STATE", () => {
  it("has expected baseline values", () => {
    expect(DEFAULT_FORM_STATE.name).toBe("");
    expect(DEFAULT_FORM_STATE.logo).toBe("🏢");
    expect(DEFAULT_FORM_STATE.connectionType).toBe("API");
    expect(DEFAULT_FORM_STATE.status).toBe("draft");
    expect(DEFAULT_FORM_STATE.authMethod).toBe("api_key");
    expect(DEFAULT_FORM_STATE.requestFormat).toBe("json");
    expect(DEFAULT_FORM_STATE.dataScope).toEqual([]);
    expect(DEFAULT_FORM_STATE.apiEndpoints).toEqual([]);
    expect(DEFAULT_FORM_STATE.responseSchema).toEqual([]);
    expect(DEFAULT_FORM_STATE.apiHeaders).toEqual([]);
  });
});

describe("agencyToFormState", () => {
  it("maps all Agency fields to form state for API agency", () => {
    const s = agencyToFormState(API_AGENCY);
    expect(s.name).toBe("Test Agency");
    expect(s.shortName).toBe("TA");
    expect(s.logo).toBe("🏛️");
    expect(s.description).toBe("A test agency");
    expect(s.connectionType).toBe("API");
    expect(s.status).toBe("active");
    expect(s.endpointUrl).toBe("https://api.test.go.th/v1");
    expect(s.color).toBe("hsl(200 60% 50%)");
    expect(s.dataScope).toEqual(["citizens", "tax"]);
    expect(s.authMethod).toBe("oauth2");
    expect(s.authHeader).toBe("Authorization");
    expect(s.basePath).toBe("/api/v1");
    expect(s.requestFormat).toBe("json");
    expect(s.apiEndpoints).toEqual([{ method: "GET", path: "/citizens", description: "List citizens" }]);
    expect(s.responseSchema).toEqual([{ field: "id", type: "string", description: "Citizen ID" }]);
    expect(s.apiHeaders).toEqual([{ name: "X-Source", value: "portal" }]);
    expect(s.apiSpecRaw).toBe("openapi: 3.0.0");
    expect(s.scopeInput).toBe(""); // always empty — not persisted
  });

  it("serialises expectedPayload to formatted JSON string", () => {
    const s = agencyToFormState(API_AGENCY);
    expect(s.expectedPayload).toBe(JSON.stringify({ query: "test", limit: 10 }, null, 2));
  });

  it("produces empty expectedPayload when agency.expectedPayload is null", () => {
    const agency: Agency = { ...API_AGENCY, expectedPayload: null };
    expect(agencyToFormState(agency).expectedPayload).toBe("");
  });

  it("produces empty expectedPayload when agency.expectedPayload is undefined", () => {
    const agency: Agency = { ...API_AGENCY, expectedPayload: undefined };
    expect(agencyToFormState(agency).expectedPayload).toBe("");
  });

  it("defaults optional API fields when undefined", () => {
    const bare: Agency = { ...API_AGENCY, authMethod: undefined, authHeader: undefined, basePath: undefined };
    const s = agencyToFormState(bare);
    expect(s.authMethod).toBe("api_key");
    expect(s.authHeader).toBe("");
    expect(s.basePath).toBe("");
  });

  it("maps MCP agency correctly", () => {
    const s = agencyToFormState(MCP_AGENCY);
    expect(s.connectionType).toBe("MCP");
    expect(s.status).toBe("disabled");
    expect(s.dataScope).toEqual([]);
    expect(s.apiEndpoints).toEqual([]);
  });
});

describe("parseExpectedPayload", () => {
  it("parses valid JSON object", () => {
    const { value, error } = parseExpectedPayload('{"query":"test","limit":10}');
    expect(value).toEqual({ query: "test", limit: 10 });
    expect(error).toBe(false);
  });

  it("returns null/false for empty string", () => {
    const { value, error } = parseExpectedPayload("");
    expect(value).toBeNull();
    expect(error).toBe(false);
  });

  it("returns null/false for whitespace-only string", () => {
    const { value, error } = parseExpectedPayload("   ");
    expect(value).toBeNull();
    expect(error).toBe(false);
  });

  it("returns null/true for invalid JSON", () => {
    const { value, error } = parseExpectedPayload("{bad json}");
    expect(value).toBeNull();
    expect(error).toBe(true);
  });

  it("handles nested objects", () => {
    const { value, error } = parseExpectedPayload('{"a":{"b":1}}');
    expect(value).toEqual({ a: { b: 1 } });
    expect(error).toBe(false);
  });
});

describe("buildSavePayload", () => {
  const baseState = {
    ...DEFAULT_FORM_STATE,
    name: "Test Agency",
    shortName: "TA",
    logo: "🏛️",
    description: "desc",
    connectionType: "API" as const,
    endpointUrl: "https://api.test.go.th",
    color: "hsl(200 60% 50%)",
    dataScope: ["citizens"],
    status: "active" as const,
    authMethod: "api_key",
    authHeader: "X-API-Key",
    basePath: "/v1",
    requestFormat: "json",
    apiEndpoints: [
      { method: "GET", path: "/users", description: "Get users" },
      { method: "POST", path: "", description: "Empty path — filtered out" },
    ],
    responseSchema: [
      { field: "id", type: "string", description: "User ID" },
      { field: "", type: "string", description: "Blank field — filtered out" },
    ],
    apiHeaders: [
      { name: "X-Source", value: "portal" },
      { name: "", value: "missing-name" },
      { name: "X-Env", value: "" },
    ],
    apiSpecRaw: "openapi: 3.0.0",
  };

  it("includes base fields in payload", () => {
    const payload = buildSavePayload(baseState, null);
    expect(payload.name).toBe("Test Agency");
    expect(payload.shortName).toBe("TA");
    expect(payload.logo).toBe("🏛️");
    expect(payload.connectionType).toBe("API");
    expect(payload.status).toBe("active");
    expect(payload.dataScope).toEqual(["citizens"]);
  });

  it("includes API-specific fields when connectionType is API", () => {
    const parsedPayload = { query: "test" };
    const payload = buildSavePayload(baseState, parsedPayload);
    expect(payload.authMethod).toBe("api_key");
    expect(payload.authHeader).toBe("X-API-Key");
    expect(payload.basePath).toBe("/v1");
    expect(payload.requestFormat).toBe("json");
    expect(payload.expectedPayload).toEqual({ query: "test" });
    expect(payload.apiSpecRaw).toBe("openapi: 3.0.0");
  });

  it("filters out endpoints with empty path", () => {
    const payload = buildSavePayload(baseState, null);
    expect(payload.apiEndpoints).toEqual([{ method: "GET", path: "/users", description: "Get users" }]);
  });

  it("filters out response schema fields with empty field name", () => {
    const payload = buildSavePayload(baseState, null);
    expect(payload.responseSchema).toEqual([{ field: "id", type: "string", description: "User ID" }]);
  });

  it("filters out headers where name or value is empty", () => {
    const payload = buildSavePayload(baseState, null);
    expect(payload.apiHeaders).toEqual([{ name: "X-Source", value: "portal" }]);
  });

  it("excludes API-specific fields for MCP connectionType", () => {
    const mcpState = { ...baseState, connectionType: "MCP" as const };
    const payload = buildSavePayload(mcpState, null);
    expect(payload.authMethod).toBeUndefined();
    expect(payload.authHeader).toBeUndefined();
    expect(payload.apiEndpoints).toBeUndefined();
  });

  it("excludes API-specific fields for A2A connectionType", () => {
    const a2aState = { ...baseState, connectionType: "A2A" as const };
    const payload = buildSavePayload(a2aState, null);
    expect(payload.authMethod).toBeUndefined();
    expect(payload.apiEndpoints).toBeUndefined();
  });

  it("passes parsedPayload through as expectedPayload for API type", () => {
    const parsed = { key: "value", nested: { a: 1 } };
    const payload = buildSavePayload(baseState, parsed);
    expect(payload.expectedPayload).toEqual(parsed);
  });

  it("passes null parsedPayload through for API type", () => {
    const payload = buildSavePayload(baseState, null);
    expect(payload.expectedPayload).toBeNull();
  });
});

describe("PROTOCOL_INFO", () => {
  it("has entries for all three connection types", () => {
    expect(PROTOCOL_INFO).toHaveProperty("MCP");
    expect(PROTOCOL_INFO).toHaveProperty("A2A");
    expect(PROTOCOL_INFO).toHaveProperty("API");
  });

  it("MCP entry mentions the protocol name", () => {
    expect(PROTOCOL_INFO.MCP).toContain("Model Context Protocol");
  });

  it("A2A entry mentions Agent-to-Agent", () => {
    expect(PROTOCOL_INFO.A2A).toContain("Agent-to-Agent");
  });
});

describe("wizard step validation", () => {
  it("defines five steps in order", () => {
    expect(WIZARD_STEPS.map((s) => s.id)).toEqual([
      "general",
      "connection",
      "test",
      "routing",
      "review",
    ]);
  });

  it("general step requires name and shortName", () => {
    expect(isStepGeneralValid({ ...DEFAULT_FORM_STATE })).toBe(false);
    expect(isStepGeneralValid({ ...DEFAULT_FORM_STATE, name: "กรมที่ดิน", shortName: "DOL" })).toBe(true);
  });

  it("connection step requires endpoint; MCP also requires a selected tool", () => {
    const api = { ...DEFAULT_FORM_STATE, connectionType: "API" as const };
    expect(isStepConnectionValid(api)).toBe(false);
    expect(isStepConnectionValid({ ...api, endpointUrl: "https://x.example" })).toBe(true);

    const mcp = { ...DEFAULT_FORM_STATE, connectionType: "MCP" as const, endpointUrl: "https://x.example/mcp" };
    expect(isStepConnectionValid(mcp)).toBe(false);
    expect(isStepConnectionValid({ ...mcp, mcpToolName: "chat" })).toBe(true);
  });

  it("canActivate requires general + connection", () => {
    expect(canActivate(DEFAULT_FORM_STATE)).toBe(false);
    expect(
      canActivate({
        ...DEFAULT_FORM_STATE,
        name: "กรมที่ดิน",
        shortName: "DOL",
        endpointUrl: "https://x.example",
      }),
    ).toBe(true);
  });

  it("firstIncompleteStep walks general → connection → test", () => {
    expect(firstIncompleteStep(DEFAULT_FORM_STATE)).toBe("general");
    expect(firstIncompleteStep({ ...DEFAULT_FORM_STATE, name: "ก", shortName: "ข" })).toBe("connection");
    expect(
      firstIncompleteStep({ ...DEFAULT_FORM_STATE, name: "ก", shortName: "ข", endpointUrl: "https://x.example" }),
    ).toBe("test");
  });
});

describe("isUrlValid", () => {
  it("returns true for a valid https URL", () => {
    expect(isUrlValid("https://api.example.com/v1")).toBe(true);
  });

  it("returns true for a valid http URL", () => {
    expect(isUrlValid("http://localhost:8080")).toBe(true);
  });

  it("returns false for a bare word", () => {
    expect(isUrlValid("not-a-url")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isUrlValid("")).toBe(false);
  });
});

describe("invalidHeaderIndices", () => {
  it("returns empty array for entirely empty rows", () => {
    expect(invalidHeaderIndices([{ name: "", value: "" }])).toEqual([]);
  });

  it("returns index for a row with value but empty name", () => {
    expect(invalidHeaderIndices([{ name: "", value: "bearer-token" }])).toEqual([0]);
  });

  it("returns index for a row with name but empty value", () => {
    expect(invalidHeaderIndices([{ name: "Authorization", value: "" }])).toEqual([0]);
  });

  it("ignores valid rows and returns only invalid ones", () => {
    const headers = [
      { name: "X-Source", value: "portal" },
      { name: "", value: "orphan-value" },
      { name: "", value: "" },
    ];
    expect(invalidHeaderIndices(headers)).toEqual([1]);
  });

  it("returns empty array for headers with both name and value", () => {
    expect(invalidHeaderIndices([{ name: "X-Key", value: "abc" }])).toEqual([]);
  });
});

describe("isStepConnectionValid — header gating", () => {
  const base = { ...DEFAULT_FORM_STATE, connectionType: "API" as const, endpointUrl: "https://x.example" };

  it("returns false when a header has a value but no name", () => {
    expect(isStepConnectionValid({ ...base, apiHeaders: [{ name: "", value: "v" }] })).toBe(false);
  });

  it("returns false when a header has a name but no value", () => {
    expect(isStepConnectionValid({ ...base, apiHeaders: [{ name: "X-Key", value: "" }] })).toBe(false);
  });

  it("returns true when all headers are valid", () => {
    expect(isStepConnectionValid({ ...base, apiHeaders: [{ name: "X-Key", value: "v" }] })).toBe(true);
  });

  it("returns true when headers contain only empty rows", () => {
    expect(isStepConnectionValid({ ...base, apiHeaders: [{ name: "", value: "" }] })).toBe(true);
  });
});

describe("buildSavePayload routing fields", () => {
  it("includes routing fields and parses numerics", () => {
    const payload = buildSavePayload(
      {
        ...DEFAULT_FORM_STATE,
        name: "ก",
        shortName: "ข",
        priority: "2",
        routerHint: "ภาษี",
        dispatchTimeoutS: "45",
        mcpToolName: "chat",
        connectionType: "MCP",
        endpointUrl: "https://x.example/mcp",
      },
      null,
    );
    expect(payload.priority).toBe(2);
    expect(payload.routerHint).toBe("ภาษี");
    expect(payload.dispatchTimeoutS).toBe(45);
    expect(payload.mcpToolName).toBe("chat");
  });

  it("maps empty numeric inputs to null", () => {
    const payload = buildSavePayload({ ...DEFAULT_FORM_STATE, name: "ก", shortName: "ข" }, null);
    expect(payload.priority).toBeNull();
    expect(payload.dispatchTimeoutS).toBeNull();
  });
});
