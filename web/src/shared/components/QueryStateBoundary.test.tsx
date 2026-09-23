import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryStateBoundary } from "./QueryStateBoundary";

describe("QueryStateBoundary", () => {
  it("renders children when data is available", () => {
    render(
      <QueryStateBoundary isLoading={false} isError={false} hasData onRetry={vi.fn()}>
        <span>content</span>
      </QueryStateBoundary>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("renders loading skeleton when isLoading is true", () => {
    render(
      <QueryStateBoundary isLoading isError={false} hasData={false} onRetry={vi.fn()}>
        <span>content</span>
      </QueryStateBoundary>,
    );
    expect(screen.queryByText("content")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ลองอีกครั้ง/ })).not.toBeInTheDocument();
  });

  it("shows retry on error and calls onRetry", () => {
    const onRetry = vi.fn();
    render(
      <QueryStateBoundary isLoading={false} isError hasData={false} onRetry={onRetry}>
        x
      </QueryStateBoundary>,
    );
    fireEvent.click(screen.getByRole("button", { name: /ลองอีกครั้ง/ }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows error card with role=alert when isError is true", () => {
    render(
      <QueryStateBoundary isLoading={false} isError hasData={false} onRetry={vi.fn()}>
        x
      </QueryStateBoundary>,
    );
    expect(screen.queryByText("x")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("ไม่สามารถโหลดข้อมูลได้")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ลองอีกครั้ง/ })).toBeInTheDocument();
  });

  it("shows distinct empty state (not error) when success but no data", () => {
    render(
      <QueryStateBoundary isLoading={false} isError={false} hasData={false}>
        x
      </QueryStateBoundary>,
    );
    expect(screen.queryByText("x")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("ไม่สามารถโหลดข้อมูลได้")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ลองอีกครั้ง/ })).not.toBeInTheDocument();
    expect(screen.getByText("ไม่พบข้อมูล")).toBeInTheDocument();
  });

  it("renders custom emptyMessage when provided", () => {
    render(
      <QueryStateBoundary
        isLoading={false}
        isError={false}
        hasData={false}
        emptyMessage="ยังไม่มีข้อมูลสุขภาพ"
      >
        x
      </QueryStateBoundary>,
    );
    expect(screen.getByText("ยังไม่มีข้อมูลสุขภาพ")).toBeInTheDocument();
  });
});
