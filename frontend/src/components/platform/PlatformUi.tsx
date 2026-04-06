import type { ReactNode } from 'react';

import { GlassPanel } from '@/components/GlassPanel';
import { LoadingSpinner } from '@/components/LoadingSpinner';

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
  planning: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  queued: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
  assigned: 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300',
  scheduled: 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300',
  running: 'bg-sky-500/10 text-sky-700 dark:text-sky-300',
  blocked: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
  reviewing: 'bg-violet-500/10 text-violet-700 dark:text-violet-300',
  completed: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  failed: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
  cancelled: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
  working: 'bg-sky-500/10 text-sky-700 dark:text-sky-300',
  idle: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  offline: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
  connected: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  disconnected: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
  error: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
  syncing: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  default: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300',
};

const formatToken = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(' ');

interface StatusBadgeProps {
  status?: string | null;
}

export const StatusBadge = ({ status }: StatusBadgeProps) => {
  const normalized = (status || 'unknown').toLowerCase();
  const className = STATUS_STYLES[normalized] || STATUS_STYLES.default;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}
    >
      {formatToken(normalized)}
    </span>
  );
};

interface MetricCardProps {
  label: string;
  value: string;
  helper?: string;
}

export const MetricCard = ({ label, value, helper }: MetricCardProps) => (
  <GlassPanel className="h-full border border-zinc-200/70 bg-white/80 p-5 dark:border-zinc-800 dark:bg-zinc-950/60">
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
      {label}
    </p>
    <p className="mt-3 text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
    {helper ? (
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{helper}</p>
    ) : null}
  </GlassPanel>
);

interface SectionCardProps {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}

export const SectionCard = ({ title, description, action, children }: SectionCardProps) => (
  <GlassPanel className="border border-zinc-200/70 bg-white/80 p-6 dark:border-zinc-800 dark:bg-zinc-950/60">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-zinc-950 dark:text-zinc-50">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
    <div className="mt-5">{children}</div>
  </GlassPanel>
);

interface LoadingStateProps {
  label?: string;
}

export const LoadingState = ({ label = 'Loading data…' }: LoadingStateProps) => (
  <div className="flex min-h-[260px] flex-col items-center justify-center gap-4 rounded-[24px] border border-dashed border-zinc-300/80 bg-white/60 px-6 text-center dark:border-zinc-700 dark:bg-zinc-950/40">
    <LoadingSpinner size="lg" />
    <p className="text-sm text-zinc-600 dark:text-zinc-400">{label}</p>
  </div>
);

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
}

export const EmptyState = ({ title, description, action }: EmptyStateProps) => (
  <GlassPanel className="border border-dashed border-zinc-300/80 bg-white/70 p-8 text-center dark:border-zinc-700 dark:bg-zinc-950/50">
    <h2 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">{title}</h2>
    <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
    {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
  </GlassPanel>
);

interface NoticeBannerProps {
  title: string;
  description: string;
}

export const NoticeBanner = ({ title, description }: NoticeBannerProps) => (
  <GlassPanel className="border border-amber-500/20 bg-amber-500/5 p-4 dark:border-amber-400/20 dark:bg-amber-400/10">
    <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">{title}</p>
    <p className="mt-1 text-sm text-amber-700/80 dark:text-amber-200/80">{description}</p>
  </GlassPanel>
);
