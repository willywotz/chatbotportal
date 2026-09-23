import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgencyLogo } from "./AgencyLogo";

describe("AgencyLogo", () => {
  it("renders an <img> for an uploaded backend logo path", () => {
    render(<AgencyLogo logo="/api/v1/public/agencies/1/logo?v=abcd1234" alt="กรมสรรพากร" />);
    const img = screen.getByRole("img", { name: "กรมสรรพากร" });
    expect(img).toHaveAttribute("src", "/api/v1/public/agencies/1/logo?v=abcd1234");
  });

  it("renders an <img> for an absolute http(s) URL", () => {
    render(<AgencyLogo logo="https://cdn.example/logo.png" alt="test" />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("renders an <img> for a data URI", () => {
    render(<AgencyLogo logo="data:image/png;base64,abc" alt="test" />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("renders emoji text for a non-image logo", () => {
    render(<AgencyLogo logo="🏛️" alt="กรมสรรพากร" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("🏛️")).toBeInTheDocument();
  });

  it("renders nothing for an empty logo", () => {
    const { container } = render(<AgencyLogo logo="" alt="test" />);
    expect(container).toBeEmptyDOMElement();
  });
});
