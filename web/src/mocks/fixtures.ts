import type { AgencyRow, HealthHistoryBucketRow, HealthWindow } from "@/shared/types/agency";
import type { PopularQuestionAdmin } from "@/features/popular-questions/popularQuestionsApi";
import type { HistoryItem } from "@/features/history/historyApi";
import type {
  AgencyUsageDatum,
  CategoryDatum,
  DashboardStats,
  WeeklyTrendDatum,
} from "@/shared/types/dashboard";

export function row(partial: Partial<AgencyRow> & Pick<AgencyRow, "id" | "name" | "short_name">): AgencyRow {
  return {
    logo: "🏢",
    connection_type: "API",
    status: "active",
    description: "",
    data_scope: [],
    total_calls: 0,
    color: "#2563eb",
    endpoint_url: "",
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
    priority: null,
    router_hint: "",
    dispatch_timeout_s: null,
    mcp_tool_name: null,
    rating_up: 0,
    rating_down: 0,
    health: null,
    ...partial,
  };
}

export function makeFixtureAgencies(): AgencyRow[] {
  return [
    row({
      id: "11111111-1111-1111-1111-111111111111",
      name: "กรมสรรพากร",
      short_name: "RD",
      logo: "🏛️",
      connection_type: "API",
      status: "active",
      description: "ข้อมูลภาษีอากร",
      data_scope: ["ภาษี", "ภาษีเงินได้"],
      total_calls: 1204,
      endpoint_url: "https://rd.example/api/chat",
      expected_payload: { query: "__query__", session_id: "__session_id__" },
      priority: 1,
      router_hint: "คำถามเกี่ยวกับภาษีทุกประเภท",
      dispatch_timeout_s: 30,
      rating_up: 41,
      rating_down: 3,
      health: { state: "up", uptime_24h: 99.2, avg_latency_ms_24h: 320, last_check_at: "2026-06-11T08:00:00Z" },
    }),
    row({
      id: "22222222-2222-2222-2222-222222222222",
      name: "สำนักงานคณะกรรมการอาหารและยา",
      short_name: "อย.",
      logo: "💊",
      connection_type: "MCP",
      status: "active",
      description: "ข้อมูลอาหารและยา",
      data_scope: ["ยา", "อาหาร", "เครื่องสำอาง"],
      total_calls: 458,
      endpoint_url: "https://fda.example/mcp",
      mcp_tool_name: "chat_with_fda",
      priority: 2,
      health: { state: "degraded", uptime_24h: 71.0, avg_latency_ms_24h: 1230, last_check_at: "2026-06-11T08:00:00Z" },
    }),
    row({
      id: "33333333-3333-3333-3333-333333333333",
      name: "กรมที่ดิน",
      short_name: "DOL",
      logo: "🗂️",
      connection_type: "A2A",
      status: "draft",
      description: "ข้อมูลโฉนดที่ดิน",
    }),
    row({
      id: "44444444-4444-4444-4444-444444444444",
      name: "กรมการปกครอง",
      short_name: "DOPA",
      logo: "🪪",
      connection_type: "API",
      status: "disabled",
      description: "ข้อมูลทะเบียนราษฎร",
      endpoint_url: "https://dopa.example/api/chat",
    }),
    row({
      id: "55555555-5555-5555-5555-555555555555",
      name: "กรมขนส่งทางบก",
      short_name: "DLT",
      logo: "🚗",
      connection_type: "API",
      status: "maintenance",
      description: "ข้อมูลใบขับขี่และทะเบียนรถ",
      data_scope: ["ใบขับขี่", "ทะเบียนรถ"],
      endpoint_url: "https://dlt.example/api/chat",
      priority: 3,
      health: { state: "down", uptime_24h: 12.5, avg_latency_ms_24h: 2100, last_check_at: "2026-06-11T07:30:00Z" },
    }),
  ];
}

/** Mutable in-memory store the handlers operate on. */
export let mockAgencies: AgencyRow[] = makeFixtureAgencies();

export function makeFixturePopularQuestions(): PopularQuestionAdmin[] {
  return [
    {
      id: "pq-1",
      text: "สอบถามเรื่องการลดหย่อนภาษี 2568",
      agency: { id: "11111111-1111-1111-1111-111111111111", name: "กรมสรรพากร", logo: "🏛️" },
      source: "seed",
      pinned: true,
      hidden: false,
      sort_order: 0,
      score: 42,
    },
    {
      id: "pq-2",
      text: "ขอตรวจสอบทะเบียนยา พาราเซตามอล",
      agency: { id: "22222222-2222-2222-2222-222222222222", name: "สำนักงานคณะกรรมการอาหารและยา", logo: "💊" },
      source: "auto",
      pinned: false,
      hidden: false,
      sort_order: 1,
      score: 18,
    },
    {
      id: "pq-3",
      text: "คำถามทั่วไปที่ไม่มีหน่วยงานเจ้าของ",
      agency: null,
      source: "manual",
      pinned: false,
      hidden: true,
      sort_order: 2,
      score: 3,
    },
  ];
}

export let mockPopularQuestions: PopularQuestionAdmin[] = makeFixturePopularQuestions();

export function resetMockData(): void {
  mockAgencies = makeFixtureAgencies();
  mockPopularQuestions = makeFixturePopularQuestions();
}

export const FIXTURE_MCP_TOOLS = [
  { name: "chat_with_fda", description: "ถามตอบข้อมูล อย.", input_schema: { type: "object", properties: { query: { type: "string" } } } },
  { name: "search_products", description: "ค้นหาผลิตภัณฑ์", input_schema: { type: "object", properties: { keyword: { type: "string" } } } },
];

