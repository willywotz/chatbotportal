import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { server } from "@/mocks/server";
import { fetchChatHistory } from "./historyApi";

describe("fetchChatHistory", () => {
  it("returns the API payload on success", async () => {
    const res = await fetchChatHistory();
    expect(res.success).toBe(true);
    expect(Array.isArray(res.data)).toBe(true);
  });

  it("throws when the API responds with an error (no mock fallback)", async () => {
    server.use(
      http.get("*/api/v1/history", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    await expect(fetchChatHistory()).rejects.toThrow();
  });

  it("throws when the API reports success=false (no mock fallback)", async () => {
    server.use(
      http.get("*/api/v1/history", () =>
        HttpResponse.json({ success: false, data: [], total: 0, responseTime: 0 }),
      ),
    );
    await expect(fetchChatHistory()).rejects.toThrow();
  });
});
