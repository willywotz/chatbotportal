import { describe, expect, it } from "vitest";
import { agencySchema } from "./agencySchema";

const VALID_PAYLOAD = {
  name: "กรมสรรพากร",
  shortName: "สร.",
  endpointUrl: "https://api.rd.go.th/v1/chat",
  connectionType: "API" as const,
  apiHeaders: [{ name: "X-Source", value: "portal" }],
};

describe("agencySchema — valid payload", () => {
  it("accepts a well-formed payload", () => {
    const result = agencySchema.safeParse(VALID_PAYLOAD);
    expect(result.success).toBe(true);
  });

  it("accepts payload with no headers", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD, apiHeaders: [] });
    expect(result.success).toBe(true);
  });

  it("accepts optional numeric fields when provided as positive integers", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      priority: 2,
      dispatchTimeoutS: 30,
    });
    expect(result.success).toBe(true);
  });

  it("accepts MCP connection type with mcpToolName", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      connectionType: "MCP",
      mcpToolName: "chat_with_agency",
    });
    expect(result.success).toBe(true);
  });
});

describe("agencySchema — name validation", () => {
  it("rejects empty name", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD, name: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const nameErr = result.error.issues.find((i) => i.path[0] === "name");
      expect(nameErr).toBeDefined();
    }
  });

  it("rejects whitespace-only name", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD, name: "   " });
    expect(result.success).toBe(false);
  });
});

describe("agencySchema — endpointUrl validation", () => {
  it("rejects empty endpointUrl", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD, endpointUrl: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const urlErr = result.error.issues.find((i) => i.path[0] === "endpointUrl");
      expect(urlErr).toBeDefined();
    }
  });

  it("rejects malformed URL (no scheme)", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD, endpointUrl: "not-a-url" });
    expect(result.success).toBe(false);
  });

  it("rejects URL missing host (bare slash)", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD, endpointUrl: "https://" });
    expect(result.success).toBe(false);
  });

  it("accepts valid https URL", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      endpointUrl: "https://customs.example/api/chat",
    });
    expect(result.success).toBe(true);
  });

  it("accepts valid http URL (non-prod dev endpoints)", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      endpointUrl: "http://localhost:8080/api",
    });
    expect(result.success).toBe(true);
  });
});

describe("agencySchema — apiHeaders validation", () => {
  it("rejects header with empty name", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      apiHeaders: [{ name: "", value: "some-value" }],
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const headerErr = result.error.issues.find(
        (i) => i.path[0] === "apiHeaders" && i.path[2] === "name",
      );
      expect(headerErr).toBeDefined();
    }
  });

  it("rejects header with empty value", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      apiHeaders: [{ name: "X-Source", value: "" }],
    });
    expect(result.success).toBe(false);
  });

  it("rejects header with whitespace-only name", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      apiHeaders: [{ name: "   ", value: "v" }],
    });
    expect(result.success).toBe(false);
  });

  it("accepts multiple valid headers", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      apiHeaders: [
        { name: "X-Source", value: "portal" },
        { name: "Authorization", value: "Bearer token123" },
      ],
    });
    expect(result.success).toBe(true);
  });
});

describe("agencySchema — numeric field coercion", () => {
  it("accepts omitted optional numerics (undefined → omitted)", () => {
    const result = agencySchema.safeParse({ ...VALID_PAYLOAD });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.priority).toBeUndefined();
      expect(result.data.dispatchTimeoutS).toBeUndefined();
    }
  });

  it("accepts empty string for optional numerics (treated as omitted)", () => {
    const result = agencySchema.safeParse({
      ...VALID_PAYLOAD,
      priority: "",
      dispatchTimeoutS: "",
    });
    expect(result.success).toBe(true);
  });
});
