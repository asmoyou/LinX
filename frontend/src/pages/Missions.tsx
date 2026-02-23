import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  Rocket,
  ArrowLeft,
  ChevronRight,
  Search,
  MessageSquare,
  Settings,
  Trash2,
  Download,
  Eye,
  AlertTriangle,
  X,
} from 'lucide-react';
import { useMissionStore } from '@/stores/missionStore';
import { MissionFlowCanvas } from '@/components/missions/MissionFlowCanvas';
import { MissionCreateWizard } from '@/components/missions/MissionCreateWizard';
import { MissionControls } from '@/components/missions/MissionControls';
import { ClarificationPanel } from '@/components/missions/ClarificationPanel';
import { DeliverablesPanel } from '@/components/missions/DeliverablesPanel';
import { TaskListPanel } from '@/components/missions/TaskListPanel';
import { MissionSettingsPanel } from '@/components/missions/MissionSettingsPanel';
import { LayoutModal } from '@/components/LayoutModal';
import { ModalPanel } from '@/components/ModalPanel';
import { selectLatestMissionRunEvents } from '@/utils/missionEvents';
import { missionsApi } from '@/api/missions';
import type { Mission, MissionEvent, MissionStatus } from '@/types/mission';

const statusColors: Record<MissionStatus, string> = {
  draft: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400',
  requirements: 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
  planning: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400',
  executing: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  reviewing: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  qa: 'bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400',
  completed: 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400',
  failed: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
  cancelled: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-500',
};

const statusDots: Record<MissionStatus, string> = {
  draft: 'bg-zinc-400',
  requirements: 'bg-blue-500',
  planning: 'bg-indigo-500',
  executing: 'bg-emerald-500 animate-pulse',
  reviewing: 'bg-amber-500 animate-pulse',
  qa: 'bg-purple-500 animate-pulse',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  cancelled: 'bg-zinc-400',
};

const quickDeliverableStatuses = new Set<MissionStatus>(['completed']);

type DeliverableSummary = {
  finalCount: number;
  intermediateCount: number;
  sampleNames: string[];
};

type TaskAttemptDiagnostic = {
  attempt: number;
  maxAttempts?: number;
  error?: string;
  errorType?: string;
  willRetry?: boolean;
  backoffSeconds?: number;
  traceback?: string;
  timestamp?: string;
};

type FailureTaskDiagnostic = {
  taskId: string;
  title: string;
  owner: string;
  reviewFeedback?: string;
  reviewCycle?: number;
  attempts: number;
  lastError?: string;
  blockedDependencyTitles: string[];
  attemptDiagnostics: TaskAttemptDiagnostic[];
};

function getEventErrorMessage(event: MissionEvent): string {
  if (typeof event.event_data?.error === 'string' && event.event_data.error.trim()) {
    return event.event_data.error.trim();
  }
  if (typeof event.event_data?.summary === 'string' && event.event_data.summary.trim()) {
    return event.event_data.summary.trim();
  }
  if (typeof event.message === 'string' && event.message.trim()) {
    return event.message.trim();
  }
  return '';
}

