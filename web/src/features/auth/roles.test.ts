import { describe, expect, it } from "vitest";
import { ROUTE_ROLES, canAccess } from "./roles";

describe("canAccess", () => {
  it("lets a user reach chat, architecture, and history", () => {
    for (const path of ["/chat", "/architecture", "/history"]) {
      expect(canAccess("user", path)).toBe(true);
    }
  });

  it("keeps ops dashboards and settings away from a plain user", () => {
    for (const path of ["/dashboard", "/executive", "/health", "/heatmap", "/feedback", "/settings", "/settings/usage"]) {
      expect(canAccess("user", path)).toBe(false);
    }
  });

  it("gives staff the dashboards but not admin pages", () => {
    for (const path of ["/dashboard", "/executive", "/health", "/heatmap", "/feedback", "/settings/usage"]) {
      expect(canAccess("staff", path)).toBe(true);
    }
    expect(canAccess("staff", "/users")).toBe(false);
    expect(canAccess("staff", "/agencies")).toBe(false);
  });

  it("gives admin everything", () => {
    expect(canAccess("admin", "/users")).toBe(true);
    expect(canAccess("admin", "/dashboard")).toBe(true);
  });

  it("allows unknown paths through — routing owns those", () => {
    expect(canAccess("user", "/not-a-known-route")).toBe(true);
  });

  it("no longer routes to removed owner pages", () => {
    expect(ROUTE_ROLES["/my-agencies"]).toBeUndefined();
  });

  it("restricts the merged llm-settings page to admin", () => {
    expect(canAccess("user", "/llm-settings")).toBe(false);
    expect(canAccess("admin", "/llm-settings")).toBe(true);
  });
});
