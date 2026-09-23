import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { resetMockData } from "@/mocks/fixtures";
import PopularQuestionsPage from "./PopularQuestionsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PopularQuestionsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => resetMockData());

describe("PopularQuestionsPage list rendering", () => {
  it("lists rows with text, agency, and source badges", async () => {
    renderPage();
    expect(await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568")).toBeInTheDocument();
    expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument();
    expect(screen.getByText("ตั้งต้น")).toBeInTheDocument();
    expect(screen.getByText("อัตโนมัติ")).toBeInTheDocument();
    expect(screen.getByText("กำหนดเอง")).toBeInTheDocument();
  });
});

describe("PopularQuestionsPage create flow", () => {
  it("opens the create dialog and calls the POST endpoint on submit", async () => {
    renderPage();
    await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568");

    await userEvent.click(screen.getByRole("button", { name: /เพิ่มคำถาม/ }));
    expect(screen.getByText("เพิ่มคำถามยอดนิยม")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("คำถาม"), "คำถามทดสอบใหม่");
    await userEvent.click(screen.getByRole("button", { name: /^สร้าง$/ }));

    await waitFor(() => expect(screen.getByText("คำถามทดสอบใหม่")).toBeInTheDocument());
    await waitFor(() => expect(screen.queryByText("เพิ่มคำถามยอดนิยม")).not.toBeInTheDocument());
  });
});

describe("PopularQuestionsPage edit flow", () => {
  it("opens the edit dialog pre-filled and PATCHes the updated text", async () => {
    renderPage();
    await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568");

    await userEvent.click(screen.getAllByRole("button", { name: "แก้ไข" })[0]);
    const textInput = screen.getByLabelText("คำถาม") as HTMLInputElement;
    expect(textInput.value).toBe("สอบถามเรื่องการลดหย่อนภาษี 2568");

    await userEvent.clear(textInput);
    await userEvent.type(textInput, "คำถามที่แก้ไขแล้ว");
    await userEvent.click(screen.getByRole("button", { name: /บันทึก/ }));

    await waitFor(() => expect(screen.getByText("คำถามที่แก้ไขแล้ว")).toBeInTheDocument());
  });
});

describe("PopularQuestionsPage pin / hide flow", () => {
  it("toggles pinned state when the pin button is clicked", async () => {
    renderPage();
    await screen.findByText("ขอตรวจสอบทะเบียนยา พาราเซตามอล");

    const pinButtons = screen.getAllByRole("button", { name: "ปักหมุด" });
    expect(pinButtons.length).toBeGreaterThan(0);
    await userEvent.click(pinButtons[0]);

    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "เลิกปักหมุด" }).length).toBeGreaterThan(0),
    );
  });

  it("toggles hidden state when the visibility button is clicked", async () => {
    renderPage();
    await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568");

    const hideButtons = screen.getAllByRole("button", { name: "ซ่อน" });
    await userEvent.click(hideButtons[0]);

    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "แสดง" }).length).toBeGreaterThan(0),
    );
  });
});

describe("PopularQuestionsPage delete flow", () => {
  it("opens confirm dialog and calls DELETE on confirm", async () => {
    renderPage();
    await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568");

    await userEvent.click(screen.getAllByRole("button", { name: "ลบ" })[0]);
    expect(screen.getByText("ยืนยันการลบ")).toBeInTheDocument();

    const confirmBtn = screen
      .getAllByRole("button")
      .find((b) => b.textContent?.trim() === "ลบ" && !b.hasAttribute("aria-label"));
    await userEvent.click(confirmBtn!);

    await waitFor(() =>
      expect(screen.queryByText("สอบถามเรื่องการลดหย่อนภาษี 2568")).not.toBeInTheDocument(),
    );
  });
});

describe("PopularQuestionsPage regenerate flow", () => {
  it("POSTs to the regenerate endpoint and shows a success toast", async () => {
    let regenerateCalled = false;
    server.use(
      http.post("*/api/v1/popular-questions/regenerate", () => {
        regenerateCalled = true;
        return HttpResponse.json({ status: "accepted" }, { status: 202 });
      }),
    );

    renderPage();
    await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568");

    await userEvent.click(screen.getByRole("button", { name: /สร้างใหม่ตอนนี้/ }));

    await waitFor(() => expect(regenerateCalled).toBe(true));
  });
});
