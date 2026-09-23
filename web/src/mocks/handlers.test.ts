import { afterEach, describe, expect, it } from "vitest";

import { resetMockData } from "./fixtures";

afterEach(() => {
  resetMockData();
});

const BASE = "http://localhost:3000";

describe("agency mock handlers", () => {
  it("GET /api/v1/agencies returns fixtures with embedded health", async () => {
    const res = await fetch(`${BASE}/api/v1/agencies`);
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.total).toBeGreaterThanOrEqual(5);
    const active = body.data.find((a: { status: string }) => a.status === "active");
    expect(active.health.state).toBeDefined();
    expect(active.health.uptime_24h).not.toBeNull();
  });

  it("GET health/history returns buckets for a window", async () => {
    const list = await (await fetch(`${BASE}/api/v1/agencies`)).json();
    const id = list.data[0].id;
    const res = await fetch(`${BASE}/api/v1/agencies/${id}/health/history?window=24h`);
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.data.length).toBe(24);
    expect(body.data[0]).toHaveProperty("bucket_start");
    expect(body.data[0]).toHaveProperty("uptime_pct");
    expect(body.data[0]).toHaveProperty("avg_latency_ms");
  });

  it("PATCH status applies a legal transition and rejects an illegal one with 422", async () => {
    const list = await (await fetch(`${BASE}/api/v1/agencies`)).json();
    const active = list.data.find((a: { status: string }) => a.status === "active");

    const ok = await fetch(`${BASE}/api/v1/agencies/${active.id}/status`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "maintenance" }),
    });
    expect(ok.status).toBe(200);
    expect((await ok.json()).status).toBe("maintenance");

    const bad = await fetch(`${BASE}/api/v1/agencies/${active.id}/status`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "draft" }),
    });
    expect(bad.status).toBe(422);
    expect((await bad.json()).detail).toContain("transition");
  });

  it("POST mcp/discover returns tools", async () => {
    const res = await fetch(`${BASE}/api/v1/agencies/mcp/discover`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ endpoint_url: "https://mcp.example/sse" }),
    });
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.tools.length).toBeGreaterThan(0);
    expect(body.tools[0]).toHaveProperty("name");
    expect(body.tools[0]).toHaveProperty("input_schema");
  });

  it("POST /api/v1/agencies creates a draft with partial config", async () => {
    const res = await fetch(`${BASE}/api/v1/agencies`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "กรมใหม่", short_name: "NEW", status: "draft" }),
    });
    const body = await res.json();
    expect(res.status).toBe(201);
    expect(body.id).toBeTruthy();
    expect(body.status).toBe("draft");
    expect(body.health).toBeNull();
    expect(body.name).toBe("กรมใหม่");
    expect(body.logo).toBe("🏢");
    expect(body.connection_type).toBe("API");
  });

  it("POST preserves explicitly provided fields", async () => {
    const res = await fetch(`${BASE}/api/v1/agencies`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "x", short_name: "X", logo: "🚀", connection_type: "MCP" }),
    });
    const body = await res.json();
    expect(body.logo).toBe("🚀");
    expect(body.connection_type).toBe("MCP");
  });
});
