import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/server";
import PublicPortal from "./PublicPortal";

const { resetMock, signInMock } = vi.hoisted(() => ({ resetMock: vi.fn(), signInMock: vi.fn() }));

// Stub the auth adapter: signIn is asserted; the SPA stays anonymous here.
vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ user: null, isAdmin: false, isLoading: false, signIn: signInMock, signOut: vi.fn() }),
}));

vi.mock("@/features/chat/useChat", () => ({
  useChat: () => ({
    messages: [],
    input: "",
    setInput: vi.fn(),
    isTyping: false,
    activeStepCount: 0,
    currentSteps: [],
    streamingState: { pipelineSteps: [], done: false },
    scrollRef: { current: null },
    handleSend: vi.fn(),
    handleRate: vi.fn(),
    reset: resetMock,
    cancelStream: vi.fn(),
    hasMessages: false,
  }),
}));

function renderPortal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PublicPortal />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => server.resetHandlers());

describe("PublicPortal popular questions", () => {
  it("renders fetched popular questions", async () => {
    renderPortal();
    expect(await screen.findByText("คำถามยอดนิยม")).toBeInTheDocument();
    expect(await screen.findByText("สอบถามเรื่องการลดหย่อนภาษี 2568")).toBeInTheDocument();
  });

  it("renders nothing when the endpoint returns an empty list", async () => {
    server.use(
      http.get("*/api/v1/public/popular-questions", () => HttpResponse.json({ questions: [] })),
    );
    renderPortal();
    await waitFor(() => expect(screen.queryByText("คำถามยอดนิยม")).not.toBeInTheDocument());
  });
});

describe("PublicPortal login button", () => {
  it("redirects to the OIDC provider when an anon user clicks login", async () => {
    signInMock.mockClear();
    renderPortal();
    const button = await screen.findByRole("button", { name: /เข้าสู่ระบบ/ });
    await userEvent.click(button);
    expect(signInMock).toHaveBeenCalledTimes(1);
  });
});

describe("PublicPortal connected agencies", () => {
  it("renders the connected-agencies section from the public endpoint", async () => {
    renderPortal();
    expect(await screen.findByText("หน่วยงานที่เชื่อมต่อ")).toBeInTheDocument();
    expect(await screen.findByText("อย.")).toBeInTheDocument();
  });

  it("hides the section when no agencies are returned", async () => {
    server.use(http.get("*/api/v1/public/agencies", () => HttpResponse.json([])));
    renderPortal();
    await waitFor(() =>
      expect(screen.queryByText("หน่วยงานที่เชื่อมต่อ")).not.toBeInTheDocument(),
    );
  });

  it("shows the connected-agencies sidebar in chat mode", async () => {
    const user = userEvent.setup();
    renderPortal();
    await user.type(
      await screen.findByPlaceholderText(/พิมพ์คำถามของคุณ/),
      "test",
    );
    await user.keyboard("{Enter}");
    expect(await screen.findByText("หน่วยงานที่เชื่อมต่อ")).toBeInTheDocument();
    expect(await screen.findByText("อย.")).toBeInTheDocument();

    // "แชทใหม่" starts a fresh chat via reset instead of navigating to /chat.
    const newChat = screen.getByRole("button", { name: /แชทใหม่/ });
    resetMock.mockClear();
    await user.click(newChat);
    expect(resetMock).toHaveBeenCalledTimes(1);
  });
});
