import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExecutiveWeeklyBrief } from "./ExecutiveWeeklyBrief";

describe("ExecutiveWeeklyBrief", () => {
  it("hides the regenerate button for non-admins", () => {
    render(<ExecutiveWeeklyBrief weeklyBrief="brief" canRegenerate={false} />);
    expect(screen.queryByRole("button", { name: /สร้างใหม่/ })).not.toBeInTheDocument();
  });

  it("shows the regenerate button for admins", () => {
    render(<ExecutiveWeeklyBrief weeklyBrief="brief" canRegenerate={true} />);
    expect(screen.getByRole("button", { name: /สร้างใหม่/ })).toBeInTheDocument();
  });
});
