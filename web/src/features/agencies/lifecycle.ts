import type { AgencyLifecycleStatus, HealthState } from "@/shared/types/agency";

export const LEGAL_TRANSITIONS: Record<AgencyLifecycleStatus, AgencyLifecycleStatus[]> = {
  draft: ["active", "disabled"],
  active: ["maintenance", "disabled"],
  maintenance: ["active", "disabled"],
  disabled: ["active"],
};

export function legalTransitions(from: AgencyLifecycleStatus): AgencyLifecycleStatus[] {
  return LEGAL_TRANSITIONS[from];
}

export function isLegalTransition(
  from: AgencyLifecycleStatus,
  to: AgencyLifecycleStatus,
): boolean {
  return LEGAL_TRANSITIONS[from].includes(to);
}

export const STATUS_LABEL: Record<AgencyLifecycleStatus, string> = {
  draft: "Draft",
  active: "Active",
  maintenance: "ปิดปรับปรุง",
  disabled: "Disabled",
};

export const STATUS_BADGE_CLASS: Record<AgencyLifecycleStatus, string> = {
  draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  active: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  maintenance: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  disabled: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export const TRANSITION_LABEL: Record<AgencyLifecycleStatus, string> = {
  draft: "กลับเป็น Draft",
  active: "เปิดใช้งาน",
  maintenance: "ปิดปรับปรุง",
  disabled: "ปิดการใช้งาน",
};

export const HEALTH_DOT_CLASS: Record<HealthState, string> = {
  up: "bg-green-500",
  degraded: "bg-amber-500",
  down: "bg-red-500",
  unknown: "bg-gray-300",
};

export const HEALTH_LABEL: Record<HealthState, string> = {
  up: "ปกติ",
  degraded: "เสื่อมประสิทธิภาพ",
  down: "ล่ม",
  unknown: "ยังไม่มีข้อมูล",
};
