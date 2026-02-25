import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Save, SlidersHorizontal } from 'lucide-react';
import { missionsApi } from '@/api/missions';
import { MissionSettingsPanel } from '@/components/missions/MissionSettingsPanel';
import type { MissionSettings } from '@/types/mission';

export const MissionPolicySettings = () => {
  const { t } = useTranslation();
  const [missionSettings, setMissionSettings] = useState<MissionSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPanelOpen, setIsPanelOpen] = useState(false);

  const loadSettings = async () => {
    setIsLoading(true);
    try {
      const data = await missionsApi.getSettings();
      setMissionSettings(data);
    } catch (error) {
      console.error('Failed to load mission settings:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadSettings();
  }, []);

  const execution = missionSettings?.execution_config;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-5 bg-white dark:bg-zinc-900/40">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-5 h-5 text-emerald-500" />
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                {t('settings.missionPolicy.title', 'Mission Execution Policy')}
              </h2>
            </div>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-2">
              {t(
                'settings.missionPolicy.subtitle',
                'Configure default retry, timeout, and team execution behavior for all missions.'
              )}
            </p>
          </div>

          <button
            onClick={() => setIsPanelOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
          >
            <Save className="w-4 h-4" />
            {t('settings.missionPolicy.openEditor', 'Open Policy Editor')}
          </button>
        </div>

        {isLoading && (
          <div className="mt-4 inline-flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{t('settings.missionPolicy.loading', 'Loading policy...')}</span>
          </div>
        )}

        {!isLoading && execution && (
          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3">
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('settings.missionPolicy.maxRetries', 'Max Retries')}
              </p>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mt-1">
                {execution.max_retries}
              </p>
            </div>
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3">
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('settings.missionPolicy.taskTimeout', 'Task Timeout')}
              </p>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mt-1">
                {execution.task_timeout_s}s
              </p>
            </div>
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3">
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('settings.missionPolicy.maxConcurrentTasks', 'Max Concurrent Tasks')}
              </p>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mt-1">
                {execution.max_concurrent_tasks}
              </p>
            </div>
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3">
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('settings.missionPolicy.networkAccess', 'Network Access')}
              </p>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mt-1">
                {execution.network_access ? t('settings.enabled', 'Enabled') : t('settings.disabled', 'Disabled')}
              </p>
            </div>
          </div>
        )}
      </div>

      <MissionSettingsPanel
        isOpen={isPanelOpen}
        onClose={() => {
          setIsPanelOpen(false);
          void loadSettings();
        }}
      />
    </div>
  );
};
