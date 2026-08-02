import { describe, expect, it } from "vitest";

import { getPaginationRange } from "@/shared/lib/pagination";

describe("getPaginationRange", () => {
  it("lists every page when the total is small", () => {
    expect(getPaginationRange(1, 1)).toEqual([1]);
    expect(getPaginationRange(2, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(getPaginationRange(4, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("caps the number of rendered items with ellipsis for large totals", () => {
    const range = getPaginationRange(1, 34);
    expect(range.filter((p) => typeof p === "number").length).toBeLessThanOrEqual(7);
    expect(range).toContain(1);
    expect(range).toContain(34);
    expect(range).toContain("ellipsis");
  });

  it("keeps the current page and its neighbors in the middle", () => {
    expect(getPaginationRange(17, 34)).toEqual([1, "ellipsis", 16, 17, 18, "ellipsis", 34]);
  });

  it("expands the start window without a leading ellipsis near the first page", () => {
    expect(getPaginationRange(2, 34)).toEqual([1, 2, 3, "ellipsis", 34]);
  });

  it("expands the end window without a trailing ellipsis near the last page", () => {
    expect(getPaginationRange(33, 34)).toEqual([1, "ellipsis", 32, 33, 34]);
  });
});
