import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ApiKeysPage from "./ApiKeysPage";
import type { APIKey, CreatedAPIKey } from "./apiKeyApi";

const mockListAPIKeys = vi.fn();
const mockCreateAPIKey = vi.fn();
const mockUpdateAPIKey = vi.fn();
const mockRevokeAPIKey = vi.fn();
const mockDeleteAPIKey = vi.fn();

vi.mock("@/features/api-keys/apiKeyApi", () => ({
  listAPIKeys: (...args: unknown[]) => mockListAPIKeys(...args),
  createAPIKey: (...args: unknown[]) => mockCreateAPIKey(...args),
  updateAPIKey: (...args: unknown[]) => mockUpdateAPIKey(...args),
  revokeAPIKey: (...args: unknown[]) => mockRevokeAPIKey(...args),
  deleteAPIKey: (...args: unknown[]) => mockDeleteAPIKey(...args),
}));

const makeKey = (overrides: Partial<APIKey> = {}): APIKey => ({
  id: "key-1",
  name: "Test Key",
  key_prefix: "sk-test-abc",
  last_used_at: null,
  created_at: "2024-01-01T00:00:00Z",
  expires_at: null,
  revoked_at: null,
  status: "active",
  ...overrides,
});

const makeCreatedKey = (overrides: Partial<CreatedAPIKey> = {}): CreatedAPIKey => ({
  ...makeKey(overrides),
  key: "sk-test-abc-FULL-SECRET-KEY",
  ...overrides,
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ApiKeysPage />
    </QueryClientProvider>,
  );
}

describe("ApiKeysPage create button", () => {
  beforeEach(() => {
    mockListAPIKeys.mockResolvedValue([]);
  });

  afterEach(() => vi.clearAllMocks());

  it("shows the create button for a writer", async () => {
    renderPage();
    expect(await screen.findByText("สร้าง API Key")).toBeInTheDocument();
  });
});

describe("ApiKeysPage list rendering", () => {
  afterEach(() => vi.clearAllMocks());

  it("shows empty state when there are no keys", async () => {
    mockListAPIKeys.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("ยังไม่มี API Key กรุณาสร้างใหม่")).toBeInTheDocument();
  });

  it("renders key cards with name and prefix", async () => {
    mockListAPIKeys.mockResolvedValue([
      makeKey({ id: "k1", name: "Production Key", key_prefix: "sk-prod-123" }),
      makeKey({ id: "k2", name: "Dev Key", key_prefix: "sk-dev-456", status: "revoked" }),
    ]);
    renderPage();
    expect(await screen.findByText("Production Key")).toBeInTheDocument();
    expect(screen.getByText("Dev Key")).toBeInTheDocument();
    expect(screen.getByText("sk-prod-123…")).toBeInTheDocument();
    expect(screen.getByText("sk-dev-456…")).toBeInTheDocument();
  });

  it("hides revoke button for revoked keys", async () => {
    mockListAPIKeys.mockResolvedValue([
      makeKey({ id: "k1", name: "Dead Key", status: "revoked" }),
    ]);
    renderPage();
    await screen.findByText("Dead Key");
    expect(screen.queryByRole("button", { name: "เพิกถอน" })).not.toBeInTheDocument();
  });

});

describe("ApiKeysPage create flow", () => {
  afterEach(() => vi.clearAllMocks());

  it("opens create dialog when button is clicked", async () => {
    mockListAPIKeys.mockResolvedValue([]);
    renderPage();

    const btn = await screen.findByRole("button", { name: /สร้าง API Key/ });
    await userEvent.click(btn);

    expect(screen.getByText("สร้าง API Key ใหม่")).toBeInTheDocument();
    expect(screen.getByLabelText("ชื่อ")).toBeInTheDocument();
  });

  it("submit button is disabled when name is empty", async () => {
    mockListAPIKeys.mockResolvedValue([]);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /สร้าง API Key/ }));
    await screen.findByText("สร้าง API Key ใหม่");

    const submitBtn = screen.getByRole("button", { name: /^สร้าง$/ });
    expect(submitBtn).toBeDisabled();
  });

  it("calls createAPIKey with name on submit and shows reveal dialog", async () => {
    mockListAPIKeys.mockResolvedValue([]);
    const created = makeCreatedKey({ id: "new-1", name: "My New Key" });
    mockCreateAPIKey.mockResolvedValue(created);
    mockListAPIKeys.mockResolvedValueOnce([]).mockResolvedValue([makeKey({ id: "new-1", name: "My New Key" })]);

    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /สร้าง API Key/ }));
    await screen.findByText("สร้าง API Key ใหม่");

    await userEvent.type(screen.getByLabelText("ชื่อ"), "My New Key");
    await userEvent.click(screen.getByRole("button", { name: /^สร้าง$/ }));

    await waitFor(() => expect(mockCreateAPIKey).toHaveBeenCalledWith({ name: "My New Key" }));

    expect(await screen.findByText("สร้าง API Key เรียบร้อย")).toBeInTheDocument();
    expect(screen.getByText("sk-test-abc-FULL-SECRET-KEY")).toBeInTheDocument();
    expect(screen.getByText(/คัดลอก API Key นี้ไว้ทันที/)).toBeInTheDocument();
  });

  it("reveal dialog closes when รับทราบ is clicked", async () => {
    mockListAPIKeys.mockResolvedValue([]);
    mockCreateAPIKey.mockResolvedValue(makeCreatedKey({ name: "Temp" }));

    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /สร้าง API Key/ }));
    await screen.findByText("สร้าง API Key ใหม่");

    await userEvent.type(screen.getByLabelText("ชื่อ"), "Temp");
    await userEvent.click(screen.getByRole("button", { name: /^สร้าง$/ }));

    await screen.findByText("สร้าง API Key เรียบร้อย");
    await userEvent.click(screen.getByRole("button", { name: "รับทราบ" }));

    await waitFor(() =>
      expect(screen.queryByText("สร้าง API Key เรียบร้อย")).not.toBeInTheDocument(),
    );
  });
});

