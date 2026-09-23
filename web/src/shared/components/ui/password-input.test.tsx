import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PasswordInput } from "./password-input";

describe("PasswordInput", () => {
  it("starts masked and toggles to plain text and back", () => {
    render(<PasswordInput aria-label="pw" defaultValue="secret" />);
    const input = screen.getByLabelText("pw") as HTMLInputElement;
    expect(input.type).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "แสดงรหัสผ่าน" }));
    expect(input.type).toBe("text");

    fireEvent.click(screen.getByRole("button", { name: "ซ่อนรหัสผ่าน" }));
    expect(input.type).toBe("password");
  });

  it("does not submit the surrounding form when toggled", () => {
    let submitted = false;
    render(
      <form onSubmit={() => { submitted = true; }}>
        <PasswordInput aria-label="pw" />
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "แสดงรหัสผ่าน" }));
    expect(submitted).toBe(false);
  });
});
