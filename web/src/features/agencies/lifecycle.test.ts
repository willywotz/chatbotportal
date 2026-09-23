import { describe, expect, it } from "vitest";

import { isLegalTransition, legalTransitions, STATUS_LABEL } from "./lifecycle";

describe("legalTransitions", () => {
  it("draft can activate or be disabled", () => {
    expect(legalTransitions("draft")).toEqual(["active", "disabled"]);
  });
  it("active can go to maintenance or disabled", () => {
    expect(legalTransitions("active")).toEqual(["maintenance", "disabled"]);
  });
  it("maintenance can go back to active or be disabled", () => {
    expect(legalTransitions("maintenance")).toEqual(["active", "disabled"]);
  });
  it("disabled can only be re-activated", () => {
    expect(legalTransitions("disabled")).toEqual(["active"]);
  });
});

describe("isLegalTransition", () => {
  it("accepts legal and rejects illegal transitions", () => {
    expect(isLegalTransition("draft", "active")).toBe(true);
    expect(isLegalTransition("disabled", "maintenance")).toBe(false);
    expect(isLegalTransition("active", "draft")).toBe(false);
  });
});

describe("STATUS_LABEL", () => {
  it("has a label for every status", () => {
    expect(STATUS_LABEL.draft).toBeTruthy();
    expect(STATUS_LABEL.active).toBeTruthy();
    expect(STATUS_LABEL.maintenance).toBeTruthy();
    expect(STATUS_LABEL.disabled).toBeTruthy();
  });
});
