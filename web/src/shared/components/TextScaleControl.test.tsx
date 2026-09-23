import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { TextScaleProvider } from "@/shared/hooks/useTextScale";
import { TextScaleControl } from "./TextScaleControl";

function renderControl() {
  return render(
    <TextScaleProvider>
      <TextScaleControl />
    </TextScaleProvider>,
  );
}

afterEach(() => window.localStorage.clear());

describe("TextScaleControl", () => {
  it("renders small, normal and large options", () => {
    renderControl();
    expect(screen.getByRole("button", { name: /เล็ก/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ปกติ/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ใหญ่/ })).toBeInTheDocument();
  });

  it("marks the active scale as pressed", () => {
    renderControl();
    expect(screen.getByRole("button", { name: /ปกติ/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("selects and persists a new scale on click", async () => {
    const user = userEvent.setup();
    renderControl();
    await user.click(screen.getByRole("button", { name: /ใหญ่/ }));
    expect(screen.getByRole("button", { name: /ใหญ่/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(window.localStorage.getItem("chat-text-scale")).toBe("large");
  });
});
