import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionTestResult } from "./ConnectionTestResult";

describe("ConnectionTestResult", () => {
  it("omits the placeholder version from the success title", () => {
    render(<ConnectionTestResult loading={false} result={{ success: true, protocol: "REST API", version: "-" }} />);
    expect(screen.getByText("เชื่อมต่อสำเร็จ — REST API")).toBeInTheDocument();
  });

  it("renders a non-2xx status as a reachable success", () => {
    render(
      <ConnectionTestResult
        loading={false}
        result={{
          success: true,
          protocol: "REST API",
          version: "-",
          latency: "42ms",
          status_code: 405,
          status_text: "Method Not Allowed",
          steps: [{ step: 1, label: "TCP Connection", status: "done", timeMs: 42 }],
        }}
      />,
    );
    expect(screen.getByText("HTTP 405")).toBeInTheDocument();
    expect(screen.getByText("TCP Connection")).toBeInTheDocument();
  });
});
