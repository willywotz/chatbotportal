import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import UsersPage from "./UsersPage";
import { listUsers, deleteUser, type ManagedUser } from "./userApi";

const staffUser: ManagedUser = {
  id: "1",
  email: "staff@test.com",
  displayName: "Staff",
  role: "staff",
  avatarUrl: null,
  isActive: true,
  createdAt: "2026-01-01T00:00:00Z",
};

vi.mock("./userApi", () => ({
  listUsers: vi.fn(() => Promise.resolve([])),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  deactivateUser: vi.fn(),
  activateUser: vi.fn(),
  deleteUser: vi.fn(() => Promise.resolve()),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UsersPage />
    </QueryClientProvider>,
  );
}

describe("UsersPage create control", () => {
  it("shows the add-user button for a writer (admin)", async () => {
    renderPage();
    expect(await screen.findByText("เพิ่มผู้ใช้")).toBeInTheDocument();
  });

  it("renders the role filter defaulting to all roles", async () => {
    renderPage();
    expect(await screen.findByText("บทบาททั้งหมด")).toBeInTheDocument();
  });

  it("shows the staff role label on a staff row", async () => {
    vi.mocked(listUsers).mockResolvedValueOnce([staffUser]);
    renderPage();
    expect(await screen.findByText("เจ้าหน้าที่")).toBeInTheDocument();
  });
});

describe("UsersPage delete control", () => {
  it("deletes a user after confirming", async () => {
    vi.mocked(listUsers).mockResolvedValueOnce([staffUser]);
    renderPage();
    await screen.findByText("staff@test.com");
    await userEvent.click(screen.getByRole("button", { name: "ลบ" }));
    await userEvent.click(await screen.findByRole("button", { name: "ลบผู้ใช้" }));
    expect(deleteUser).toHaveBeenCalledWith("1");
  });
});
