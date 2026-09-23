import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { TextScaleProvider, useTextScale } from "./useTextScale";

function wrapper({ children }: { children: ReactNode }) {
  return <TextScaleProvider>{children}</TextScaleProvider>;
}

afterEach(() => window.localStorage.clear());

describe("useTextScale", () => {
  it("defaults to normal scale with a factor of 1", () => {
    const { result } = renderHook(() => useTextScale(), { wrapper });
    expect(result.current.scale).toBe("normal");
    expect(result.current.factor).toBe(1);
  });

  it("persists the chosen scale to localStorage", () => {
    const { result } = renderHook(() => useTextScale(), { wrapper });
    act(() => result.current.setScale("large"));
    expect(result.current.scale).toBe("large");
    expect(result.current.factor).toBeGreaterThan(1);
    expect(window.localStorage.getItem("chat-text-scale")).toBe("large");
  });

  it("reads the initial scale from localStorage", () => {
    window.localStorage.setItem("chat-text-scale", "small");
    const { result } = renderHook(() => useTextScale(), { wrapper });
    expect(result.current.scale).toBe("small");
    expect(result.current.factor).toBeLessThan(1);
  });
});
