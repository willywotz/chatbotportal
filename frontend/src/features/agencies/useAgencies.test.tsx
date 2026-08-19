import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetMockData } from "@/mocks/fixtures";
import { keycloak } from "@/shared/lib/keycloak";

import {
  useAgencies,
  useDiscoverMcpTools,
  useHealthHistory,
  useUpdateAgencyStatus,
  useUploadAgencyLogo,
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

describe("useUploadAgencyLogo", () => {
  afterEach(() => {
    keycloak.authenticated = false;
    keycloak.token = undefined;
  });

  it("sends the logo upload with no credentials and no Authorization header when unauthenticated", async () => {
    const agency = { id: ACTIVE_ID, name: "n", logo: "l" };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(agency), { status: 200 }),
    );
    const { result } = renderHook(() => useUploadAgencyLogo(), { wrapper });
    const file = new File(["x"], "logo.png", { type: "image/png" });

    await result.current.mutateAsync({ id: ACTIVE_ID, file });

    const [, options] = fetchSpy.mock.calls[0];
    expect(options?.credentials).toBeUndefined();
    expect((options?.headers as Record<string, string> | undefined)?.Authorization).toBeUndefined();

    fetchSpy.mockRestore();
  });

  it("attaches the Keycloak bearer token when authenticated", async () => {
    keycloak.authenticated = true;
    keycloak.token = "tok123";
    const agency = { id: ACTIVE_ID, name: "n", logo: "l" };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(agency), { status: 200 }),
    );
    const { result } = renderHook(() => useUploadAgencyLogo(), { wrapper });
    const file = new File(["x"], "logo.png", { type: "image/png" });

    await result.current.mutateAsync({ id: ACTIVE_ID, file });

    const [, options] = fetchSpy.mock.calls[0];
    expect((options?.headers as Record<string, string> | undefined)?.Authorization).toBe(
      "Bearer tok123",
    );

    fetchSpy.mockRestore();
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
