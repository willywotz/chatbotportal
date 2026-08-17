import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockAgencies, resetMockData } from "@/mocks/fixtures";
import { mapRowToAgency } from "@/shared/types/agency";

import { ConnectionTab } from "./ConnectionTab";
import { GeneralSection } from "./GeneralSection";
import { RoutingTab } from "./RoutingTab";

// jsdom's XHR/fetch stack can't encode real multipart bodies, so the logo
// upload mutation is mocked here; its own network wiring is exercised
// separately in useAgencies.test.tsx-style hook tests where relevant.
const { mockUploadLogo } = vi.hoisted(() => ({ mockUploadLogo: vi.fn() }));
vi.mock("../useAgencies", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useAgencies")>();
  return { ...actual, useUploadAgencyLogo: () => ({ mutateAsync: mockUploadLogo, isPending: false }) };
});

afterEach(() => {
  resetMockData();
  mockUploadLogo.mockReset();
});

const ACTIVE_ID = "11111111-1111-1111-1111-111111111111";
const DRAFT_ID = "33333333-3333-3333-3333-333333333333";

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function activeAgency() {
  return mapRowToAgency(mockAgencies.find((a) => a.id === ACTIVE_ID)!);
}

function draftAgency() {
  return mapRowToAgency(mockAgencies.find((a) => a.id === DRAFT_ID)!);
}

describe("ConnectionTab", () => {
  it("disables save button when endpoint URL is invalid", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    await user.type(input, "not-a-valid-url");
    expect(screen.getByRole("button", { name: /บันทึก/ })).toBeDisabled();
  });

  it("enables save button when endpoint URL is valid", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    await user.type(input, "https://valid.example/api");
    expect(screen.getByRole("button", { name: /บันทึก/ })).not.toBeDisabled();
  });

  it("saves an edited endpoint", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    await user.type(input, "https://rd-new.example/api/chat");
    await user.click(screen.getByRole("button", { name: /บันทึก/ }));
    await user.click(await screen.findByRole("button", { name: "ยืนยัน" }));
    await waitFor(() =>
      expect(mockAgencies.find((a) => a.id === ACTIVE_ID)!.endpoint_url).toBe(
        "https://rd-new.example/api/chat",
      ),
    );
  });

  it("shows a confirm dialog before saving a connection-identity change on an active agency", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    await user.type(input, "https://rd-new.example/api/chat");
    await user.click(screen.getByRole("button", { name: /บันทึก/ }));
    expect(await screen.findByText(/จะทำให้หน่วยงานกลับเป็น Draft/)).toBeInTheDocument();
    expect(mockAgencies.find((a) => a.id === ACTIVE_ID)!.endpoint_url).not.toBe(
      "https://rd-new.example/api/chat",
    );
    await user.click(screen.getByRole("button", { name: "ยืนยัน" }));
    await waitFor(() =>
      expect(mockAgencies.find((a) => a.id === ACTIVE_ID)!.endpoint_url).toBe(
        "https://rd-new.example/api/chat",
      ),
    );
  });

  it("saves directly with no confirm dialog on a draft agency", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={draftAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    await user.type(input, "https://dol-new.example/api");
    await user.click(screen.getByRole("button", { name: /บันทึก/ }));
    expect(screen.queryByText(/จะทำให้หน่วยงานกลับเป็น Draft/)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(mockAgencies.find((a) => a.id === DRAFT_ID)!.endpoint_url).toBe(
        "https://dol-new.example/api",
      ),
    );
  });

  it("renders the connection-type toggle and switches visible fields", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    expect(screen.getByLabelText(/Expected payload/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "MCP" }));
    expect(screen.getByLabelText("MCP tool")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Expected payload/)).not.toBeInTheDocument();
  });

  it("shows wizard-style gray placeholders for empty connection fields", () => {
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    expect(screen.getByPlaceholderText("https://…")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/"query": "__query__"/)).toBeInTheDocument();
  });

  it("shows URL error message when endpoint URL is invalid", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    await user.type(input, "not-a-valid-url");
    expect(screen.getByText("URL ไม่ถูกต้อง")).toBeInTheDocument();
  });

  it("does not show URL error message when endpoint URL is empty", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const input = screen.getByLabelText("Endpoint URL");
    await user.clear(input);
    expect(screen.queryByText("URL ไม่ถูกต้อง")).not.toBeInTheDocument();
  });

  it("disables save button when a header has a value but no name", async () => {
    const user = userEvent.setup();
    const agency = activeAgency();
    render(wrap(<ConnectionTab agency={{ ...agency, apiHeaders: [{ name: "", value: "bearer-token" }] }} />));
    expect(screen.getByRole("button", { name: /บันทึก/ })).toBeDisabled();
  });

  it("does not disable save button for entirely empty header rows", async () => {
    const user = userEvent.setup();
    render(wrap(<ConnectionTab agency={activeAgency()} />));
    const addBtn = screen.getByRole("button", { name: /เพิ่ม header/ });
    await user.click(addBtn);
    expect(screen.getByRole("button", { name: /บันทึก/ })).not.toBeDisabled();
  });

  it("shows header error message when a header has a value but no name", () => {
    const agency = activeAgency();
    render(wrap(<ConnectionTab agency={{ ...agency, apiHeaders: [{ name: "", value: "bearer-token" }] }} />));
    expect(screen.getAllByText("กรุณากรอก Header name และ Value ให้ครบ").length).toBeGreaterThan(0);
  });
});

