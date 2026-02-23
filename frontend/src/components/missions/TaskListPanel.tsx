import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { ListTodo, X } from 'lucide-react';
import type { MissionAgent, MissionTask } from '@/types/mission';

interface TaskListPanelProps {
  isOpen: boolean;
  onClose: () => void;
  tasks: MissionTask[];
  agents: MissionAgent[];
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400';
    case 'in_progress':
      return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400';
    case 'failed':
      return 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400';
    case 'reviewing':
      return 'bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400';
    default:
      return 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400';
  }
}

export const TaskListPanel: React.FC<TaskListPanelProps> = ({
  isOpen,
  onClose,
  tasks,
  agents,
}) => {
  const { t } = useTranslation();
  const getAssignmentLabel = (source: string): string => {
    switch (source) {
      case 'leader_assigned':
        return t('missions.assignmentLeader', 'Leader assigned');
      case 'team_blueprint_assigned':
        return t('missions.assignmentBlueprint', 'Team blueprint');
      case 'platform_auto_match_planning':
      case 'platform_auto_match':
        return t('missions.assignmentAutoMatch', 'Auto matched');
      case 'temporary_fallback_pending':
        return t('missions.assignmentTempPending', 'Temporary fallback');
      default:
        return t('missions.assignmentUnknown', 'Unknown');
    }
  };
  const getAssignmentReasonLabel = (code: string, fallbackText: string): string => {
    switch (code) {
      case 'leader_assigned':
        return t('missions.assignmentReasonLeaderAssigned', 'Planner selected an existing agent.');
      case 'leader_assigned_agent_not_found':
        return t(
          'missions.assignmentReasonLeaderNotFound',
          'Planner-selected agent unavailable, fallback policy applied.'
        );
      case 'team_blueprint_assigned':
        return t(
          'missions.assignmentReasonBlueprintAssigned',
          'Team blueprint matched an existing platform agent.'
        );
      case 'team_blueprint_agent_not_found':
        return t(
          'missions.assignmentReasonBlueprintNotFound',
          'Team blueprint preferred agent unavailable, fallback policy applied.'
        );
      case 'platform_auto_match_planning':
      case 'platform_auto_match':
        return t(
          'missions.assignmentReasonAutoMatch',
          'Auto matched by capability and context relevance.'
        );
      case 'no_suitable_existing_agent':
        return t(
          'missions.assignmentReasonNoExisting',
          'No suitable existing agent found for this task.'
        );
      case 'no_available_platform_agents':
        return t('missions.assignmentReasonNoAgents', 'No platform agents available right now.');
      case 'prefer_temporary_workers_policy':
        return t(
          'missions.assignmentReasonTempPolicy',
          'Policy allows temporary workers first for this task.'
        );
      case 'temporary_fallback_pending':
        return t(
          'missions.assignmentReasonTempPending',
          'Temporary worker will be provisioned during execution.'
        );
      case 'temporary_worker_provisioned':
        return t(
          'missions.assignmentReasonTempProvisioned',
          'Temporary worker was created and assigned for execution.'
        );
      case 'temporary_workers_disabled':
        return t(
          'missions.assignmentReasonTempDisabled',
          'Temporary workers are disabled and no existing agent matched.'
        );
      default:
        return fallbackText || code || t('missions.assignmentReasonUnknown', 'Policy fallback');
    }
  };
  const agentNameById = useMemo(
    () =>
      new Map(
        agents
          .filter((agent) => Boolean(agent.agent_id))
          .map((agent) => [agent.agent_id, agent.agent_name || agent.role || 'Agent'])
      ),
    [agents]
  );

  if (!isOpen) return null;

  const panel = (
    <div
      className="fixed right-0 z-[60] glass-panel border-l border-zinc-200 dark:border-zinc-700 pointer-events-auto flex flex-col animate-in slide-in-from-right duration-300 shadow-2xl"
      style={{
        top: 'var(--app-header-height, 4rem)',
        height: 'calc(100vh - var(--app-header-height, 4rem))',
        width: 'min(42vw, 560px)',
      }}
    >
      <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center gap-2 min-w-0">
          <ListTodo className="w-4 h-4 text-cyan-500" />
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">
            {t('missions.taskListTitle', 'Task List')}
          </h3>
          <span className="text-xs text-zinc-400">({tasks.length})</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-zinc-500" />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar space-y-4">
        {agents.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {agents.map((agent) => (
              <span
                key={agent.id}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300 border border-cyan-200 dark:border-cyan-500/20"
              >
                <span className="font-semibold">
                  {agent.agent_name || t('missions.unknownAgent', 'Agent')}
                </span>
                <span className="opacity-80">({agent.role})</span>
              </span>
            ))}
          </div>
        )}

        {tasks.length === 0 ? (
          <div className="text-sm text-zinc-500 py-3">
            {t('missions.noPlannedTasksYet', 'Tasks have not been planned yet.')}
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => {
              const taskMetadata =
                task.task_metadata && typeof task.task_metadata === 'object'
                  ? (task.task_metadata as Record<string, unknown>)
                  : {};
              const assignmentSource =
                typeof taskMetadata.assignment_source === 'string'
                  ? taskMetadata.assignment_source
                  : '';
              const owner =
                task.assigned_agent_name ||
                (task.assigned_agent_id ? agentNameById.get(task.assigned_agent_id) : undefined) ||
                (assignmentSource === 'temporary_fallback_pending'
                  ? t('missions.assignmentTempPending', 'Temporary fallback')
                  : undefined) ||
                t('missions.unassigned', 'Unassigned');
              const assignmentReasonCode =
                typeof taskMetadata.assignment_reason_code === 'string'
                  ? taskMetadata.assignment_reason_code
                  : '';
              const assignmentReasonText =
                typeof taskMetadata.assignment_reason === 'string'
                  ? taskMetadata.assignment_reason
                  : '';
              const dependencyLevel =
                typeof taskMetadata.dependency_level === 'number'
                  ? taskMetadata.dependency_level
                  : undefined;
              const taskResult =
                task.result && typeof task.result === 'object'
                  ? (task.result as Record<string, unknown>)
                  : {};
              const reviewFeedback =
                typeof taskMetadata.review_feedback === 'string'
                  ? taskMetadata.review_feedback
                  : undefined;
              const reviewCycle =
                typeof taskMetadata.review_cycle_count === 'number'
                  ? taskMetadata.review_cycle_count
                  : undefined;
              const attempts = Array.isArray(taskResult.attempts)
                ? (taskResult.attempts as Array<Record<string, unknown>>)
                : [];
              const lastAttempt = attempts.length > 0 ? attempts[attempts.length - 1] : undefined;
              const taskError =
                typeof taskResult.error === 'string' ? taskResult.error : undefined;
              const lastError =
                typeof taskResult.last_error === 'string' ? taskResult.last_error : undefined;
              const traceText =
                typeof lastAttempt?.traceback === 'string' ? lastAttempt.traceback : undefined;
              const lastAttemptText =
                typeof lastAttempt?.attempt === 'number'
                  ? `${lastAttempt.attempt}/${lastAttempt.max_attempts ?? '?'}`
                  : undefined;

              return (
                <div
                  key={task.task_id}
                  className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2.5 bg-white/70 dark:bg-zinc-900/60"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm text-zinc-800 dark:text-zinc-200 leading-6">
                      {task.goal_text}
                    </p>
                    <span
                      className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${statusBadgeClass(
                        task.status
                      )}`}
                    >
                      {task.status}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                    <span>
                      {t('missions.owner', 'Owner')}: {owner}
                    </span>
                    <span>•</span>
                    <span>
                      {t('missions.assignmentSource', 'Assignment')}: {getAssignmentLabel(assignmentSource)}
                    </span>
                    <span>•</span>
                    <span>
                      {t('missions.priorityShort', 'P')}: {task.priority ?? 0}
                    </span>
                    <span>•</span>
                    <span>
                      {t('missions.dependenciesShort', 'Deps')}:{' '}
                      {Array.isArray(task.dependencies) ? task.dependencies.length : 0}
                    </span>
                    {typeof dependencyLevel === 'number' && (
                      <>
                        <span>•</span>
                        <span>
                          {t('missions.executionWave', 'Wave')}: {dependencyLevel + 1}
                        </span>
                      </>
                    )}
                  </div>
                  {(assignmentReasonCode || assignmentReasonText) && (
                    <div className="mt-1 text-[11px] text-zinc-500">
                      {t('missions.assignmentReason', 'Reason')}:{' '}
                      {getAssignmentReasonLabel(assignmentReasonCode, assignmentReasonText)}
                    </div>
                  )}
                  {(lastError || attempts.length > 0) && (
                    <div className="mt-2 rounded-md border border-red-200/70 dark:border-red-500/30 bg-red-50/70 dark:bg-red-500/5 px-2.5 py-2">
                      <div className="text-[11px] text-red-700 dark:text-red-300">
                        {t('missions.debugLastError', 'Last error')}: {lastError || taskError || '-'}
                      </div>
                      <div className="text-[10px] text-red-600/90 dark:text-red-300/90 mt-0.5">
                        {t('missions.debugAttempts', 'Attempts')}: {attempts.length}
                        {lastAttemptText ? `, ${t('missions.debugLatestAttempt', 'Latest')} ${lastAttemptText}` : ''}
                      </div>
                      {traceText && (
                        <details className="mt-1">
                          <summary className="cursor-pointer text-[10px] text-red-600 dark:text-red-300">
                            {t('missions.debugTraceback', 'Traceback')}
                          </summary>
                          <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words text-[10px] leading-4 text-red-700 dark:text-red-200 bg-red-100/60 dark:bg-red-900/40 rounded p-2">
                            {traceText}
                          </pre>
                        </details>
                      )}
                    </div>
                  )}
                  {(reviewFeedback || reviewCycle !== undefined) && (
                    <div className="mt-2 rounded-md border border-amber-200/70 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-500/5 px-2.5 py-2">
                      <div className="text-[11px] text-amber-700 dark:text-amber-300">
                        {t('missions.reviewCycle', 'Review Cycle')}: {reviewCycle ?? '-'}
                      </div>
                      {reviewFeedback && (
                        <details className="mt-1">
                          <summary className="cursor-pointer text-[10px] text-amber-700 dark:text-amber-300">
                            {t('missions.reviewFeedback', 'Review Feedback')}
                          </summary>
                          <pre className="mt-1 max-h-44 overflow-auto whitespace-pre-wrap break-words text-[10px] leading-4 text-amber-800 dark:text-amber-100 bg-amber-100/70 dark:bg-amber-900/30 rounded p-2">
                            {reviewFeedback}
                          </pre>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );

  if (typeof document === 'undefined') {
    return panel;
  }
  return createPortal(panel, document.body);
};
