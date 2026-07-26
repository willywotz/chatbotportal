import { Activity, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/shared/lib/utils';
import type { AgentStepsSnapshot } from '@/shared/types/chat';

const STEP_LABELS: Record<string, { icon: string; label: string }> = {
  discover: { icon: '🔍', label: 'ค้นหาหน่วยงาน' },
  classify: { icon: '🧠', label: 'วิเคราะห์คำถาม' },
  invoke: { icon: '🔗', label: 'สืบค้นจากหน่วยงาน' },
  verify: { icon: '✅', label: 'ตรวจสอบความเกี่ยวข้อง' },
  summarize: { icon: '📌', label: 'สรุปภาพรวม' },
  synthesize: { icon: '📝', label: 'สังเคราะห์คำตอบ' },
};

const AGENCY_ICON: Record<string, string> = {
  error: '❌', passed: '✅', rejected: '⚠️', ok: '⏳', running: '🔗', pending: '🔗',
};

/**
 * Collapsible card showing the AI-agent pipeline snapshot (steps + per-agency
 * statuses + errors), fed by either the live `StreamingState` or a persisted
 * `Message.agent_steps` snapshot. Renders nothing when there is no snapshot.
 */
export function AgentStepsCard({ steps }: { steps: AgentStepsSnapshot | null }) {
  const [open, setOpen] = useState(false);
  if (!steps) return null;

  return (
    <div className="rounded-lg border border-border bg-muted/40 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Activity className="h-3.5 w-3.5 shrink-0" />
        <span className="font-medium">กระบวนการทำงานของ AI Agent</span>
        {open ? <ChevronUp className="ml-auto h-3.5 w-3.5" /> : <ChevronDown className="ml-auto h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-border px-3 pb-3 pt-2 text-xs text-muted-foreground">
          {steps.steps.map((s, i) => {
            const info = STEP_LABELS[s.name] ?? { icon: '⚙️', label: s.name };
            return (
              <div key={`step-${i}`} className="flex items-center gap-2">
                <span>{info.icon}</span>
                <span className="text-foreground">{info.label}</span>
                {s.ms != null && <span className="text-[10px]">{(s.ms / 1000).toFixed(1)}s</span>}
                <span className="text-green-600 text-[10px]">✓</span>
              </div>
            );
          })}
          {steps.agencies.length > 0 && (
            <div className="ml-4 mt-1 space-y-1 border-l-2 border-muted pl-3">
              {steps.agencies.map((a) => (
                <div key={a.id} className="flex items-center gap-2">
                  <span>{AGENCY_ICON[a.status] ?? '🔗'}</span>
                  <span>{a.name ?? a.id}</span>
                  {a.errorType && <span className="text-destructive text-[10px]">({a.errorType})</span>}
                </div>
              ))}
            </div>
          )}
          {steps.errors.map((e, i) => (
            <div key={`err-${i}`} className={cn('flex items-center gap-2 text-destructive')}>
              <span>❌</span>
              <span>{e.name || e.errorType}: {e.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
