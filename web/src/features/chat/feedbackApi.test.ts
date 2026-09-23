import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";

import { updateMessageRating } from "./feedbackApi";

describe("updateMessageRating", () => {
  it("sends an up rating with null feedback_text and resolves true", async () => {
    let captured: { id: string; body: unknown } | undefined;
    server.use(
      http.patch("*/api/v1/messages/:id/rating", async ({ request, params }) => {
        captured = { id: String(params.id), body: await request.json() };
        return HttpResponse.json({ success: true, messageId: params.id });
      }),
    );

    const ok = await updateMessageRating("msg-1", "up");

    expect(ok).toBe(true);
    expect(captured?.id).toBe("msg-1");
    expect(captured?.body).toEqual({ rating: "up", feedback_text: null });
  });

  it("sends a down rating together with the feedback text", async () => {
    let body: unknown;
    server.use(
      http.patch("*/api/v1/messages/:id/rating", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ success: true, messageId: "msg-2" });
      }),
    );

    const ok = await updateMessageRating("msg-2", "down", "ไม่ตรงคำถาม");

    expect(ok).toBe(true);
    expect(body).toEqual({ rating: "down", feedback_text: "ไม่ตรงคำถาม" });
  });

  it("resolves false when the server errors, so the caller can roll back", async () => {
    server.use(
      http.patch("*/api/v1/messages/:id/rating", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    const ok = await updateMessageRating("msg-3", "up");

    expect(ok).toBe(false);
  });
});
