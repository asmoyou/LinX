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
} from 'lucide-react';
import { useMissionStore } from '@/stores/missionStore';
import { MissionFlowCanvas } from '@/components/missions/MissionFlowCanvas';
import { MissionCreateWizard } from '@/components/missions/MissionCreateWizard';
import { MissionControls } from '@/components/missions/MissionControls';
import { ClarificationPanel } from '@/components/missions/ClarificationPanel';
import { DeliverablesPanel } from '@/components/missions/DeliverablesPanel';
import { MissionSettingsPanel } from '@/components/missions/MissionSettingsPanel';
import type { Mission, MissionStatus } from '@/types/mission';

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
    setSearchQuery,
    setStatusFilter,
    getFilteredMissions,
    statusFilter,
    searchQuery,
  } = useMissionStore();

  const [showWizard, setShowWizard] = useState(false);
  const [showClarification, setShowClarification] = useState(false);
  const [showDeliverables, setShowDeliverables] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [deletingMissionId, setDeletingMissionId] = useState<string | null>(null);
  const autoOpenedClarificationRef = useRef<string>('');
  const selectedMissionId = selectedMission?.mission_id;
  const selectedMissionStatus = selectedMission?.status;
  const agentNameById = useMemo(
    () =>
      new Map(
        missionAgents
          .filter((agent) => Boolean(agent.agent_id))
          .map((agent) => [agent.agent_id, agent.agent_name || agent.role || 'Agent'])
      ),
    [missionAgents]
  );

  useEffect(() => {
    fetchMissions();
  }, [fetchMissions]);

  useEffect(() => {
    if (!selectedMissionId) return;
    fetchMissionEvents(selectedMissionId);
  }, [selectedMissionId, fetchMissionEvents]);

  useEffect(() => {
    if (!selectedMissionId) return;
    const requestCount = missionEvents.filter(
      (event) =>
        event.mission_id === selectedMissionId &&
        (event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
          event.event_type === 'clarification_request')
    ).length;
    if (selectedMissionStatus !== 'requirements' || requestCount === 0) return;

    const autoOpenKey = `${selectedMissionId}:${requestCount}`;
    if (autoOpenedClarificationRef.current !== autoOpenKey) {
      setShowClarification(true);
      autoOpenedClarificationRef.current = autoOpenKey;
    }
  }, [selectedMissionId, selectedMissionStatus, missionEvents]);

  const filteredMissions = getFilteredMissions();

  const handleSelectMission = (mission: Mission) => {
    selectMission(mission);
  };

  const handleBack = () => {
    selectMission(null);
    setShowClarification(false);
    setShowDeliverables(false);
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

  const hasPendingClarification = Boolean(
    selectedMissionId &&
      selectedMissionStatus === 'requirements' &&
      missionEvents.some(
        (event) =>
          event.mission_id === selectedMissionId &&
          (event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
            event.event_type === 'clarification_request')
      )
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

        {/* Controls toolbar */}
        <MissionControls
          onOpenDeliverables={() => {
            setShowClarification(false);
            setShowDeliverables(true);
          }}
          onFitView={() => {/* handled by react flow */}}
        />

        <section className="glass-panel rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                {t('missions.taskListTitle', 'Task List')}
              </h2>
              <p className="text-xs text-zinc-500 mt-0.5">
                {t(
                  'missions.taskListSubtitle',
                  'See who is executing each task and current dependency progress.'
                )}
              </p>
            </div>
            <span className="text-xs font-medium px-2 py-1 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300">
              {missionTasks.length} {t('missions.tasksCountLabel', 'tasks')}
            </span>
          </div>

          {missionAgents.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {missionAgents.map((agent) => (
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

          {missionTasks.length === 0 ? (
            <div className="text-sm text-zinc-500 py-3">
              {t('missions.noPlannedTasksYet', 'Tasks have not been planned yet.')}
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1 custom-scrollbar">
              {missionTasks.map((task) => {
                const owner =
                  task.assigned_agent_name ||
                  (task.assigned_agent_id ? agentNameById.get(task.assigned_agent_id) : undefined) ||
                  t('missions.unassigned', 'Unassigned');

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
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${
                          task.status === 'completed'
                            ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400'
                            : task.status === 'in_progress'
                              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
                              : task.status === 'failed'
                                ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                                : task.status === 'reviewing'
                                  ? 'bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400'
                                  : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400'
                        }`}
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
                        {t('missions.priorityShort', 'P')}: {task.priority ?? 0}
                      </span>
                      <span>•</span>
                      <span>
                        {t('missions.dependenciesShort', 'Deps')}:{' '}
                        {Array.isArray(task.dependencies) ? task.dependencies.length : 0}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

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
              onDelete={() => handleDeleteMission(mission)}
              isDeleting={deletingMissionId === mission.mission_id}
            />
          ))}
        </div>
      )}

      <MissionCreateWizard isOpen={showWizard} onClose={() => setShowWizard(false)} />
      <MissionSettingsPanel isOpen={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
};

const MissionCard: React.FC<{
  mission: Mission;
  onClick: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}> = ({
  mission,
  onClick,
  onDelete,
  isDeleting,
}) => {
  const { t } = useTranslation();
  const progress =
    mission.total_tasks > 0
      ? Math.round((mission.completed_tasks / mission.total_tasks) * 100)
      : 0;

  return (
    <div className="w-full text-left p-5 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-lg transition-all duration-200 group">
      <div className="flex items-start gap-4">
        <button onClick={onClick} className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2 mb-2">
            <div className={`w-2 h-2 rounded-full ${statusDots[mission.status]}`} />
            <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-200 truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
              {mission.title}
            </h3>
          </div>
          <p className="text-sm text-zinc-500 line-clamp-2 mb-3">
            {mission.instructions}
          </p>

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

            <span className="text-[10px] text-zinc-400">
              {new Date(mission.created_at).toLocaleDateString()}
            </span>
          </div>
        </button>

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
