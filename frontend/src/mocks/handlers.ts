import { http, HttpResponse } from "msw";

import { LEGAL_TRANSITIONS } from "@/features/agencies/lifecycle";
import type { AgencyLifecycleStatus, AgencyRow, HealthWindow } from "@/shared/types/agency";
import type { HistoryItem } from "@/features/history/historyApi";
import { agencyUsageData, categoryData, dashboardStats, weeklyTrendData, conversationHistory } from "@/shared/data/mockData";

import type { PopularQuestionAdmin } from "@/features/popular-questions/popularQuestionsApi";

import { FIXTURE_MCP_TOOLS, makeHistory, mockAgencies, mockFeedbackStats, mockPopularQuestions, row } from "./fixtures";

const MOCK_HISTORY_ITEMS: HistoryItem[] = (conversationHistory as unknown as HistoryItem[]).map((c) => ({
  id: c.id,
  title: c.title,
  preview: c.preview,
  date: c.date,
  agencies: c.agencies,
  status: c.status,
}));

const MOCK_CONNECTION_LOGS = {
  search: null,
  page: 1,
  page_size: 20,
  items: [],
  total_items: 0,
  total_connections: 0,
  successful_connections: 0,
  failed_connections: 0,
  average_latency_ms: 0,
};

const MOCK_AGENCY_HEALTH = {
  agencies: [
    { id: "rd", name: "กรมสรรพากร", shortName: "RD", status: "healthy", uptime: 99.2, currentLatency: 320, avgLatency: 310, errorRate: 0.1, requestsPerMin: 42, lastCheckedAt: "2026-06-23T08:00:00Z" },
    { id: "fda", name: "สำนักงานอาหารและยา", shortName: "อย.", status: "degraded", uptime: 71.0, currentLatency: 1230, avgLatency: 1100, errorRate: 2.4, requestsPerMin: 12, lastCheckedAt: "2026-06-23T08:00:00Z" },
  ],
  historical: [
    { time: "00:00", rd_latency: 310, fda_latency: 1100 },
    { time: "01:00", rd_latency: 290, fda_latency: 1200 },
  ],
  incidents: [],
  slaCompliance: [
    { agency: "กรมสรรพากร", uptime: 99.2, target: 99.0, met: true },
  ],
  generatedAt: "2026-06-23T08:00:00Z",
};

const MOCK_HEATMAP = {
  range: "7d" as const,
  days: 7,
  sampleSize: 1000,
  totalMessages: 5000,
  days_labels: ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"],
  hours: Array.from({ length: 24 }, (_, i) => i),
  agencies: [{ id: "rd", name: "กรมสรรพากร" }],
  hourlyByAgency: [{ agency: "กรมสรรพากร", agencyId: "rd", data: Array(24).fill(10) }],
  dayHourMatrix: [{ day: "จ", dayIndex: 1, data: Array(24).fill(5) }],
  insights: {
    peakDay: "พุธ",
    peakHour: "10:00",
    peakValue: 150,
    totalRequests: 1000,
    businessHoursPercent: 80,
    busiest: { agency: "กรมสรรพากร", total: 500, peakHour: 10 },
    recommendation: "เพิ่มทรัพยากรช่วง 09-11 น.",
  },
  generatedAt: "2026-06-23T08:00:00Z",
};

function findAgency(id: string): AgencyRow | undefined {
  return mockAgencies.find((a) => a.id === id);
}

