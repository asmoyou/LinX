import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { GlassPanel } from '@/components/GlassPanel';
import {
  EmptyState,
  LoadingState,
  MetricCard,
  NoticeBanner,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import {
  formatDateTime,
  formatDuration,
  formatNumber,
} from '@/utils/platformFormatting';

export const RunCenter = () => {
  const { t } = useTranslation();
  const runs = useProjectExecutionStore((state) => state.runs);
  const isLoading = useProjectExecutionStore((state) => state.loading.runs);
  const error = useProjectExecutionStore((state) => state.errors.runs);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadRuns = useProjectExecutionStore((state) => state.loadRuns);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const stats = useMemo(() => {
    const active = runs.filter((run) => ['running', 'reviewing'].includes(run.status.toLowerCase())).length;
    const completed = runs.filter((run) => run.status.toLowerCase() === 'completed').length;
    const failed = runs.filter((run) => run.failedTasks > 0 || run.status.toLowerCase() === 'failed').length;

    return {
      total: runs.length,
      active,
      completed,
      failed,
    };
  }, [runs]);

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl space-y-3">
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-500">{t('projectExecution.runCenter.badge', 'Operations')}
          </p>
          <div>
            <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{t('projectExecution.runCenter.title', 'Run Center')}</h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('projectExecution.runCenter.subtitle', 'Review recent execution attempts, watch long-running delivery streams, and jump back into the owning project when attention is needed.')}
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
          title={t('projectExecution.runCenter.fallbackTitle', 'Run Center is using fallback data')}
          description={t('projectExecution.runCenter.fallbackDescription', 'Runs are sourced from the project execution backend and can fall back to local seeded data if those APIs are unavailable.')}
        />
      ) : null}

      {error ? <NoticeBanner title={t('projectExecution.runCenter.errorTitle', 'Run refresh issue')} description={error} /> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label={t('projectExecution.runCenter.metricRuns', 'Runs')} value={formatNumber(stats.total)} helper={t('projectExecution.runCenter.metricRunsHelper', 'Recent execution streams')} />
        <MetricCard label={t('projectExecution.runCenter.metricActive', 'Active')} value={formatNumber(stats.active)} helper={t('projectExecution.runCenter.metricActiveHelper', 'Currently running or reviewing')} />
        <MetricCard label={t('projectExecution.runCenter.metricCompleted', 'Completed')} value={formatNumber(stats.completed)} helper={t('projectExecution.runCenter.metricCompletedHelper', 'Finished without active work')} />
        <MetricCard label={t('projectExecution.runCenter.metricAttention', 'Attention')} value={formatNumber(stats.failed)} helper={t('projectExecution.runCenter.metricAttentionHelper', 'Failures or degraded execution')} />
      </div>

      {isLoading && runs.length === 0 ? <LoadingState label={t('projectExecution.runCenter.loading', 'Loading runs…')} /> : null}

      {!isLoading && runs.length === 0 ? (
        <EmptyState
          title={t('projectExecution.runCenter.emptyTitle', 'No runs available')}
          description={t('projectExecution.runCenter.emptyDescription', 'Execution runs will appear here as soon as projects begin running.')}
        />
      ) : null}

      {runs.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {runs.map((run) => (
            <GlassPanel
              key={run.id}
              hover
              className="border border-zinc-200/70 bg-white/80 p-6 dark:border-zinc-800 dark:bg-zinc-950/60"
            >
              <div className="flex h-full flex-col gap-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                      {formatDateTime(run.updatedAt)}
                    </p>
                    <h2 className="mt-2 text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {run.projectTitle}
                    </h2>
                  </div>
                  <StatusBadge status={run.status} />
                </div>

                <div className="grid gap-3 rounded-[20px] border border-zinc-200/70 bg-zinc-50/70 p-4 sm:grid-cols-4 dark:border-zinc-800 dark:bg-zinc-900/60">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.duration', 'Duration')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {formatDuration(run.startedAt, run.completedAt)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.tasks', 'Tasks')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {run.completedTasks}/{run.totalTasks}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.failed', 'Failed')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {run.failedTasks}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.runCenter.externalAgents', 'External Agents')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {run.externalAgentCount ?? '—'}
                    </p>
                  </div>
                </div>

                {run.latestSignal ? (
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {run.latestSignal}
                  </p>
                ) : null}

                <div className="mt-auto flex flex-wrap gap-3">
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
