import { useState } from 'react';
import {
  Brain, Check, ChevronDown, ChevronUp, GitBranch, Loader2, Quote, Search, Send,
  ShieldCheck, Sparkles, X, type LucideIcon,
} from 'lucide-react';
import { Badge } from '@/shared/components/ui/badge';
import { cn } from '@/shared/lib/utils';
import type { AgentStepsSnapshot } from '@/shared/types/chat';

const STEP_META: Record<string, { icon: LucideIcon; label: string; description: string }> = {
  discover: { icon: Search, label: 'ค้นหาหน่วยงาน', description: 'ค้นหารายชื่อหน่วยงานที่ให้บริการ' },
  classify: { icon: Brain, label: 'วิเคราะห์คำถาม', description: 'วิเคราะห์เจตนาและแยกเป็นคำถามย่อย' },
  routing: { icon: GitBranch, label: 'เลือกหน่วยงาน', description: 'เลือกหน่วยงานที่เกี่ยวข้องกับคำถาม' },
  invoke: { icon: Send, label: 'สืบค้นจากหน่วยงาน', description: 'ส่งคำถามไปยังหน่วยงานพร้อมกันแบบขนาน' },
  verify: { icon: ShieldCheck, label: 'ตรวจสอบความเกี่ยวข้อง', description: 'ให้คะแนนว่าคำตอบตรงประเด็นหรือไม่' },
  summarize: { icon: Quote, label: 'สรุปภาพรวม', description: 'สรุปคำตอบภาพรวมพร้อมเลขอ้างอิง' },
  synthesize: { icon: Sparkles, label: 'สังเคราะห์คำตอบ', description: 'รวมคำตอบที่ผ่านการตรวจสอบเป็นคำตอบสุดท้าย' },
};

const AGENCY_STYLE: Record<string, { icon: string; className: string }> = {
  passed: { icon: '✅', className: 'text-emerald-700 dark:text-emerald-400' },
  rejected: { icon: '⚠️', className: 'text-amber-700 dark:text-amber-400' },
  error: { icon: '❌', className: 'text-red-700 dark:text-red-400' },
  ok: { icon: '⏳', className: 'text-muted-foreground' },
  running: { icon: '🔗', className: 'text-muted-foreground' },
  pending: { icon: '🔗', className: 'text-muted-foreground' },
};

/**
 * Persisted pipeline snapshot, rendered as a collapsible card (collapsed by
 * default). The expanded body mirrors the OneChat debug console's FlowPanel:
 * a summary-chip row, a vertical step timeline with icon nodes, and the
 * per-agency verdicts below it. Terminal state only — no live/running spinner.
 */
export function AgentStepsCard({
  steps,
  defaultOpen = false,
  loading = false,
}: {
  steps: AgentStepsSnapshot | null;
  defaultOpen?: boolean;
  loading?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!steps) return null;

  const passed = steps.agencies.filter((a) => a.status === 'passed').length;
  const rejected = steps.agencies.filter((a) => a.status === 'rejected').length;
  const errored = steps.agencies.filter((a) => a.status === 'error').length + steps.errors.length;

  return (
    <div className="rounded-lg border border-border bg-muted/40 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-[0.75em] text-muted-foreground hover:text-foreground transition-colors"
      >
        <Sparkles className="h-3.5 w-3.5 shrink-0" />
        <span className="font-medium">กระบวนการทำงานของ AI Agent</span>
        {open ? <ChevronUp className="ml-auto h-3.5 w-3.5" /> : <ChevronDown className="ml-auto h-3.5 w-3.5" />}
      </button>

      {open && (
        <div className="border-t border-border px-3 pb-3 pt-2">
          {(passed > 0 || rejected > 0 || errored > 0) && (
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              {passed > 0 && (
                <Badge variant="outline" className="gap-1 border-emerald-300 text-[0.75em] text-emerald-700 dark:text-emerald-400">
                  <Check className="h-3 w-3" />ผ่าน {passed}
                </Badge>
              )}
              {rejected > 0 && (
                <Badge variant="outline" className="gap-1 border-amber-300 text-[0.75em] text-amber-700 dark:text-amber-400">
                  <X className="h-3 w-3" />ไม่ผ่าน {rejected}
                </Badge>
              )}
              {errored > 0 && (
                <Badge variant="outline" className="border-red-300 text-[0.75em] text-red-700 dark:text-red-400">
                  error {errored}
                </Badge>
              )}
            </div>
          )}

          <div>
            {steps.steps.map((s, i) => {
              const meta = STEP_META[s.name] ?? { icon: Sparkles, label: s.name, description: '' };
              const Icon = meta.icon;
              const isLast = i === steps.steps.length - 1 && !loading;
              return (
                <div key={`${s.name}-${i}`} className="flex gap-2.5">
                  <div className="flex flex-col items-center">
                    <div className="flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-emerald-400 bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40">
                      <Icon className="size-3" />
                    </div>
                    {!isLast && <div className="my-1 w-0.5 flex-1 rounded-full bg-emerald-300/60" />}
                  </div>
                  <div className={cn('min-w-0 flex-1', !isLast && 'pb-2')}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[0.75em] font-medium text-foreground">{meta.label}</span>
                      {s.ms != null && (
                        <Badge variant="secondary" className="h-4 px-1.5 text-[0.625em] font-normal text-emerald-700 dark:text-emerald-400">
                          เสร็จ · {(s.ms / 1000).toFixed(1)}s
                        </Badge>
                      )}
                    </div>
                    {meta.description && <p className="mt-0.5 text-[0.6875em] text-muted-foreground">{meta.description}</p>}
                  </div>
                </div>
              );
            })}
            {loading && (
              <div className="flex gap-2.5">
                <div className="flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-amber-400 bg-amber-50 text-amber-600 dark:bg-amber-950/40">
                  <Loader2 className="size-3 animate-spin" />
                </div>
                <span className="pt-0.5 text-[0.75em] font-medium text-muted-foreground">กำลังทำงาน…</span>
              </div>
            )}
          </div>

          {steps.agencies.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[0.6875em] font-medium text-muted-foreground">หน่วยงาน</p>
              <div className="space-y-1 rounded-md bg-muted/60 p-2">
                {steps.agencies.map((a) => {
                  const style = AGENCY_STYLE[a.status] ?? AGENCY_STYLE.pending;
                  return (
                    <div key={a.id} className={cn('flex items-center gap-1.5 text-[0.75em] leading-snug', style.className)}>
                      <span>{style.icon}</span>
                      {a.sectionLabel && <b className="text-foreground">[{a.sectionLabel}]</b>}
                      <span>{a.name ?? a.id}</span>
                      {a.errorType && <span className="text-[0.625em] text-red-600">({a.errorType})</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {steps.errors.length > 0 && (
            <div className="mt-2 space-y-1">
              {steps.errors.map((e, i) => (
                <div key={`err-${i}`} className="flex items-center gap-1.5 text-[0.75em] text-red-700 dark:text-red-400">
                  <span>❌</span>
                  <span>{e.name || e.errorType}: {e.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
