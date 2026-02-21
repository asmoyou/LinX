import React from 'react';
import { useTranslation } from 'react-i18next';
import { Play, XCircle, Package, Maximize } from 'lucide-react';
import { useMissionStore } from '@/stores/missionStore';
import type { MissionStatus } from '@/types/mission';

const statusColors: Record<MissionStatus, string> = {
  draft: 'bg-zinc-100 text-zinc-600',
  requirements: 'bg-blue-100 text-blue-700',
  planning: 'bg-indigo-100 text-indigo-700',
  executing: 'bg-emerald-100 text-emerald-700',
  reviewing: 'bg-amber-100 text-amber-700',
  qa: 'bg-purple-100 text-purple-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-zinc-100 text-zinc-500',
};

interface MissionControlsProps {
  onOpenDeliverables: () => void;
  onFitView: () => void;
}

export const MissionControls: React.FC<MissionControlsProps> = ({
  onOpenDeliverables,
  onFitView,
}) => {
  const { t } = useTranslation();
  const { selectedMission, startMission, cancelMission } = useMissionStore();

  if (!selectedMission) return null;

  const canStart = selectedMission.status === 'draft';
  const canCancel = ['requirements', 'planning', 'executing', 'reviewing', 'qa'].includes(
    selectedMission.status
  );
  const canOpenDeliverables = selectedMission.status !== 'draft';
  const handleStart = () => {
    void startMission(selectedMission.mission_id).catch(() => {
      // Error toast is handled by API interceptor/store.
    });
  };
  const handleCancel = () => {
    void cancelMission(selectedMission.mission_id).catch(() => {
      // Error toast is handled by API interceptor/store.
    });
  };

  return (
    <div className="flex items-center gap-3 p-3 glass-panel rounded-xl border border-zinc-200 dark:border-zinc-700">
      {/* Status badge */}
      <span
        className={`text-xs font-semibold px-3 py-1.5 rounded-full ${statusColors[selectedMission.status]}`}
      >
        {t(`missions.status.${selectedMission.status}`)}
      </span>

      {/* Progress */}
      <div className="flex items-center gap-2 text-xs text-zinc-500">
        <span>
          {selectedMission.completed_tasks}/{selectedMission.total_tasks}
        </span>
        {selectedMission.total_tasks > 0 && (
          <div className="w-20 bg-zinc-200 dark:bg-zinc-700 rounded-full h-1.5">
            <div
              className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500"
              style={{
                width: `${Math.round(
                  (selectedMission.completed_tasks / selectedMission.total_tasks) * 100
                )}%`,
              }}
            />
          </div>
        )}
      </div>

      <div className="flex-1" />

      {/* Actions */}
      {canStart && (
        <button
          onClick={handleStart}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors"
        >
          <Play className="w-3.5 h-3.5" />
          {t('missions.start')}
        </button>
      )}

      {canCancel && (
        <button
          onClick={handleCancel}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-500/10 dark:hover:bg-red-500/20 rounded-lg transition-colors"
        >
          <XCircle className="w-3.5 h-3.5" />
          {t('missions.cancel')}
        </button>
      )}

      {canOpenDeliverables && (
        <button
          onClick={onOpenDeliverables}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-lg transition-colors"
        >
          <Package className="w-3.5 h-3.5" />
          {t('missions.deliverables')}
        </button>
      )}

      <button
        onClick={onFitView}
        className="p-1.5 text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 bg-zinc-100 dark:bg-zinc-800 rounded-lg transition-colors"
        title="Fit view"
      >
        <Maximize className="w-4 h-4" />
      </button>
    </div>
  );
};