describe("RoutingTab", () => {
  it("saves routing fields", async () => {
    const user = userEvent.setup();
    render(wrap(<RoutingTab agency={activeAgency()} />));
    const hint = screen.getByLabelText(/Router hint/);
    await user.clear(hint);
    await user.type(hint, "ภาษีทุกชนิด");
    const priority = screen.getByLabelText(/Priority/);
    await user.clear(priority);
    await user.type(priority, "5");
    await user.click(screen.getByRole("button", { name: /บันทึก/ }));
    await waitFor(() => {
      const row = mockAgencies.find((a) => a.id === ACTIVE_ID)!;
      expect(row.router_hint).toBe("ภาษีทุกชนิด");
      expect(row.priority).toBe(5);
    });
  });

  it("edits data scope", async () => {
    const user = userEvent.setup();
    render(wrap(<RoutingTab agency={activeAgency()} />));
    await user.type(screen.getByPlaceholderText(/เพิ่มขอบเขตข้อมูล/), "ภาษีมูลค่าเพิ่ม");
    await user.click(screen.getByRole("button", { name: "เพิ่มขอบเขต" }));
    await user.click(screen.getByRole("button", { name: /บันทึก/ }));
    await waitFor(() =>
      expect(mockAgencies.find((a) => a.id === ACTIVE_ID)!.data_scope).toContain("ภาษีมูลค่าเพิ่ม"),
    );
  });

  it("shows wizard-style gray placeholders for empty routing fields", () => {
    render(wrap(<RoutingTab agency={activeAgency()} />));
    expect(screen.getByPlaceholderText(/อธิบายว่าหน่วยงานนี้ตอบคำถาม/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("เช่น 1")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("ค่าเริ่มต้นระบบ")).toBeInTheDocument();
  });
});

describe("GeneralSection", () => {
  it("disables save button when name is blank", async () => {
    const user = userEvent.setup();
    render(wrap(<GeneralSection agency={activeAgency()} />));
    await user.clear(screen.getByLabelText("ชื่อหน่วยงาน"));
    expect(screen.getByRole("button", { name: /บันทึก/ })).toBeDisabled();
  });

  it("disables save button when short name is blank", async () => {
    const user = userEvent.setup();
    render(wrap(<GeneralSection agency={activeAgency()} />));
    await user.clear(screen.getByLabelText("ชื่อย่อ"));
    expect(screen.getByRole("button", { name: /บันทึก/ })).toBeDisabled();
  });

  it("saves a valid edit", async () => {
    const user = userEvent.setup();
    render(wrap(<GeneralSection agency={activeAgency()} />));
    const nameInput = screen.getByLabelText("ชื่อหน่วยงาน");
    await user.clear(nameInput);
    await user.type(nameInput, "กรมสรรพากรใหม่");
    await user.click(screen.getByRole("button", { name: /บันทึก/ }));
    await waitFor(() =>
      expect(mockAgencies.find((a) => a.id === ACTIVE_ID)!.name).toBe("กรมสรรพากรใหม่"),
    );
  });

  it("shows a native hex color picker seeded from the agency color", () => {
    render(wrap(<GeneralSection agency={activeAgency()} />));
    const colorInput = screen.getByLabelText("สี") as HTMLInputElement;
    expect(colorInput).toHaveAttribute("type", "color");
    expect(colorInput.value).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("uploads a logo file and syncs the preview to the returned path", async () => {
    const user = userEvent.setup();
    const uploadedLogo = `/api/v1/agencies/${ACTIVE_ID}/logo?v=abcd1234`;
    mockUploadLogo.mockResolvedValueOnce({ ...activeAgency(), logo: uploadedLogo });
    render(wrap(<GeneralSection agency={activeAgency()} />));
    const file = new File(["x"], "logo.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);
    expect(mockUploadLogo).toHaveBeenCalledWith({ id: ACTIVE_ID, file });
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", uploadedLogo));
  });

  it("rejects an oversized logo file before calling the upload mutation", async () => {
    const user = userEvent.setup();
    render(wrap(<GeneralSection agency={activeAgency()} />));
    const big = new File([new Uint8Array(600 * 1024)], "big.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, big);
    expect(mockUploadLogo).not.toHaveBeenCalled();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
