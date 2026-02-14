import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Rocket, ArrowLeft, ChevronRight, Search, MessageSquare, Settings } from 'lucide-react';
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
    selectMission,
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

  useEffect(() => {
    fetchMissions();
  }, [fetchMissions]);

  const filteredMissions = getFilteredMissions();

  const handleSelectMission = (mission: Mission) => {
    selectMission(mission);
  };

  const handleBack = () => {
    selectMission(null);
    setShowClarification(false);
    setShowDeliverables(false);
  };

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
              Mission {selectedMission.mission_id.substring(0, 8)}
            </p>
          </div>
          <button
            onClick={() => setShowClarification(!showClarification)}
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

        {/* Controls toolbar */}
        <MissionControls
          onOpenDeliverables={() => setShowDeliverables(true)}
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
            Create missions and watch your AI team execute them
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
            placeholder="Search missions..."
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-200 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as MissionStatus | 'all')}
          className="px-3 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
        >
          <option value="all">All Status</option>
          {(['draft', 'requirements', 'planning', 'executing', 'reviewing', 'qa', 'completed', 'failed', 'cancelled'] as MissionStatus[]).map((s) => (
            <option key={s} value={s}>{t(`missions.status.${s}`)}</option>
          ))}
        </select>
      </div>

      {/* Mission cards */}
      {isLoading && missions.length === 0 ? (
        <div className="text-center py-16 text-zinc-400">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          Loading missions...
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
            />
          ))}
        </div>
      )}

      <MissionCreateWizard isOpen={showWizard} onClose={() => setShowWizard(false)} />
      <MissionSettingsPanel isOpen={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
};

const MissionCard: React.FC<{ mission: Mission; onClick: () => void }> = ({
  mission,
  onClick,
}) => {
  const { t } = useTranslation();
  const progress =
    mission.total_tasks > 0
      ? Math.round((mission.completed_tasks / mission.total_tasks) * 100)
      : 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-5 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-emerald-300 dark:hover:border-emerald-500/30 hover:shadow-lg transition-all duration-200 group"
    >
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
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
        </div>

        <ChevronRight className="w-5 h-5 text-zinc-300 group-hover:text-emerald-500 transition-colors flex-shrink-0 mt-1" />
      </div>
    </button>
  );
};
