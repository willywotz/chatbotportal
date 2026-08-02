import type { ReactNode } from 'react';
import { cn } from '@/shared/lib/utils';

/**
 * Canonical admin page header: one `<h1>`, an optional muted subtitle, an
 * optional leading icon, and a right-aligned action slot. Replaces the
 * per-page header markup that had drifted across four different sizes and
 * heading levels.
 */
export function PageHeader({
  title,
  subtitle,
  icon,
  actions,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap items-center justify-between gap-3', className)}>
      <div>
        <h1 className="text-2xl flex items-center gap-2">
          {icon}
          {title}
        </h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