function getEventDataString(event: MissionEvent, key: string): string | undefined {
  const value = event.event_data?.[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;
}

function getEventDataNumber(event: MissionEvent, key: string): number | undefined {
  const value = event.event_data?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function formatEventType(eventType: string): string {
  return eventType
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatTimestamp(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatMissionCardTime(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatMissionDuration(startedAt?: string, endedAt?: string): string | null {
  if (!startedAt || !endedAt) return null;
  const started = new Date(startedAt).getTime();
  const ended = new Date(endedAt).getTime();
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended <= started) {
    return null;
  }
  const totalSeconds = Math.floor((ended - started) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function buildDeliverableSummary(mission: Mission): DeliverableSummary {
  const result = mission.result && typeof mission.result === 'object'
    ? (mission.result as Record<string, unknown>)
    : null;
  const rawDeliverables = Array.isArray(result?.deliverables) ? result.deliverables : [];
  const deliverables = rawDeliverables.filter(
    (item): item is Record<string, unknown> =>
      typeof item === 'object' && item !== null
  );
  const isFinalDeliverable = (item: Record<string, unknown>): boolean => {
    if (item.is_target === true) return true;
    if (typeof item.artifact_kind === 'string' && item.artifact_kind.toLowerCase() === 'final') {
      return true;
    }
    if (typeof item.source_scope === 'string' && item.source_scope.toLowerCase() === 'output') {
      return true;
    }
    return false;
  };
  const finalDeliverables = deliverables.filter((item) => isFinalDeliverable(item));
  const intermediateDeliverables = deliverables.filter((item) => !isFinalDeliverable(item));
  const sampleNames = finalDeliverables
    .map((item) => {
      if (typeof item.filename === 'string' && item.filename.trim().length > 0) {
        return item.filename.trim();
      }
      if (typeof item.path === 'string' && item.path.trim().length > 0) {
        const trimmed = item.path.trim();
        const segments = trimmed.split('/');
        return segments[segments.length - 1] || trimmed;
      }
      return '';
    })
    .filter((name) => name.length > 0)
    .slice(0, 3);

  return {
    finalCount: finalDeliverables.length,
    intermediateCount: intermediateDeliverables.length,
    sampleNames,
  };
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

export const Missions: React.FC = () => {
  const { t } = useTranslation();
  const {
    missions,
    selectedMission,
    isLoading,
    fetchMissions,
    deleteMission,
    selectMission,
    missionEvents,
    missionTasks,
    missionAgents,
    fetchMissionEvents,
    fetchMissionTasks,
    fetchMissionAgents,
    setSearchQuery,
    setStatusFilter,
    getFilteredMissions,
    statusFilter,
    searchQuery,
  } = useMissionStore();

  const [showWizard, setShowWizard] = useState(false);
  const [showClarification, setShowClarification] = useState(false);
  const [showDeliverables, setShowDeliverables] = useState(false);
  const [showTaskList, setShowTaskList] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showFailureDiagnosticsModal, setShowFailureDiagnosticsModal] = useState(false);
  const [quickDeliverablesMissionId, setQuickDeliverablesMissionId] = useState<string | null>(null);
  const [downloadingArchiveMissionId, setDownloadingArchiveMissionId] = useState<string | null>(null);
  const [deletingMissionId, setDeletingMissionId] = useState<string | null>(null);
  const autoOpenedClarificationRef = useRef<string>('');
  const selectedMissionId = selectedMission?.mission_id;
  const selectedMissionStatus = selectedMission?.status;
  const selectedMissionEvents = useMemo(
    () =>
      selectedMissionId
        ? selectLatestMissionRunEvents(
            missionEvents.filter((event) => event.mission_id === selectedMissionId)
          )
        : [],
    [missionEvents, selectedMissionId]
  );

  useEffect(() => {
    fetchMissions();
  }, [fetchMissions]);

  useEffect(() => {
    if (!selectedMissionId) return;
    fetchMissionEvents(selectedMissionId);
    fetchMissionTasks(selectedMissionId);
    fetchMissionAgents(selectedMissionId);
  }, [selectedMissionId, fetchMissionEvents, fetchMissionTasks, fetchMissionAgents]);

  useEffect(() => {
    if (!selectedMissionId) return;
    const requestCount = selectedMissionEvents.filter(
      (event) =>
        event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
        event.event_type === 'clarification_request'
    ).length;
    if (selectedMissionStatus !== 'requirements' || requestCount === 0) return;

    const autoOpenKey = `${selectedMissionId}:${requestCount}`;
    if (autoOpenedClarificationRef.current !== autoOpenKey) {
      setShowClarification(true);
      autoOpenedClarificationRef.current = autoOpenKey;
    }
  }, [selectedMissionEvents, selectedMissionId, selectedMissionStatus]);

  const filteredMissions = getFilteredMissions();

  const handleSelectMission = (mission: Mission) => {
    setQuickDeliverablesMissionId(null);
    setShowFailureDiagnosticsModal(false);
    selectMission(mission);
  };

  const handleBack = () => {
    selectMission(null);
    setShowClarification(false);
    setShowDeliverables(false);
    setShowTaskList(false);
    setShowFailureDiagnosticsModal(false);
  };

  const handleDeleteMission = async (mission: Mission) => {
    const confirmed = window.confirm(t('missions.deleteConfirm', { title: mission.title }));
    if (!confirmed) return;

    setDeletingMissionId(mission.mission_id);
    try {
      await deleteMission(mission.mission_id);
    } catch {
      // Error toast is handled by API interceptor/store.
    } finally {
      setDeletingMissionId(null);
    }
  };

  const handleOpenQuickDeliverables = (missionId: string) => {
    setQuickDeliverablesMissionId(missionId);
  };

  const handleDownloadTargetArchive = async (mission: Mission) => {
    setDownloadingArchiveMissionId(mission.mission_id);
    try {
      const { blob, filename } = await missionsApi.downloadDeliverablesArchive(
        mission.mission_id,
        { targetOnly: true }
      );
      const fallbackName = `${mission.title || 'mission'}_targets_deliverables.zip`;
      downloadBlob(blob, filename || fallbackName);
    } catch {
      // API interceptor shows toast.
    } finally {
      setDownloadingArchiveMissionId((current) =>
        current === mission.mission_id ? null : current
      );
    }
  };

  const hasPendingClarification = Boolean(
    selectedMissionId &&
      selectedMissionStatus === 'requirements' &&
      selectedMissionEvents.some(
        (event) =>
          (event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
            event.event_type === 'clarification_request')
      )
  );

  const failureEventsForSelected = useMemo(() => {
    if (!selectedMission) return [];
    return selectedMissionEvents
      .filter((event) => event.event_type === 'MISSION_FAILED' || event.event_type === 'PHASE_FAILED')
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 12);
  }, [selectedMission, selectedMissionEvents]);
  const failureTaskDiagnostics = useMemo<FailureTaskDiagnostic[]>(() => {
    if (!selectedMission) return [];

    const taskTitleById = new Map(
      missionTasks.map((task) => {
        const metadata =
          task.task_metadata && typeof task.task_metadata === 'object'
            ? (task.task_metadata as Record<string, unknown>)
            : {};
        const title =
          typeof metadata.title === 'string' && metadata.title.trim().length > 0
            ? metadata.title
            : task.goal_text;
        return [task.task_id, title];
      })
    );
    const agentNameById = new Map(
      missionAgents
        .filter((agent) => Boolean(agent.agent_id))
        .map((agent) => [agent.agent_id, agent.agent_name || agent.role || 'Agent'])
    );

    return missionTasks
      .filter((task) => task.status === 'failed')
      .map((task) => {
        const metadata =
          task.task_metadata && typeof task.task_metadata === 'object'
            ? (task.task_metadata as Record<string, unknown>)
            : {};
        const result =
          task.result && typeof task.result === 'object'
            ? (task.result as Record<string, unknown>)
            : {};
        const reviewFeedback =
          typeof metadata.review_feedback === 'string' ? metadata.review_feedback : undefined;
        const reviewCycle =
          typeof metadata.review_cycle_count === 'number' ? metadata.review_cycle_count : undefined;
        const attemptEntries = Array.isArray(result.attempts)
          ? (result.attempts as Array<Record<string, unknown>>)
          : [];
        const attemptDiagnostics: TaskAttemptDiagnostic[] = attemptEntries
          .map((entry, index) => {
            const attempt =
              typeof entry.attempt === 'number' && Number.isFinite(entry.attempt)
                ? entry.attempt
                : index + 1;
            const maxAttempts =
              typeof entry.max_attempts === 'number' && Number.isFinite(entry.max_attempts)
                ? entry.max_attempts
                : undefined;
            const error = typeof entry.error === 'string' ? entry.error : undefined;
            const errorType = typeof entry.error_type === 'string' ? entry.error_type : undefined;
            const willRetry = typeof entry.will_retry === 'boolean' ? entry.will_retry : undefined;
            const backoffSeconds =
              typeof entry.backoff_s === 'number' && Number.isFinite(entry.backoff_s)
                ? entry.backoff_s
                : undefined;
            const traceback = typeof entry.traceback === 'string' ? entry.traceback : undefined;
            const timestamp = typeof entry.timestamp === 'string' ? entry.timestamp : undefined;
            return {
              attempt,
              maxAttempts,
              error,
              errorType,
              willRetry,
              backoffSeconds,
              traceback,
              timestamp,
            };
          })
          .filter((entry) => Boolean(entry.error || entry.traceback || entry.errorType));
        const attempts = attemptEntries.length;
        const lastError =
          (typeof result.last_error === 'string' && result.last_error) ||
          (typeof result.error === 'string' && result.error) ||
          undefined;
        const blockedDependencies =
          typeof result.error === 'string' &&
          result.error.startsWith('Blocked by failed dependencies:')
            ? result.error
                .split(':')
                .slice(1)
                .join(':')
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean)
            : [];
        const blockedDependencyTitles = blockedDependencies.map(
          (taskId) => taskTitleById.get(taskId) || taskId
        );
        const owner =
          task.assigned_agent_name ||
          (task.assigned_agent_id ? agentNameById.get(task.assigned_agent_id) : undefined) ||
          t('missions.unassigned', 'Unassigned');
        return {
          taskId: task.task_id,
          title: taskTitleById.get(task.task_id) || task.goal_text,
          owner,
          reviewFeedback,
          reviewCycle,
          attempts,
          lastError,
          blockedDependencyTitles,
          attemptDiagnostics,
        };
      });
  }, [selectedMission, missionTasks, missionAgents, t]);
  const reviewRetryEventsForSelected = useMemo(() => {
    if (!selectedMission) return [];
    return selectedMissionEvents
      .filter(
        (event) =>
          event.event_type === 'REVIEW_CYCLE_RETRY'
      )
      .sort((a, b) => {
        const aTs = new Date(a.created_at).getTime();
        const bTs = new Date(b.created_at).getTime();
        return aTs - bTs;
      });
  }, [selectedMission, selectedMissionEvents]);
  const executionErrorEventsForSelected = useMemo(() => {
    if (!selectedMission) return [];
    return selectedMissionEvents
      .filter(
        (event) =>
          (event.event_type === 'TASK_ATTEMPT_FAILED' ||
            event.event_type === 'PHASE_ATTEMPT_FAILED' ||
            event.event_type === 'TASK_FAILED' ||
            event.event_type === 'PHASE_FAILED' ||
            event.event_type === 'MISSION_FAILED' ||
            (event.event_type === 'QA_VERDICT' &&
              String(event.event_data?.verdict || '').toUpperCase() === 'FAIL'))
      )
      .sort((a, b) => {
        const aTs = new Date(a.created_at).getTime();
        const bTs = new Date(b.created_at).getTime();
        return bTs - aTs;
      })
      .slice(0, 24);
  }, [selectedMission, selectedMissionEvents]);
  const failureRootCause = useMemo(() => {
    const missionLevel = selectedMission?.error_message?.trim();
    if (missionLevel) return missionLevel;

    for (const event of executionErrorEventsForSelected) {
      const eventError = getEventErrorMessage(event);
      if (eventError) return eventError;
    }
    return t('missions.unknownFailure', 'Unknown failure');
  }, [executionErrorEventsForSelected, selectedMission?.error_message, t]);
  const failureRootCausePreview =
    failureRootCause.length > 240 ? `${failureRootCause.slice(0, 240)}...` : failureRootCause;
  const failedAttemptCount = useMemo(
    () => failureTaskDiagnostics.reduce((total, item) => total + item.attempts, 0),
    [failureTaskDiagnostics]
  );

  // Detail view
  if (selectedMission) {
    return (
      <div className="space-y-4 animate-in fade-in slide-in-from-bottom-6 duration-700">
        {/* Header */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleBack}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-zinc-500" />
          </button>
          <div className="flex-1">
            <h1 className="text-2xl font-bold tracking-tight text-zinc-800 dark:text-zinc-200">
              {selectedMission.title}
            </h1>
            <p className="text-sm text-zinc-500 mt-0.5">
              {t('missions.shortId', { id: selectedMission.mission_id.substring(0, 8) })}
            </p>
          </div>
          <button
            onClick={() => {
              setShowDeliverables(false);
              setShowTaskList(false);
              setShowClarification(!showClarification);
            }}
            className={`p-2 rounded-lg transition-colors ${
              showClarification
                ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10'
                : 'hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500'
            }`}
            title={t('missions.clarification')}
          >
            <MessageSquare className="w-5 h-5" />
          </button>
        </div>

        {hasPendingClarification && !showClarification && (
          <button
            onClick={() => setShowClarification(true)}
            className="w-full text-left px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-200 text-sm font-medium"
          >
            {t('missions.clarificationNeeded')}
          </button>
        )}

        {selectedMission.status === 'failed' && (
          <div
            role="button"
            tabIndex={0}
            onClick={() => setShowFailureDiagnosticsModal(true)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                setShowFailureDiagnosticsModal(true);
              }
            }}
            className="rounded-xl border border-red-200 dark:border-red-500/40 bg-red-50 dark:bg-red-500/10 px-4 py-3 cursor-pointer hover:bg-red-100/80 dark:hover:bg-red-500/15 transition-colors"
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 w-8 h-8 rounded-lg bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300 flex items-center justify-center">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-red-700 dark:text-red-300">
                  {t('missions.failureReason', 'Failure Reason')}
                </div>
                <div className="mt-1 text-sm text-red-700/90 dark:text-red-200 break-words">
                  {failureRootCausePreview}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-red-700 dark:text-red-300">
                  <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30">
                    {t('missions.failedTasks', 'Failed Tasks')}: {failureTaskDiagnostics.length}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30">
                    {t('missions.debugAttempts', 'Attempts')}: {failedAttemptCount}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30">
                    {t('missions.executionErrors', 'Execution Errors')}: {executionErrorEventsForSelected.length}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setShowFailureDiagnosticsModal(true);
                }}
                className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-red-300 dark:border-red-500/40 text-red-700 dark:text-red-200 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
              >
                <Eye className="w-3.5 h-3.5" />
                {t('missions.viewFailureDetails', 'View Details')}
              </button>
            </div>
          </div>
        )}

        {/* Controls toolbar */}
        <MissionControls
          onOpenDeliverables={() => {
            setShowClarification(false);
            setShowTaskList(false);
            setShowDeliverables((prev) => !prev);
          }}
          onToggleTaskList={() => {
            setShowClarification(false);
            setShowDeliverables(false);
            setShowTaskList((prev) => !prev);
          }}
          isTaskListOpen={showTaskList}
          onFitView={() => {/* handled by react flow */}}
        />

        {/* Flow canvas */}
        <MissionFlowCanvas missionId={selectedMission.mission_id} />

        {/* Side panels */}
        <ClarificationPanel
          missionId={selectedMission.mission_id}
          isOpen={showClarification}
          onClose={() => setShowClarification(false)}
        />
        <DeliverablesPanel
          missionId={selectedMission.mission_id}
          isOpen={showDeliverables}
          onClose={() => setShowDeliverables(false)}
        />
        <TaskListPanel
          isOpen={showTaskList}
          onClose={() => setShowTaskList(false)}
          tasks={missionTasks}
          agents={missionAgents}
        />

        <LayoutModal
          isOpen={showFailureDiagnosticsModal}
          onClose={() => setShowFailureDiagnosticsModal(false)}
          closeOnBackdropClick={true}
          closeOnEscape={true}
        >
          <ModalPanel className="w-full max-w-5xl p-0 max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
              <div>
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                  {t('missions.failureDetailsTitle', 'Failure Details')}
                </h2>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t('missions.shortId', { id: selectedMission.mission_id.substring(0, 8) })}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowFailureDiagnosticsModal(false)}
                className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 transition-colors"
                aria-label={t('common.close', 'Close')}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto px-6 py-4 space-y-4">
              <section className="rounded-xl border border-red-200 dark:border-red-500/40 bg-red-50/70 dark:bg-red-500/10 p-4">
                <div className="text-sm font-semibold text-red-700 dark:text-red-300">
                  {t('missions.failureRootCause', 'Root Cause')}
                </div>
                <div className="mt-1 text-sm text-red-700/90 dark:text-red-200 whitespace-pre-wrap break-words">
                  {failureRootCause}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-red-700 dark:text-red-300">
                  <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30">
                    {t('missions.failedTasks', 'Failed Tasks')}: {failureTaskDiagnostics.length}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30">
                    {t('missions.debugAttempts', 'Attempts')}: {failedAttemptCount}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30">
                    {t('missions.executionErrors', 'Execution Errors')}: {executionErrorEventsForSelected.length}
                  </span>
                </div>
              </section>

              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 p-4">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">
                  {t('missions.attemptFailureDetails', 'Attempt Failure Details')}
                </div>
                {failureTaskDiagnostics.length === 0 ? (
                  <div className="text-sm text-zinc-500">{t('missions.noFailureDetails', 'No failure details available.')}</div>
                ) : (
                  <div className="space-y-3">
                    {failureTaskDiagnostics.map((taskDiagnostic) => (
                      <div
                        key={taskDiagnostic.taskId}
                        className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/50 p-3"
                      >
                        <div className="flex flex-wrap items-start gap-2">
                          <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                            {taskDiagnostic.title}
                          </div>
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-200/80 dark:bg-zinc-700 text-zinc-600 dark:text-zinc-300">
                            {t('missions.owner', 'Owner')}: {taskDiagnostic.owner}
                          </span>
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300">
                            {t('missions.debugAttempts', 'Attempts')}: {taskDiagnostic.attempts}
                          </span>
                        </div>
                        {taskDiagnostic.blockedDependencyTitles.length > 0 && (
                          <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
                            {t('missions.blockedDependencies', 'Blocked by dependencies')}:{' '}
                            {taskDiagnostic.blockedDependencyTitles.join(', ')}
                          </div>
                        )}
                        {taskDiagnostic.lastError && (
                          <div className="mt-2 text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap break-words">
                            {t('missions.debugLastError', 'Last error')}: {taskDiagnostic.lastError}
                          </div>
                        )}
                        {taskDiagnostic.attemptDiagnostics.length > 0 && (
                          <div className="mt-2 space-y-2">
                            {taskDiagnostic.attemptDiagnostics.map((attemptDiagnostic, attemptIndex) => (
                              <div
                                key={`${taskDiagnostic.taskId}-${attemptDiagnostic.attempt}-${attemptIndex}`}
                                className="rounded-md border border-red-200/70 dark:border-red-500/30 bg-red-50/70 dark:bg-red-500/5 p-2"
                              >
                                <div className="text-[11px] text-red-700 dark:text-red-300">
                                  {t('missions.attemptLabel', 'Attempt')} {attemptDiagnostic.attempt}
                                  {attemptDiagnostic.maxAttempts
                                    ? `/${attemptDiagnostic.maxAttempts}`
                                    : ''}
                                  {attemptDiagnostic.errorType ? ` • ${attemptDiagnostic.errorType}` : ''}
                                  {attemptDiagnostic.willRetry !== undefined
                                    ? ` • ${attemptDiagnostic.willRetry ? t('missions.retry', 'Retry') : t('missions.status.failed', 'Failed')}`
                                    : ''}
                                  {attemptDiagnostic.backoffSeconds !== undefined
                                    ? ` • ${t('missions.backoffSeconds', 'Backoff {{seconds}}s', {
                                        seconds: attemptDiagnostic.backoffSeconds,
                                      })}`
                                    : ''}
                                  {attemptDiagnostic.timestamp
                                    ? ` • ${formatTimestamp(attemptDiagnostic.timestamp)}`
                                    : ''}
                                </div>
                                {attemptDiagnostic.error && (
                                  <div className="mt-1 text-[11px] whitespace-pre-wrap break-words text-red-700/95 dark:text-red-200">
                                    {attemptDiagnostic.error}
                                  </div>
                                )}
                                {attemptDiagnostic.traceback && (
                                  <details className="mt-1">
                                    <summary className="cursor-pointer text-[11px] text-red-700 dark:text-red-300">
                                      {t('missions.debugTraceback', 'Traceback')}
                                    </summary>
                                    <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-red-800 dark:text-red-100 bg-red-100 dark:bg-red-900/40 rounded p-2">
                                      {attemptDiagnostic.traceback}
                                    </pre>
                                  </details>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {failureEventsForSelected.length > 0 && (
                <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 p-4">
                  <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">
                    {t('missions.phaseFailureDetails', 'Mission/Phase Failures')}
                  </div>
                  <div className="space-y-2">
                    {failureEventsForSelected.map((event) => {
                      const phase = getEventDataString(event, 'phase');
                      const errorType = getEventDataString(event, 'error_type');
                      const trace = getEventDataString(event, 'traceback');
                      const errorMessage = getEventErrorMessage(event);
                      return (
                        <div
                          key={event.event_id}
                          className="rounded-md border border-red-200/70 dark:border-red-500/30 bg-red-50/70 dark:bg-red-500/5 p-2.5"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-red-700 dark:text-red-300">
                            <span className="font-medium">{formatEventType(event.event_type)}</span>
                            {phase && <span>{t('missions.failedPhase', 'Failed Phase')}: {phase}</span>}
                            {errorType && <span>{t('missions.errorType', 'Error Type')}: {errorType}</span>}
                            <span>{formatTimestamp(event.created_at)}</span>
                          </div>
                          {errorMessage && (
                            <div className="mt-1 text-[11px] text-red-700/95 dark:text-red-200 whitespace-pre-wrap break-words">
                              {errorMessage}
                            </div>
                          )}
                          {trace && (
                            <details className="mt-1">
                              <summary className="cursor-pointer text-[11px] text-red-700 dark:text-red-300">
                                {t('missions.debugTraceback', 'Traceback')}
                              </summary>
                              <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-red-800 dark:text-red-100 bg-red-100 dark:bg-red-900/40 rounded p-2">
                                {trace}
                              </pre>
                            </details>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {reviewRetryEventsForSelected.length > 0 && (
                <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 p-4">
                  <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">
                    {t('missions.reviewLoopTimeline', 'Review Loop Timeline')}
                  </div>
                  <div className="space-y-2">
                    {reviewRetryEventsForSelected.map((event) => (
                      <div
                        key={event.event_id}
                        className="rounded-md border border-amber-200/70 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-500/5 p-2.5 text-[11px] text-amber-700 dark:text-amber-300"
                      >
                        <div className="font-medium">{formatEventType(event.event_type)}</div>
                        <div className="mt-0.5">
                          {getEventErrorMessage(event) || event.message || '-'}
                        </div>
                        <div className="mt-0.5 text-amber-700/80 dark:text-amber-300/80">
                          {formatTimestamp(event.created_at)}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {executionErrorEventsForSelected.length > 0 && (
                <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 p-4">
                  <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">
                    {t('missions.failureTimeline', 'Failure Timeline')}
                  </div>
                  <div className="space-y-2">
                    {executionErrorEventsForSelected.map((event) => {
                      const eventError = getEventErrorMessage(event);
                      const attempt = getEventDataNumber(event, 'attempt');
                      const maxAttempts = getEventDataNumber(event, 'max_attempts');
                      const eventType = formatEventType(event.event_type);
                      return (
                        <div
                          key={`timeline-${event.event_id}`}
                          className="rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/50 p-2.5"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                            <span className="font-medium text-zinc-700 dark:text-zinc-200">{eventType}</span>
                            {event.task_id && (
                              <span>
                                {t('missions.taskId', 'Task')}: {event.task_id.slice(0, 8)}
                              </span>
                            )}
                            {attempt !== undefined && (
                              <span>
                                {t('missions.debugAttempts', 'Attempts')}: {attempt}
                                {maxAttempts !== undefined ? `/${maxAttempts}` : ''}
                              </span>
                            )}
                            <span>{formatTimestamp(event.created_at)}</span>
                          </div>
                          {eventError && (
                            <div className="mt-1 text-[11px] text-zinc-700 dark:text-zinc-200 whitespace-pre-wrap break-words">
                              {eventError}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </div>
          </ModalPanel>
        </LayoutModal>
      </div>
    );
  }

  // List view
  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2 text-zinc-800 dark:text-zinc-200">
            {t('missions.title')}
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 font-medium">
            {t('missions.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(true)}
            className="p-2.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-xl transition-colors text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            title={t('missions.settings')}
          >
            <Settings className="w-5 h-5" />
          </button>
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors shadow-lg shadow-emerald-500/20"
          >
            <Plus className="w-4 h-4" />
            {t('missions.create')}
          </button>
        </div>
      </header>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('missions.searchPlaceholder')}
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-200 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as MissionStatus | 'all')}
          className="px-3 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
        >
          <option value="all">{t('missions.allStatus')}</option>
          {(['draft', 'requirements', 'planning', 'executing', 'reviewing', 'qa', 'completed', 'failed', 'cancelled'] as MissionStatus[]).map((s) => (
            <option key={s} value={s}>{t(`missions.status.${s}`)}</option>
          ))}
        </select>
      </div>

      {/* Mission cards */}
      {isLoading && missions.length === 0 ? (
        <div className="text-center py-16 text-zinc-400">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          {t('missions.loadingMissions')}
        </div>
      ) : filteredMissions.length === 0 ? (
        <div className="text-center py-16">
          <Rocket className="w-12 h-12 text-zinc-300 dark:text-zinc-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-zinc-600 dark:text-zinc-400 mb-1">
            {t('missions.noMissions')}
          </h3>
          <p className="text-sm text-zinc-400 mb-4">{t('missions.createFirst')}</p>
          <button
            onClick={() => setShowWizard(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('missions.create')}
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredMissions.map((mission) => (
            <MissionCard
              key={mission.mission_id}
              mission={mission}
              onClick={() => handleSelectMission(mission)}
              onOpenQuickDeliverables={() => handleOpenQuickDeliverables(mission.mission_id)}
              onDownloadTargetArchive={() => handleDownloadTargetArchive(mission)}
              isDownloadingArchive={downloadingArchiveMissionId === mission.mission_id}
              onDelete={() => handleDeleteMission(mission)}
              isDeleting={deletingMissionId === mission.mission_id}
            />
          ))}
        </div>
      )}

      <MissionCreateWizard isOpen={showWizard} onClose={() => setShowWizard(false)} />
      <MissionSettingsPanel isOpen={showSettings} onClose={() => setShowSettings(false)} />
      <DeliverablesPanel
        missionId={quickDeliverablesMissionId || ''}
        isOpen={Boolean(quickDeliverablesMissionId)}
        onClose={() => setQuickDeliverablesMissionId(null)}
      />
    </div>
  );
};

const MissionCard: React.FC<{
  mission: Mission;
  onClick: () => void;
  onOpenQuickDeliverables: () => void;
  onDownloadTargetArchive: () => void;
  isDownloadingArchive: boolean;
  onDelete: () => void;
  isDeleting: boolean;
}> = ({
  mission,
  onClick,
  onOpenQuickDeliverables,
  onDownloadTargetArchive,
  isDownloadingArchive,
  onDelete,
  isDeleting,
}) => {
  const { t } = useTranslation();
  const progress =
    mission.total_tasks > 0
      ? Math.round((mission.completed_tasks / mission.total_tasks) * 100)
      : 0;
  const isTerminalMissionStatus =
    mission.status === 'completed' || mission.status === 'failed' || mission.status === 'cancelled';
  const isTerminalMission = quickDeliverableStatuses.has(mission.status);
  const deliverableSummary = buildDeliverableSummary(mission);
  const remainingCount = Math.max(deliverableSummary.finalCount - deliverableSummary.sampleNames.length, 0);
  const missionDuration = formatMissionDuration(mission.started_at, mission.completed_at);

  return (
    <div className="w-full text-left p-5 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-lg transition-all duration-200 group">
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <button onClick={onClick} className="w-full text-left">
            <div className="flex items-center gap-2 mb-2">
              <div className={`w-2 h-2 rounded-full ${statusDots[mission.status]}`} />
              <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-200 truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                {mission.title}
              </h3>
            </div>
            <p className="text-sm text-zinc-500 line-clamp-2 mb-3">
              {mission.instructions}
            </p>
            {mission.status === 'failed' && mission.error_message && (
              <p className="text-xs text-red-600 dark:text-red-300 line-clamp-2 mb-3">
                {mission.error_message}
              </p>
            )}

            <div className="flex items-center gap-3">
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${statusColors[mission.status]}`}>
                {t(`missions.status.${mission.status}`)}
              </span>

              {mission.total_tasks > 0 && (
                <div className="flex items-center gap-2">
                  <div className="w-16 bg-zinc-200 dark:bg-zinc-700 rounded-full h-1.5">
                    <div
                      className="bg-emerald-500 h-1.5 rounded-full transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-zinc-400">
                    {mission.completed_tasks}/{mission.total_tasks}
                  </span>
                </div>
              )}

              {missionDuration && (
                <span className="text-[10px] text-zinc-400">
                  {t('missions.durationLabel', 'Duration')}: {missionDuration}
                </span>
              )}
            </div>

            <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
              <div className="rounded-md border border-zinc-200/80 dark:border-zinc-700/80 bg-zinc-50/70 dark:bg-zinc-800/40 px-2.5 py-1.5">
                <div className="text-zinc-400">{t('missions.createdAtLabel', 'Created')}</div>
                <div className="text-zinc-700 dark:text-zinc-200 mt-0.5">
                  {formatMissionCardTime(mission.created_at)}
                </div>
              </div>
              <div className="rounded-md border border-zinc-200/80 dark:border-zinc-700/80 bg-zinc-50/70 dark:bg-zinc-800/40 px-2.5 py-1.5">
                <div className="text-zinc-400">{t('missions.startedAtLabel', 'Started')}</div>
                <div className="text-zinc-700 dark:text-zinc-200 mt-0.5">
                  {mission.started_at
                    ? formatMissionCardTime(mission.started_at)
                    : t('missions.notStarted', 'Not started')}
                </div>
              </div>
              <div className="rounded-md border border-zinc-200/80 dark:border-zinc-700/80 bg-zinc-50/70 dark:bg-zinc-800/40 px-2.5 py-1.5">
                <div className="text-zinc-400">{t('missions.finishedAtLabel', 'Finished')}</div>
                <div className="text-zinc-700 dark:text-zinc-200 mt-0.5">
                  {mission.completed_at
                    ? formatMissionCardTime(mission.completed_at)
                    : isTerminalMissionStatus
                      ? t('missions.notFinished', 'Not finished')
                      : t('missions.inProgress', 'In progress')}
                </div>
              </div>
            </div>
          </button>

          {isTerminalMission && (
            <div className="mt-3 pt-3 border-t border-zinc-200/80 dark:border-zinc-700/80">
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
                  {t('missions.quickDeliverables')}
                </span>
                <span className="text-[11px] text-zinc-400">
                  {t('missions.finalDeliverablesSummary', {
                    count: deliverableSummary.finalCount,
                  })}
                  {deliverableSummary.intermediateCount > 0
                    ? ` • ${t('missions.intermediateFilesSummary', {
                        count: deliverableSummary.intermediateCount,
                      })}`
                    : ''}
                </span>
              </div>
              {deliverableSummary.sampleNames.length > 0 ? (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {deliverableSummary.sampleNames.map((name, index) => (
                    <span
                      key={`${mission.mission_id}-${name}-${index}`}
                      className="inline-flex items-center rounded-full border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-300"
                    >
                      {name}
                    </span>
                  ))}
                  {remainingCount > 0 && (
                    <span className="inline-flex items-center rounded-full border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500 dark:text-zinc-400">
                      +{remainingCount}
                    </span>
                  )}
                </div>
              ) : (
                <div className="text-[11px] text-zinc-400 mb-2">
                  {t('missions.noFinalDeliverablesYet')}
                </div>
              )}
              {deliverableSummary.intermediateCount > 0 && (
                <div className="text-[10px] text-zinc-400 mb-2">
                  {t('missions.intermediateFilesHint')}
                </div>
              )}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onOpenQuickDeliverables}
                  className="inline-flex items-center gap-1.5 rounded-md border border-zinc-200 dark:border-zinc-700 px-2.5 py-1 text-[11px] font-medium text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <Eye className="w-3.5 h-3.5" />
                  {t('missions.quickViewDeliverables')}
                </button>
                <button
                  type="button"
                  onClick={onDownloadTargetArchive}
                  disabled={isDownloadingArchive || deliverableSummary.finalCount === 0}
                  className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 dark:border-emerald-500/30 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  <Download className="w-3.5 h-3.5" />
                  {isDownloadingArchive
                    ? t('missions.downloadingArchive')
                    : t('missions.downloadTargetArchive')}
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-start gap-2">
          <button
            onClick={onDelete}
            disabled={isDeleting}
            className="p-2 rounded-lg text-zinc-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={t('missions.delete')}
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <ChevronRight className="w-5 h-5 text-zinc-300 group-hover:text-emerald-500 transition-colors flex-shrink-0 mt-1" />
        </div>
      </div>
    </div>
  );
};
