import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { resetMockData } from "@/mocks/fixtures";

import {
  useAgencies,
  useDiscoverMcpTools,
  useHealthHistory,
  useUpdateAgencyStatus,
} from "./useAgencies";

afterEach(() => {
  resetMockData();
});

const ACTIVE_ID = "11111111-1111-1111-1111-111111111111";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useAgencies", () => {
  it("returns mapped agencies with health", async () => {
    const { result } = renderHook(() => useAgencies(), { wrapper });
    await waitFor(() => expect(result.current.data?.length).toBeGreaterThan(0));
    const active = result.current.data!.find((a) => a.id === ACTIVE_ID)!;
    expect(active.health.state).toBe("up");
    expect(active.routerHint).toContain("ภาษี");
  });
});

describe("useHealthHistory", () => {
  it("fetches camelCase buckets for a window", async () => {
    const { result } = renderHook(() => useHealthHistory(ACTIVE_ID, "24h"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data!.length).toBe(24);
    expect(result.current.data![0].uptimePct).toBeTypeOf("number");
    expect(result.current.data![0].bucketStart).toBeTypeOf("string");
  });

  it("does not fetch without an id", () => {
    const { result } = renderHook(() => useHealthHistory(undefined, "24h"), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useUpdateAgencyStatus", () => {
  it("applies a legal transition", async () => {
    const { result } = renderHook(() => useUpdateAgencyStatus(), { wrapper });
    const updated = await result.current.mutateAsync({ id: ACTIVE_ID, status: "maintenance" });
    expect(updated.status).toBe("maintenance");
  });

  it("surfaces the 422 detail on an illegal transition", async () => {
    const { result } = renderHook(() => useUpdateAgencyStatus(), { wrapper });
    await expect(
      result.current.mutateAsync({ id: ACTIVE_ID, status: "draft" }),
    ).rejects.toThrow(/transition/i);
  });
});

describe("useDiscoverMcpTools", () => {
  it("returns mapped tools", async () => {
    const { result } = renderHook(() => useDiscoverMcpTools(), { wrapper });
    const tools = await result.current.mutateAsync({ endpointUrl: "https://mcp.example/sse" });
    expect(tools[0].name).toBe("chat_with_fda");
    expect(tools[0].inputSchema).toBeDefined();
  });
});
