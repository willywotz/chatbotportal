import { z } from "zod";

const apiHeaderSchema = z.object({
  name: z.string().min(1, "Header name is required").refine((v) => v.trim().length > 0, {
    message: "Header name cannot be blank",
  }),
  value: z.string().min(1, "Header value is required"),
});

// Coerce empty string to undefined so optional numerics can be omitted.
const positiveIntOptional = z
  .union([z.string(), z.number()])
  .optional()
  .transform((v) => {
    if (v === "" || v === undefined || v === null) return undefined;
    const n = Number(v);
    return Number.isNaN(n) ? undefined : n;
  })
  .pipe(z.number().int().positive().optional());

export const agencySchema = z.object({
  name: z
    .string()
    .min(1, "Agency name is required")
    .refine((v) => v.trim().length > 0, { message: "Agency name cannot be blank" }),
  shortName: z.string().optional(),
  connectionType: z.enum(["API", "MCP", "A2A"]).optional(),
  endpointUrl: z.string().url("Endpoint URL must be a valid URL"),
  apiHeaders: z.array(apiHeaderSchema).optional(),
  // Optional numeric fields — accept string or number, coerce.
  priority: positiveIntOptional,
  dispatchTimeoutS: positiveIntOptional,
  // MCP-specific
  mcpToolName: z.string().optional(),
});

export type AgencySchemaInput = z.input<typeof agencySchema>;
export type AgencySchemaOutput = z.output<typeof agencySchema>;
