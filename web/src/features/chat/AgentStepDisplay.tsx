import { cn } from "@/shared/lib/utils";
import type { AgentStep } from "@/shared/types";
import type { StreamingState } from "@/shared/types/chat";

const STEP_LABELS: Record<string, { icon: string; label: string }> = {
  discover: { icon: '🔍', label: 'ค้นหาหน่วยงาน' },
  classify: { icon: '🧠', label: 'วิเคราะห์คำถาม' },
  invoke: { icon: '🔗', label: 'สืบค้นจากหน่วยงาน' },
  verify: { icon: '✅', label: 'ตรวจสอบความเกี่ยวข้อง' },
  synthesize: { icon: '📝', label: 'สังเคราะห์คำตอบ' },
};

/** Legacy: render from AgentStep[] array */
export function AgentStepDisplay({ steps, visibleCount }: { steps: AgentStep[]; visibleCount: number }) {
  return (
    <div className="bg-muted/50 rounded-lg p-3 mb-3 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground mb-2">กระบวนการทำงานของ AI Agent:</p>
      {steps.slice(0, visibleCount).map((step, i) => {
        const isActive = i === visibleCount - 1 && visibleCount <= steps.length;
        const isDone = i < visibleCount - 1 || visibleCount > steps.length;
        return (
          <div key={i} className="flex items-center gap-2 text-xs animate-fade-in">
            <span>{step.icon}</span>
            <span className={cn(
              isDone && 'text-foreground',
              isActive && 'text-primary font-medium',
            )}>
              {step.label}
            </span>
            {isDone && <span className="text-green-600 text-[10px]">✓</span>}
            {isActive && <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
          </div>
        );
      })}
    </div>
  );
}

/** Streaming: render from StreamingState with pipeline steps + per-agency status */
export function StreamingProgress({ state }: { state: StreamingState }) {
  return (
    <div className="bg-muted/50 rounded-lg p-3 mb-3 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground mb-2">กระบวนการทำงานของ AI Agent:</p>

      {/* Pipeline steps */}
      {state.pipelineSteps.map((ps, i) => {
        const info = STEP_LABELS[ps.name] ?? { icon: '⚙️', label: ps.name };
        const isRunning = ps.status === 'running';
        return (
          <div key={`step-${i}`} className="flex items-center gap-2 text-xs animate-fade-in">
            <span>{info.icon}</span>
            <span className={cn(
              !isRunning && 'text-foreground',
              isRunning && 'text-primary font-medium',
            )}>
              {info.label}
            </span>
            {ps.ms != null && (
              <span className="text-muted-foreground text-[10px]">{(ps.ms / 1000).toFixed(1)}s</span>
            )}
            {!isRunning && <span className="text-green-600 text-[10px]">✓</span>}
            {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
          </div>
        );
      })}

      {/* Per-agency status (under invoke step) */}
      {Object.values(state.agencyStatuses).length > 0 && (
        <div className="ml-4 mt-1 space-y-1 border-l-2 border-muted pl-3">
          {Object.values(state.agencyStatuses).map((a) => {
            const statusIcon = a.status === 'error' ? '❌' : a.status === 'passed' ? '✅' : a.status === 'rejected' ? '⚠️' : a.status === 'running' ? '⏳' : '🔗';
            const isRunning = a.status === 'running';
            return (
              <div key={a.agencyId} className="flex items-center gap-2 text-xs animate-fade-in">
                <span>{statusIcon}</span>
                <span className={cn(
                  !isRunning && 'text-muted-foreground',
                  isRunning && 'text-primary font-medium',
                )}>
                  {a.agencyName ?? a.agencyId}
                </span>
                {a.status === 'error' && a.errorType && (
                  <span className="text-destructive text-[10px]">({a.errorType})</span>
                )}
                {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
              </div>
            );
          })}
        </div>
      )}

      {/* Streaming errors */}
      {state.errors.length > 0 && (
        <div className="mt-1 space-y-1">
          {state.errors.map((err, i) => (
            <div key={`err-${i}`} className="flex items-center gap-2 text-xs text-destructive animate-fade-in">
              <span>❌</span>
              <span>{err.name || err.errorType}: {err.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}