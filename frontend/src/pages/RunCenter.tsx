import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

import { GlassPanel } from '@/components/GlassPanel';
import {
  EmptyState,
  LoadingState,
  MetricCard,
  NoticeBanner,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionPolling } from '@/hooks/useProjectExecutionPolling';
import { useAuthStore } from '@/stores/authStore';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import {
  formatDateTime,
  formatDuration,
  formatNumber,
  formatRunLabel,
  formatTokenLabel,
} from '@/utils/platformFormatting';

type RunFilter = 'attention' | 'active' | 'all';

const ATTENTION_STATUSES = new Set(['blocked', 'failed', 'reviewing']);
const ACTIVE_STATUSES = new Set(['running', 'queued', 'assigned', 'scheduled']);
const QUEUED_STATUSES = new Set(['queued', 'assigned', 'scheduled']);

const isRunHandled = (run: {
  handledAt?: string | null;
  handledSignature?: string | null;
  alertSignature?: string | null;
}): boolean => Boolean(run.handledAt && run.handledSignature && run.handledSignature === run.alertSignature);

export const RunCenter = () => {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<RunFilter>('attention');
  const [handlingRunId, setHandlingRunId] = useState<string | null>(null);
  const currentUser = useAuthStore((state) => state.user);
  const runs = useProjectExecutionStore((state) => state.runs);
  const isLoading = useProjectExecutionStore((state) => state.loading.runs);
  const error = useProjectExecutionStore((state) => state.errors.runs);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadRuns = useProjectExecutionStore((state) => state.loadRuns);
  const markRunHandled = useProjectExecutionStore((state) => state.markRunHandled);

  useEffect(() => {
    void loadRuns({ force: true });
  }, [loadRuns]);

  useProjectExecutionPolling(
    runs.some((run) => ACTIVE_STATUSES.has(run.status.toLowerCase())),
    () => loadRuns({ force: true }),
  );

  const filteredRuns = useMemo(() => {
    switch (filter) {
      case 'active':
        return runs.filter((run) => ACTIVE_STATUSES.has(run.status.toLowerCase()));
      case 'all':
        return runs;
      case 'attention':
      default:
        return runs.filter(
          (run) =>
            (ATTENTION_STATUSES.has(run.status.toLowerCase()) || run.failedTasks > 0) &&
            !isRunHandled(run),
        );
    }
  }, [filter, runs]);

  const stats = useMemo(() => {
    const attention = runs.filter(
      (run) =>
        (ATTENTION_STATUSES.has(run.status.toLowerCase()) || run.failedTasks > 0) &&
        !isRunHandled(run),
    ).length;
    const active = runs.filter((run) => ACTIVE_STATUSES.has(run.status.toLowerCase())).length;
    const queued = runs.filter((run) => QUEUED_STATUSES.has(run.status.toLowerCase())).length;

    return {
      attention,
      active,
      queued,
      showing: filteredRuns.length,
    };
  }, [filteredRuns.length, runs]);

  const handleMarkHandled = async (runId: string) => {
    try {
      setHandlingRunId(runId);
      const targetRun = runs.find((candidate) => candidate.id === runId);
      if (!targetRun?.alertSignature) {
        throw new Error('Run alert signature is unavailable');
      }
      await markRunHandled(
        runId,
        new Date().toISOString(),
        targetRun.alertSignature,
        currentUser?.id || null,
      );
      toast.success(t('projectExecution.runCenter.markHandledSuccess', 'Run marked as handled'));
    } catch (markError) {
      const message =
        markError instanceof Error
          ? markError.message
          : t('projectExecution.runCenter.markHandledError', 'Failed to mark run as handled');
      toast.error(message);
    } finally {
      setHandlingRunId(null);
    }
  };

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl space-y-3">
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-500">{t('projectExecution.runCenter.badge', 'Attempt Ops')}
          </p>
          <div>
            <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{t('projectExecution.runCenter.title', 'Attempt Ops')}</h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('projectExecution.runCenter.subtitle', 'Track execution attempts that are blocked, failing, or still in flight, then jump into the owning task or project when action is required.')}
            </p>
          </div>
        </div>

        <Link
          to="/projects"
          className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
        >{t('projectExecution.shared.backToProjects', 'Back to Projects')}
        </Link>
      </section>

      {fallbackSections.includes('runs') ? (
        <NoticeBanner
          title={t('projectExecution.runCenter.fallbackTitle', 'Attempt Ops is using fallback data')}
          description={t('projectExecution.runCenter.fallbackDescription', 'Attempts are sourced from the project execution backend and can fall back to local seeded data if those APIs are unavailable.')}
        />
      ) : null}

      {error ? <NoticeBanner title={t('projectExecution.runCenter.errorTitle', 'Run refresh issue')} description={error} /> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label={t('projectExecution.runCenter.metricAttention', 'Needs Attention')} value={formatNumber(stats.attention)} helper={t('projectExecution.runCenter.metricAttentionHelper', 'Blocked, reviewing, or failed runs')} />
        <MetricCard label={t('projectExecution.runCenter.metricActive', 'In Progress')} value={formatNumber(stats.active)} helper={t('projectExecution.runCenter.metricActiveHelper', 'Runs currently executing')} />
        <MetricCard label={t('projectExecution.runCenter.metricQueued', 'Queued')} value={formatNumber(stats.queued)} helper={t('projectExecution.runCenter.metricQueuedHelper', 'Waiting for executor pickup')} />
        <MetricCard label={t('projectExecution.runCenter.metricShowing', 'Showing')} value={formatNumber(stats.showing)} helper={t('projectExecution.runCenter.metricShowingHelper', 'Runs in the current filter')} />
      </div>

      <div className="flex flex-wrap gap-3">
        {([
          ['attention', t('projectExecution.runCenter.filterAttention', 'Needs Attention')],
          ['active', t('projectExecution.runCenter.filterActive', 'In Progress')],
          ['all', t('projectExecution.runCenter.filterAll', 'All')],
        ] as Array<[RunFilter, string]>).map(([value, label]) => {
          const isSelected = filter === value;
          return (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                isSelected
                  ? 'bg-zinc-950 text-white dark:bg-zinc-50 dark:text-zinc-950'
                  : 'border border-zinc-300 text-zinc-700 hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900'
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {isLoading && runs.length === 0 ? <LoadingState label={t('projectExecution.runCenter.loading', 'Loading runs…')} /> : null}

      {!isLoading && filteredRuns.length === 0 ? (
        <EmptyState
          title={t('projectExecution.runCenter.emptyTitle', 'No matching runs')}
          description={t('projectExecution.runCenter.emptyDescription', 'Change the filter or wait for new run activity to appear.')}
        />
      ) : null}

      {filteredRuns.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {filteredRuns.map((run) => (
            <GlassPanel
              key={run.id}
              hover
              className="border border-zinc-200/70 bg-white/80 p-6 dark:border-zinc-800 dark:bg-zinc-950/60"
            >
              <div className="flex h-full flex-col gap-4">
                {isRunHandled(run) ? (
                  <div className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                    {t('projectExecution.runCenter.handledStatus', 'Handled')}
                  </div>
                ) : null}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                      {t('projectExecution.runCenter.updatedPrefix', {
                        value: formatDateTime(run.updatedAt),
                        defaultValue: `Updated ${formatDateTime(run.updatedAt)}`,
                      })}
                    </p>
                    <h2 className="mt-2 text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {formatRunLabel(run.id)}
                    </h2>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
                      <span>{t('projectExecution.runCenter.projectPrefix', 'Project')}</span>
                      <Link
                        to={`/projects/${run.projectId}`}
                        className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                      >
                        {run.projectTitle}
                      </Link>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
                      <span>{t('projectExecution.runCenter.taskPrefix', 'Task')}</span>
                      {run.taskId ? (
                        <Link
                          to={`/projects/${run.projectId}/tasks/${run.taskId}`}
                          className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                        >
                          {run.taskTitle || run.taskId}
                        </Link>
                      ) : (
                        <span>{run.taskTitle || t('projectExecution.runCenter.taskUnknown', 'Unknown task')}</span>
                      )}
                    </div>
                  </div>
                  <StatusBadge status={run.status} />
                </div>

                <div className="grid gap-3 rounded-[20px] border border-zinc-200/70 bg-zinc-50/70 p-4 sm:grid-cols-5 dark:border-zinc-800 dark:bg-zinc-900/60">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.startedAt', 'Started')}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                      {formatDateTime(run.startedAt)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.duration', 'Duration')}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                      {formatDuration(run.startedAt, run.completedAt)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.tasks', 'Tasks')}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                      {run.completedTasks}/{run.totalTasks}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.failed', 'Failed')}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                      {run.failedTasks}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.triggerSource', 'Trigger')}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                      {formatTokenLabel(run.triggerSource)}
                    </p>
                  </div>
                </div>

                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  {t('projectExecution.runCenter.createdPrefix', {
                    value: formatDateTime(run.createdAt),
                    defaultValue: `Created ${formatDateTime(run.createdAt)}`,
                  })}
                </p>

                {run.failureReason ? (
                  <div className="rounded-2xl border border-rose-300/60 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
                    <p className="font-medium">{t('projectExecution.runCenter.failureTitle', 'Failure reason')}</p>
                    <p className="mt-1 leading-6">{run.failureReason}</p>
                  </div>
                ) : run.latestSignal ? (
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {run.latestSignal}
                  </p>
                ) : null}

                <div className="mt-auto flex flex-wrap gap-3">
                  {(ATTENTION_STATUSES.has(run.status.toLowerCase()) || run.failedTasks > 0) &&
                  !isRunHandled(run) ? (
                    <button
                      type="button"
                      onClick={() => void handleMarkHandled(run.id)}
                      disabled={handlingRunId === run.id}
                      className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                    >
                      {handlingRunId === run.id
                        ? t('projectExecution.shared.saving', 'Saving…')
                        : t('projectExecution.runCenter.markHandledAction', 'Mark Handled')}
                    </button>
                  ) : null}
                  <Link
                    to={`/runs/${run.id}`}
                    className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
                  >{t('projectExecution.shared.openRun', 'Open Run')}
                  </Link>
                  <Link
                    to={`/projects/${run.projectId}`}
                    className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                  >{t('projectExecution.shared.openProject', 'Open Project')}
                  </Link>
                  {run.taskId ? (
                    <Link
                      to={`/projects/${run.projectId}/tasks/${run.taskId}`}
                      className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                    >
                      {t('projectExecution.runDetail.openTaskAction', 'Open Task')}
                    </Link>
                  ) : null}
                </div>
              </div>
            </GlassPanel>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default RunCenter;
