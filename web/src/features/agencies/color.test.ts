import { describe, expect, it } from "vitest";

import { DEFAULT_HEX_COLOR, hslToHex, toHexColor } from "./color";

describe("hslToHex", () => {
  it("converts pure red", () => {
    expect(hslToHex("hsl(0 100% 50%)")).toBe("#ff0000");
  });

  it("converts pure green", () => {
    expect(hslToHex("hsl(120 100% 50%)")).toBe("#00ff00");
  });

  it("converts pure blue", () => {
    expect(hslToHex("hsl(240 100% 50%)")).toBe("#0000ff");
  });

  it("falls back to the default for an unparsable string", () => {
    expect(hslToHex("not-a-color")).toBe(DEFAULT_HEX_COLOR);
  });
});

describe("toHexColor", () => {
  it("passes an already-hex value through, lowercased", () => {
    expect(toHexColor("#ABCDEF")).toBe("#abcdef");
  });

  it("converts an hsl() string", () => {
    expect(toHexColor("hsl(0 100% 50%)")).toBe("#ff0000");
  });

  it("falls back to the default for an empty/invalid value", () => {
    expect(toHexColor("")).toBe(DEFAULT_HEX_COLOR);
    expect(toHexColor("garbage")).toBe(DEFAULT_HEX_COLOR);
    expect(toHexColor(undefined)).toBe(DEFAULT_HEX_COLOR);
  });
});