describe("ApiKeysPage edit flow", () => {
  afterEach(() => vi.clearAllMocks());

  it("opens edit dialog with pre-filled name when edit button is clicked", async () => {
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Original Name" })]);
    renderPage();

    await screen.findByText("Original Name");
    await userEvent.click(screen.getByRole("button", { name: "แก้ไข" }));

    expect(screen.getByText("แก้ไขชื่อ API Key")).toBeInTheDocument();
    const input = screen.getByLabelText("ชื่อ");
    expect((input as HTMLInputElement).value).toBe("Original Name");
  });

  it("calls updateAPIKey with the new name on save", async () => {
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Old Name" })]);
    mockUpdateAPIKey.mockResolvedValue(makeKey({ id: "k1", name: "New Name" }));

    renderPage();

    await screen.findByText("Old Name");
    await userEvent.click(screen.getByRole("button", { name: "แก้ไข" }));

    const input = screen.getByLabelText("ชื่อ");
    await userEvent.clear(input);
    await userEvent.type(input, "New Name");
    await userEvent.click(screen.getByRole("button", { name: /บันทึก/ }));

    await waitFor(() => expect(mockUpdateAPIKey).toHaveBeenCalledWith("k1", "New Name"));
    await waitFor(() => expect(screen.queryByText("แก้ไขชื่อ API Key")).not.toBeInTheDocument());
  });
});

describe("ApiKeysPage revoke flow", () => {
  beforeEach(() => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("calls revokeAPIKey after user confirms", async () => {
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Active Key" })]);
    mockRevokeAPIKey.mockResolvedValue(makeKey({ id: "k1", status: "revoked" }));

    renderPage();

    await screen.findByText("Active Key");
    await userEvent.click(screen.getByRole("button", { name: "เพิกถอน" }));

    await waitFor(() => expect(mockRevokeAPIKey).toHaveBeenCalledWith("k1"));
  });

  it("does not call revokeAPIKey when user cancels confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Active Key" })]);

    renderPage();

    await screen.findByText("Active Key");
    await userEvent.click(screen.getByRole("button", { name: "เพิกถอน" }));

    expect(mockRevokeAPIKey).not.toHaveBeenCalled();
  });
});

describe("ApiKeysPage delete flow", () => {
  afterEach(() => vi.clearAllMocks());

  it("opens delete confirm dialog when delete button is clicked", async () => {
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Key To Delete" })]);
    renderPage();

    await screen.findByText("Key To Delete");
    await userEvent.click(screen.getByRole("button", { name: "ลบ" }));

    expect(screen.getByText("ยืนยันการลบ")).toBeInTheDocument();
    expect(screen.getByText(/ลบ API Key "Key To Delete"/)).toBeInTheDocument();
  });

  it("shows confirm dialog with key name and a confirm button", async () => {
    // Characterization: verify the delete confirm UI is correct.
    // (The actual API call via Radix AlertDialogAction is covered separately.)
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Key To Delete" })]);

    renderPage();

    await screen.findByText("Key To Delete");
    await userEvent.click(screen.getByRole("button", { name: "ลบ" }));

    await screen.findByText("ยืนยันการลบ");
    expect(screen.getByText(/ลบ API Key "Key To Delete"/)).toBeInTheDocument();
    expect(screen.getByText(/ไม่สามารถย้อนกลับได้/)).toBeInTheDocument();

    const allBtns = screen.getAllByRole("button");
    const confirmBtn = allBtns.find(
      (b) => b.textContent?.trim() === "ลบ" && !b.hasAttribute("aria-label"),
    );
    expect(confirmBtn).toBeDefined();
    expect(confirmBtn).not.toBeDisabled();
  });

  it("dismisses delete dialog on cancel", async () => {
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Key To Delete" })]);
    renderPage();

    await screen.findByText("Key To Delete");
    await userEvent.click(screen.getByRole("button", { name: "ลบ" }));

    await screen.findByText("ยืนยันการลบ");
    await userEvent.click(screen.getByRole("button", { name: "ยกเลิก" }));

    await waitFor(() => expect(screen.queryByText("ยืนยันการลบ")).not.toBeInTheDocument());
    expect(mockDeleteAPIKey).not.toHaveBeenCalled();
  });

  it("calls deleteAPIKey with the correct id when confirm ลบ is clicked", async () => {
    mockListAPIKeys.mockResolvedValue([makeKey({ id: "k1", name: "Key To Delete" })]);
    mockDeleteAPIKey.mockResolvedValue({ detail: "deleted" });

    renderPage();

    await screen.findByText("Key To Delete");
    await userEvent.click(screen.getByRole("button", { name: "ลบ" }));

    await screen.findByText("ยืนยันการลบ");

    const allBtns = screen.getAllByRole("button");
    const confirmBtn = allBtns.find(
      (b) => b.textContent?.trim() === "ลบ" && !b.hasAttribute("aria-label"),
    );
    await userEvent.click(confirmBtn!);

    await waitFor(() => expect(mockDeleteAPIKey).toHaveBeenCalledWith("k1"));
    await waitFor(() => expect(screen.queryByText("ยืนยันการลบ")).not.toBeInTheDocument());
  });
});
