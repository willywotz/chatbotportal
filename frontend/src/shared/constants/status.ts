/**
 * Centralised status-label and style maps.
 *
 * Agency lifecycle labels live in agencies/lifecycle.ts and are re-exported
 * here so consumers can import from a single shared location.
 */

export {
  STATUS_LABEL as AGENCY_STATUS_LABEL,
  STATUS_BADGE_CLASS as AGENCY_STATUS_BADGE_CLASS,
  TRANSITION_LABEL as AGENCY_TRANSITION_LABEL,
  HEALTH_LABEL as AGENCY_HEALTH_LABEL,
  HEALTH_DOT_CLASS as AGENCY_HEALTH_DOT_CLASS,
} from "@/features/agencies/lifecycle";

export type AgencyHealthStatus = "healthy" | "degraded" | "down";

export const HEALTH_STATUS_LABEL: Record<AgencyHealthStatus, string> = {
  healthy: "ปกติ",
  degraded: "ช้า",
  down: "ล่ม",
};

export const HEALTH_STATUS_COLOR: Record<AgencyHealthStatus, string> = {
  healthy: "hsl(142 70% 45%)",
  degraded: "hsl(35 90% 55%)",
  down: "hsl(0 70% 55%)",
};

export type PublicAgencyStatus = "active" | "maintenance" | "disabled";

export const PUBLIC_STATUS_LABEL: Record<string, string> = {
  active: "พร้อมใช้งาน",
  maintenance: "ปรับปรุงระบบ",
  disabled: "ปิดใช้งาน",
};

export const PUBLIC_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  active: "default",
  maintenance: "secondary",
  disabled: "destructive",
};

export type APIKeyStatus = "active" | "expired" | "revoked";

export const API_KEY_STATUS_META: Record<
  APIKeyStatus,
  { label: string; className: string }
> = {
  active: { label: "ใช้งานอยู่", className: "bg-green-100 text-green-700" },
  expired: { label: "หมดอายุ", className: "bg-amber-100 text-amber-700" },
  revoked: { label: "ถูกเพิกถอน", className: "bg-red-100 text-red-700" },
};