export const handlers = [
  http.get("*/api/v1/history", ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "0");
    const dateFrom = url.searchParams.get("date_from");
    const dateTo = url.searchParams.get("date_to");
    const search = url.searchParams.get("search") ?? "";

    let items = MOCK_HISTORY_ITEMS;
    if (search) items = items.filter((c) => c.title.includes(search) || c.preview.includes(search));
    if (dateFrom) items = items.filter((c) => c.date >= dateFrom);
    if (dateTo) items = items.filter((c) => c.date <= dateTo);

    const total = items.length;
    const data = pageSize > 0 ? items.slice((page - 1) * pageSize, page * pageSize) : items;
    return HttpResponse.json({ success: true, data, total, responseTime: 10 });
  }),

  http.post("*/api/v1/history", async ({ request }) => {
    const body = (await request.json()) as Partial<HistoryItem>;
    const created: HistoryItem = {
      id: crypto.randomUUID(),
      title: body.title ?? "",
      preview: body.preview ?? "",
      date: new Date().toISOString().slice(0, 10),
      agencies: body.agencies ?? [],
      status: body.status ?? "success",
    };
    MOCK_HISTORY_ITEMS.push(created);
    return HttpResponse.json({ success: true, conversationId: created.id }, { status: 201 });
  }),

  http.delete("*/api/v1/history/:id", ({ params }) => {
    const idx = MOCK_HISTORY_ITEMS.findIndex((c) => c.id === params.id);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    MOCK_HISTORY_ITEMS.splice(idx, 1);
    return HttpResponse.json({ success: true });
  }),

  http.get("*/api/v1/history/:id/messages", () =>
    HttpResponse.json({ success: true, data: [] }),
  ),

  http.get("*/api/v1/connection-logs/information", () =>
    HttpResponse.json({
      total_connections: 0,
      successful_connections: 0,
      failed_connections: 0,
      average_latency_ms: 0,
    }),
  ),

  http.get("*/api/v1/connection-logs", ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const connectionType = url.searchParams.get("connection_type");
    const agencyId = url.searchParams.get("agency_id");
    const page = Number(url.searchParams.get("page") ?? "1");
    const limit = Number(url.searchParams.get("limit") ?? "20");

    return HttpResponse.json({
      ...MOCK_CONNECTION_LOGS,
      page,
      page_size: limit,
      // Echo back filters in search field for test introspection
      search: [status, connectionType, agencyId].filter(Boolean).join(",") || null,
    });
  }),

  http.get("*/api/v1/agency-health", () => HttpResponse.json(MOCK_AGENCY_HEALTH)),

  http.get("*/api/v1/usage-heatmap", () => HttpResponse.json(MOCK_HEATMAP)),

  http.get("*/api/v1/dashboard/statistics", () =>
    HttpResponse.json({
      success: true,
      data: { stats: dashboardStats, agencyUsage: agencyUsageData, weeklyTrend: weeklyTrendData, categoryData },
      responseTime: 42,
    }),
  ),

  http.get("*/api/v1/insight/usage", () =>
    HttpResponse.json([
      { key: "claude-3-5-sonnet", prompt_tokens: 10000, completion_tokens: 2000, cost_usd: 0.036 },
    ]),
  ),

  http.get("*/api/v1/feedback/statistics", () => HttpResponse.json(mockFeedbackStats)),

  http.patch("*/api/v1/messages/:id/rating", ({ params }) =>
    HttpResponse.json({ success: true, messageId: params.id }),
  ),

  http.get("*/api/v1/agencies", () =>
    HttpResponse.json({ data: mockAgencies, total: mockAgencies.length }),
  ),

  http.get("*/api/v1/agencies/:id/health/history", ({ params, request }) => {
    const agency = findAgency(params.id as string);
    if (!agency) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    const url = new URL(request.url);
    const window = (url.searchParams.get("window") ?? "24h") as HealthWindow;
    if (!["24h", "7d", "30d"].includes(window)) {
      return HttpResponse.json({ detail: "invalid window" }, { status: 422 });
    }
    return HttpResponse.json({ data: makeHistory(agency.id, window) });
  }),

  http.patch("*/api/v1/agencies/:id/status", async ({ params, request }) => {
    const agency = findAgency(params.id as string);
    if (!agency) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    const body = (await request.json()) as { status: AgencyLifecycleStatus };
    const from = agency.status as AgencyLifecycleStatus;
    if (!LEGAL_TRANSITIONS[from]?.includes(body.status)) {
      return HttpResponse.json(
        { detail: `Illegal transition: ${from} → ${body.status}` },
        { status: 422 },
      );
    }
    if (from === "draft" && body.status === "active" && !agency.conformance_report?.passed) {
      return HttpResponse.json(
        { error: { code: "invalid_request", message: "conformance test must pass before activation" } },
        { status: 400 },
      );
    }
    agency.status = body.status;
    return HttpResponse.json(agency);
  }),

  http.post("*/api/v1/agencies/:id/conformance", ({ params }) => {
    const agency = findAgency(params.id as string);
    if (!agency) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    const report = {
      ran_at: new Date().toISOString(),
      passed: true,
      checks: [
        { name: "responds", passed: true, detail: "120ms" },
        { name: "non_empty", passed: true, detail: "" },
        { name: "thai_text", passed: true, detail: "" },
        { name: "concurrency_3", passed: true, detail: "" },
        { name: "garbage_input", passed: true, detail: "did not crash" },
      ],
    };
    agency.conformance_report = report;
    return HttpResponse.json(report);
  }),

  http.post("*/api/v1/agencies/mcp/discover", async ({ request }) => {
    const body = (await request.json()) as { endpoint_url?: string };
    if (!body.endpoint_url) {
      return HttpResponse.json({ detail: "endpoint_url is required" }, { status: 422 });
    }
    return HttpResponse.json({ tools: FIXTURE_MCP_TOOLS });
  }),

  http.post("*/api/v1/agencies", async ({ request }) => {
    const body = (await request.json()) as Partial<AgencyRow>;
    const created = row({
      ...body,
      id: crypto.randomUUID(),
      name: body.name ?? "",
      short_name: body.short_name ?? "",
      status: body.status ?? "draft",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    mockAgencies.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.patch("*/api/v1/agencies/:id", async ({ params, request }) => {
    const agency = findAgency(params.id as string);
    if (!agency) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    const body = (await request.json()) as Partial<AgencyRow>;
    Object.assign(agency, body, { updated_at: new Date().toISOString() });
    return HttpResponse.json(agency);
  }),

  http.delete("*/api/v1/agencies/:id", ({ params }) => {
    const idx = mockAgencies.findIndex((a) => a.id === params.id);
    if (idx === -1) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    mockAgencies.splice(idx, 1);
    return HttpResponse.json({ success: true });
  }),

  http.post("*/api/v1/agencies/:id/logo", async ({ params, request }) => {
    const agency = findAgency(params.id as string);
    if (!agency) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    const formData = await request.formData();
    const file = formData.get("file");
    if (!file) return HttpResponse.json({ detail: "file is required" }, { status: 422 });
    agency.logo = `/api/v1/agencies/${agency.id}/logo?v=abcd1234`;
    agency.updated_at = new Date().toISOString();
    return HttpResponse.json(agency);
  }),

  http.get("*/api/v1/agencies/:id/test", ({ params }) => {
    const agency = findAgency(params.id as string);
    if (!agency) return HttpResponse.json({ detail: "Agency not found" }, { status: 404 });
    return HttpResponse.json({
      success: true,
      protocol: agency.connection_type,
      version: "1.0",
      steps: [
        { step: 1, label: "DNS lookup", status: "done", time: 12 },
        { step: 2, label: "Handshake", status: "done", time: 120 },
      ],
      latency: "320ms",
    });
  }),

  http.get("*/api/v1/public/agencies", () => {
    const data = mockAgencies
      .filter((a) => a.status !== "draft")
      .map((a) => ({
        id: a.id,
        name: a.name,
        short_name: a.short_name,
        logo: a.logo,
        description: a.description,
        connection_type: a.connection_type,
        status: a.status,
      }));
    return HttpResponse.json(data);
  }),

  http.get("*/api/v1/public/popular-questions", () => {
    const data = mockPopularQuestions
      .filter((q) => !q.hidden)
      .sort((a, b) => a.sort_order - b.sort_order)
      .slice(0, 8)
      .map(({ id, text, agency }) => ({ id, text, agency }));
    return HttpResponse.json({ data });
  }),

  http.get("*/api/v1/popular-questions", () =>
    HttpResponse.json({ data: mockPopularQuestions, total: mockPopularQuestions.length }),
  ),

  http.post("*/api/v1/popular-questions", async ({ request }) => {
    const body = (await request.json()) as { text: string; agency_id?: string | null };
    const agency = body.agency_id ? findAgency(body.agency_id) : undefined;
    const created: PopularQuestionAdmin = {
      id: crypto.randomUUID(),
      text: body.text,
      agency: agency ? { id: agency.id, name: agency.name, logo: agency.logo } : null,
      source: "manual",
      pinned: false,
      hidden: false,
      sort_order: mockPopularQuestions.length,
      score: 0,
    };
    mockPopularQuestions.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.patch("*/api/v1/popular-questions/:id", async ({ params, request }) => {
    const question = mockPopularQuestions.find((q) => q.id === params.id);
    if (!question) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<{
      text: string;
      agency_id: string | null;
      pinned: boolean;
      hidden: boolean;
      sort_order: number;
    }>;
    if (body.text !== undefined) question.text = body.text;
    if (body.pinned !== undefined) question.pinned = body.pinned;
    if (body.hidden !== undefined) question.hidden = body.hidden;
    if (body.sort_order !== undefined) question.sort_order = body.sort_order;
    if (body.agency_id !== undefined) {
      const agency = body.agency_id ? findAgency(body.agency_id) : undefined;
      question.agency = agency ? { id: agency.id, name: agency.name, logo: agency.logo } : null;
    }
    return HttpResponse.json(question);
  }),

  http.delete("*/api/v1/popular-questions/:id", ({ params }) => {
    const idx = mockPopularQuestions.findIndex((q) => q.id === params.id);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    mockPopularQuestions.splice(idx, 1);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("*/api/v1/popular-questions/regenerate", () =>
    HttpResponse.json({ status: "scheduled" }, { status: 202 }),
  ),
];
