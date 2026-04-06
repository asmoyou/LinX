import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

import {
  EmptyState,
  LoadingState,
  MetricCard,
  NoticeBanner,
  SectionCard,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import {
  formatDateTime,
  formatDuration,
  formatNumber,
} from '@/utils/platformFormatting';

export const RunDetail = () => {
  const { t } = useTranslation();
  const { runId = '' } = useParams();
  const [isRescheduling, setIsRescheduling] = useState(false);
  const detail = useProjectExecutionStore((state) =>
    runId ? state.runDetails[runId] : undefined,
  );
  const isLoading = useProjectExecutionStore((state) => state.loading.runDetail);
  const error = useProjectExecutionStore((state) => state.errors.runDetail);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadRunDetail = useProjectExecutionStore((state) => state.loadRunDetail);
  const rescheduleRun = useProjectExecutionStore((state) => state.rescheduleRun);

  useEffect(() => {
    if (!runId) {
      return;
    }

    void loadRunDetail(runId);
  }, [loadRunDetail, runId]);

  const handleReschedule = async () => {
    if (!runId || !detail) return;
    try {
      setIsRescheduling(true);
      const refreshed = await rescheduleRun(runId);
      toast.success(
        refreshed.executorAssignment?.agentId
          ? t('projectExecution.runDetail.rescheduleSuccessAssigned', 'Run rescheduled and an agent has been assigned')
          : t('projectExecution.runDetail.rescheduleSuccess', 'Run rescheduled')
      );
    } catch (rescheduleError) {
      const message = rescheduleError instanceof Error
        ? rescheduleError.message
        : t('projectExecution.runDetail.rescheduleFailed', 'Failed to reschedule run');
      toast.error(message);
    } finally {
      setIsRescheduling(false);
    }
  };

  if (isLoading && !detail) {
    return <LoadingState label={t('projectExecution.runDetail.loading', 'Loading run detail…')} />;
  }

  if (!detail) {
    return (
      <EmptyState
        title={t('projectExecution.runDetail.notFoundTitle', 'Run not found')}
        description={t('projectExecution.runDetail.notFoundDescription', 'The requested run could not be loaded.')}
        action={
          <Link
            to="/runs"
            className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-50 dark:text-zinc-950"
          >{t('projectExecution.shared.backToProjects', 'Back to Projects')}
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          to="/runs"
          className="text-sm font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
        >{`← ${t('projectExecution.runCenter.title', 'Run Center')}`}
        </Link>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">
                {detail.projectTitle}
              </h1>
              <StatusBadge status={detail.status} />
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {detail.projectSummary}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleReschedule}
              disabled={isRescheduling}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >{isRescheduling ? t('projectExecution.shared.saving', 'Saving…') : t('projectExecution.runDetail.rescheduleAction', 'Reschedule Run')}
            </button>
            <Link
              to={`/projects/${detail.projectId}`}
              className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
            >{t('projectExecution.shared.openProject', 'Open Project')}
            </Link>
          </div>
        </div>
      </div>

      {fallbackSections.includes('runDetail') ? (
        <NoticeBanner
          title={t('projectExecution.runDetail.fallbackTitle', 'Run detail is using fallback data')}
          description={t('projectExecution.runDetail.fallbackDescription', 'This view adapts the current run model and can fall back to local seeded data if the run backend is unavailable.')}
        />
      ) : null}

      {error ? <NoticeBanner title={t('projectExecution.runDetail.errorTitle', 'Run detail issue')} description={error} /> : null}

      {detail.executorAssignment || detail.runWorkspaceRoot ? (
        <SectionCard
          title={t('projectExecution.runDetail.routingTitle', 'Execution Routing')}
          description={t('projectExecution.runDetail.routingDescription', 'How this run is currently routed and where its run sandbox lives.')}
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-[18px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.runDetail.executorKind', 'Executor Kind')}</p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">{detail.executorAssignment?.executorKind || t('projectExecution.runDetail.executorUnknown', 'Unknown')}</p>
            </div>
            <div className="rounded-[18px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.runDetail.schedulerDecision', 'Scheduler Decision')}</p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">{detail.executorAssignment?.selectionReason || t('projectExecution.runDetail.schedulerDecisionPending', 'Waiting for assignment details')}</p>
            </div>
            <div className="rounded-[18px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.runDetail.runWorkspace', 'Run Workspace')}</p>
              <p className="mt-2 break-all text-sm text-zinc-800 dark:text-zinc-200">{detail.runWorkspaceRoot || t('projectExecution.runDetail.runWorkspacePending', 'Workspace not materialized yet')}</p>
            </div>
          </div>
        </SectionCard>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label={t('projectExecution.runDetail.duration', 'Duration')} value={formatDuration(detail.startedAt, detail.completedAt)} helper={t('projectExecution.runDetail.durationHelper', 'From start to finish')} />
        <MetricCard
          label={t('projectExecution.runDetail.tasks', 'Tasks')}
          value={`${formatNumber(detail.completedTasks)}/${formatNumber(detail.totalTasks)}`}
          helper={t('projectExecution.runDetail.tasksHelper', 'Completed vs total')}
        />
        <MetricCard label={t('projectExecution.runDetail.failed', 'Failed')} value={formatNumber(detail.failedTasks)} helper={t('projectExecution.runDetail.failedHelper', 'Task failures in this run')} />
        <MetricCard label={t('projectExecution.runDetail.nodes', 'Nodes')} value={formatNumber(detail.nodeCount || detail.nodes.length)} helper={t('projectExecution.runDetail.nodesHelper', 'Involved execution nodes')} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard title={t('projectExecution.runDetail.timelineTitle', 'Timeline')} description={t('projectExecution.runDetail.timelineDescription', 'Chronological execution events for the latest run.')}>
          {detail.timeline.length > 0 ? (
            <div className="space-y-3">
              {detail.timeline.map((event) => (
                <div
                  key={event.id}
                  className="rounded-[20px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-4 dark:border-zinc-800 dark:bg-zinc-900/60"
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="font-medium text-zinc-950 dark:text-zinc-50">{event.title}</p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {event.description}
                      </p>
                    </div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">
                      {formatDateTime(event.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('projectExecution.runDetail.timelineEmpty', 'Timeline events will appear here after execution begins.')}
            </p>
          )}
        </SectionCard>

        <div className="space-y-6">
          {detail.externalSessions && detail.externalSessions.length > 0 ? (
            <SectionCard title={t('projectExecution.runDetail.externalSessionsTitle', 'External Agent Sessions')} description={t('projectExecution.runDetail.externalSessionsDescription', 'External agents currently or previously attached to this run.') }>
              <div className="space-y-3">
                {detail.externalSessions.map((session) => (
                  <div
                    key={session.id}
                    className="rounded-[18px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/60"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-medium text-zinc-950 dark:text-zinc-50">{session.runtimeType}</p>
                        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                          {t('projectExecution.runDetail.externalSessionNode', { value: session.executionNodeId, defaultValue: `Node: ${session.executionNodeId}` })}
                        </p>
                        <p className="mt-1 break-all text-xs text-zinc-500 dark:text-zinc-400">
                          {session.workdir || t('projectExecution.runDetail.externalSessionWorkdirPending', 'Workdir will be reported by the node runtime.')}
                        </p>
                        {session.errorMessage ? (
                          <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{session.errorMessage}</p>
                        ) : null}
                      </div>
                      <StatusBadge status={session.status} />
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          ) : null}

          <SectionCard title={t('projectExecution.runDetail.nodesTitle', 'Nodes')} description={t('projectExecution.runDetail.nodesDescription', 'Execution nodes that contributed to this run.')}>
            {detail.nodes.length > 0 ? (
              <div className="space-y-3">
                {detail.nodes.map((node) => (
                  <div
                    key={node.id}
                    className="rounded-[18px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/60"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-zinc-950 dark:text-zinc-50">{node.name}</p>
                        <p className="text-sm text-zinc-600 dark:text-zinc-400">{node.role}</p>
                      </div>
                      <StatusBadge status={node.status} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-600 dark:text-zinc-400">No nodes were recorded.</p>
            )}
          </SectionCard>

          <SectionCard title={t('projectExecution.runDetail.deliverablesTitle', 'Deliverables')} description="Artifacts available from the latest run output.">
            {detail.deliverables.length > 0 ? (
              <div className="space-y-3">
                {detail.deliverables.map((item) => (
                  <div
                    key={item.path}
                    className="rounded-[18px] border border-zinc-200/70 bg-zinc-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/60"
                  >
                    <p className="font-medium text-zinc-950 dark:text-zinc-50">{item.filename}</p>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{item.path}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                No deliverables were published for this run.
              </p>
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
};

export default RunDetail;
