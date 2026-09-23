import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { UserFormDialog } from "./UserFormDialog";
import { ROLE_LABEL } from "./roleLabels";

vi.mock("./userApi", () => ({
  createUser: vi.fn(),
  updateUser: vi.fn(),
}));

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UserFormDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

describe("UserFormDialog role select", () => {
  it("offers every assignable role, including staff", async () => {
    renderDialog();
    await userEvent.click(screen.getByRole("combobox"));
    for (const label of Object.values(ROLE_LABEL)) {
      expect(await screen.findByRole("option", { name: label })).toBeInTheDocument();
    }
  });
});
