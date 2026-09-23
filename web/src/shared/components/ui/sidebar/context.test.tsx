import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import * as React from "react";

import { SidebarProvider } from "./context";
import { useSidebar } from "./use-sidebar";

describe("useSidebar", () => {
  it("throws when called outside SidebarProvider", () => {
    expect(() => {
      renderHook(() => useSidebar());
    }).toThrow("useSidebar must be used within a SidebarProvider.");
  });

  it("defaults to open=true and state=expanded inside provider", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <SidebarProvider>{children}</SidebarProvider>
    );

    const { result } = renderHook(() => useSidebar(), { wrapper });

    expect(result.current.open).toBe(true);
    expect(result.current.state).toBe("expanded");
    expect(result.current.isMobile).toBe(false);
  });

  it("respects defaultOpen=false", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <SidebarProvider defaultOpen={false}>{children}</SidebarProvider>
    );

    const { result } = renderHook(() => useSidebar(), { wrapper });

    expect(result.current.open).toBe(false);
    expect(result.current.state).toBe("collapsed");
  });

  it("toggleSidebar flips open state", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <SidebarProvider defaultOpen={true}>{children}</SidebarProvider>
    );

    const { result } = renderHook(() => useSidebar(), { wrapper });

    expect(result.current.open).toBe(true);

    act(() => {
      result.current.toggleSidebar();
    });

    expect(result.current.open).toBe(false);
    expect(result.current.state).toBe("collapsed");

    act(() => {
      result.current.toggleSidebar();
    });

    expect(result.current.open).toBe(true);
    expect(result.current.state).toBe("expanded");
  });

  it("setOpen directly sets open state", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <SidebarProvider defaultOpen={true}>{children}</SidebarProvider>
    );

    const { result } = renderHook(() => useSidebar(), { wrapper });

    act(() => {
      result.current.setOpen(false);
    });

    expect(result.current.open).toBe(false);

    act(() => {
      result.current.setOpen(true);
    });

    expect(result.current.open).toBe(true);
  });
});
