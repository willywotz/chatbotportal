import { describe, expect, it } from "vitest";
import { ROLE_LABEL, ROLE_ORDER } from "./roleLabels";

describe("role labels", () => {
  it("labels all three roles in Thai", () => {
    expect(ROLE_LABEL.user).toBe("ผู้ใช้");
    expect(ROLE_LABEL.staff).toBe("เจ้าหน้าที่");
    expect(ROLE_LABEL.admin).toBe("ผู้ดูแลระบบ");
  });

  it("orders roles least- to most-privileged", () => {
    expect(ROLE_ORDER).toEqual(["user", "staff", "admin"]);
  });
});