const WINDOW_BUCKETS: Record<HealthWindow, { count: number; stepMs: number }> = {
  "24h": { count: 24, stepMs: 3_600_000 },
  "7d": { count: 7 * 24, stepMs: 3_600_000 },
  "30d": { count: 30, stepMs: 86_400_000 },
};

export function makeHistory(agencyId: string, window: HealthWindow): HealthHistoryBucketRow[] {
  const { count, stepMs } = WINDOW_BUCKETS[window];
  const end = Date.now();
  // Deterministic pseudo-random per agency so charts look real but stable.
  const seed = agencyId.charCodeAt(0) + agencyId.charCodeAt(2);
  return Array.from({ length: count }, (_, i) => {
    const wave = Math.abs(Math.sin((i + seed) / 5));
    const failures = wave > 0.93 ? 2 : wave > 0.85 ? 1 : 0;
    const checks = 12;
    return {
      bucket_start: new Date(end - (count - i) * stepMs).toISOString(),
      uptime_pct: Math.round(((checks - failures) / checks) * 1000) / 10,
      avg_latency_ms: Math.round(250 + wave * 900),
      checks,
      failures,
    };
  });
}

export const dashboardStats: DashboardStats = {
  totalQuestions: 0,
  totalQuestionsTrend: 0.0,
  todayQuestions: 0,
  todayQuestionsTrend: 0.0,
  avgResponseTime: 0.0,
  avgResponseTimeTrend: 0.0,
  satisfactionRate: 0.0,
  satisfactionRateTrend: 0.0,
};

export const agencyUsageData: AgencyUsageDatum[] = [
  { name: "อย.", value: 12450, fill: "hsl(145 55% 40%)" },
  { name: "กรมสรรพากร", value: 18320, fill: "hsl(213 70% 45%)" },
  { name: "กรมการปกครอง", value: 9870, fill: "hsl(25 85% 55%)" },
  { name: "กรมที่ดิน", value: 7650, fill: "hsl(280 50% 50%)" },
];

export const weeklyTrendData: WeeklyTrendDatum[] = [
  { day: "จันทร์", questions: 180 },
  { day: "อังคาร", questions: 210 },
  { day: "พุธ", questions: 195 },
  { day: "พฤหัสบดี", questions: 240 },
  { day: "ศุกร์", questions: 220 },
  { day: "เสาร์", questions: 90 },
  { day: "อาทิตย์", questions: 65 },
];

export const categoryData: CategoryDatum[] = [
  { category: "สอบถามข้อมูล", count: 22450 },
  { category: "ตรวจสอบสถานะ", count: 12300 },
  { category: "ขั้นตอนดำเนินการ", count: 8900 },
  { category: "กฎหมาย/ระเบียบ", count: 4640 },
];

export function makeFixtureHistoryItems(): HistoryItem[] {
  return [
    {
      id: "conv-1",
      title: "ตรวจสอบทะเบียนยาพาราเซตามอล",
      preview: "ยาพาราเซตามอลที่ขายตามร้านขายยาทั่วไป ต้องขึ้นทะเบียนกับ อย. หรือไม่?",
      date: "2568-02-22",
      agencies: ["อย.", "กรมสรรพากร"],
      status: "success",
    },
    {
      id: "conv-2",
      title: "สอบถามเรื่องลดหย่อนภาษี",
      preview: "ค่าลดหย่อนภาษีเงินได้บุคคลธรรมดาปี 2568 มีอะไรบ้าง?",
      date: "2568-02-21",
      agencies: ["กรมสรรพากร"],
      status: "success",
    },
    {
      id: "conv-3",
      title: "ขั้นตอนทำบัตรประชาชนใหม่",
      preview: "บัตรประชาชนหาย ต้องทำอย่างไร ใช้เอกสารอะไรบ้าง?",
      date: "2568-02-20",
      agencies: ["กรมการปกครอง"],
      status: "success",
    },
    {
      id: "conv-4",
      title: "ราคาประเมินที่ดิน กรุงเทพ",
      preview: "ตรวจสอบราคาประเมินที่ดินในเขตบางรัก กรุงเทพมหานคร",
      date: "2568-02-19",
      agencies: ["กรมที่ดิน"],
      status: "success",
    },
    {
      id: "conv-5",
      title: "นำเข้าอาหารเสริม",
      preview: "ขั้นตอนการนำเข้าอาหารเสริมจากต่างประเทศ ต้องขออนุญาตจากหน่วยงานใดบ้าง?",
      date: "2568-02-18",
      agencies: ["อย.", "กรมสรรพากร"],
      status: "failed",
    },
  ];
}

export const mockFeedbackStats = {
  total_ratings: 42,
  up_count: 30,
  down_count: 12,
  satisfaction_rate: 71,
  daily_trend: [
    { date: "01/06", up: 3, down: 1, rate: 75 },
    { date: "02/06", up: 5, down: 2, rate: 71 },
  ],
  low_rated_questions: [
    {
      content: "ทำไมระบบตอบช้า",
      feedback_text: "ไม่ตรงคำถาม",
      agency: "กรมสรรพากร",
      created_at: "2026-06-01T10:00:00Z",
    },
  ],
  agency_breakdown: [
    { agency: "กรมสรรพากร", up: 20, down: 5, rate: 80 },
    { agency: "กรมที่ดิน", up: 10, down: 7, rate: 59 },
  ],
};
