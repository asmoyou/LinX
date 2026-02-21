import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Settings, X, Loader2, ChevronDown, ChevronUp, Save } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useMissionStore } from '@/stores/missionStore';
import { llmApi } from '@/api/llm';
import { ModalPanel } from '@/components/ModalPanel';
import type { MissionRoleConfig, MissionExecutionConfig, MissionSettings } from '@/types/mission';

interface MissionSettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const DEFAULT_ROLE_CONFIG: MissionRoleConfig = {
  llm_provider: '',
  llm_model: '',
  temperature: 0.7,
  max_tokens: 4096,
};

const DEFAULT_EXECUTION_CONFIG: MissionExecutionConfig = {
  max_retries: 3,
  task_timeout_s: 600,
  max_rework_cycles: 2,
  network_access: false,
  max_concurrent_tasks: 3,
};

type RoleKey = 'leader_config' | 'supervisor_config' | 'qa_config';

const ROLES: { key: RoleKey; labelKey: string }[] = [
  { key: 'leader_config', labelKey: 'missions.leader' },
  { key: 'supervisor_config', labelKey: 'missions.supervisor' },
  { key: 'qa_config', labelKey: 'missions.qaAuditor' },
];

export const MissionSettingsPanel: React.FC<MissionSettingsPanelProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const { missionSettings, fetchMissionSettings, updateMissionSettings } = useMissionStore();

  const [providers, setProviders] = useState<Record<string, string[]>>({});
  const [leaderConfig, setLeaderConfig] = useState<MissionRoleConfig>({ ...DEFAULT_ROLE_CONFIG });
  const [supervisorConfig, setSupervisorConfig] = useState<MissionRoleConfig>({ ...DEFAULT_ROLE_CONFIG });
  const [qaConfig, setQaConfig] = useState<MissionRoleConfig>({ ...DEFAULT_ROLE_CONFIG });
  const [executionConfig, setExecutionConfig] = useState<MissionExecutionConfig>({ ...DEFAULT_EXECUTION_CONFIG });
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    leader_config: true,
    supervisor_config: false,
    qa_config: false,
    execution: true,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setSaveSuccess(false);
      setSaveError(null);
      fetchMissionSettings();
      loadProviders();
    }
  }, [isOpen, fetchMissionSettings]);

  useEffect(() => {
    if (missionSettings) {
      setLeaderConfig({ ...DEFAULT_ROLE_CONFIG, ...missionSettings.leader_config });
      setSupervisorConfig({ ...DEFAULT_ROLE_CONFIG, ...missionSettings.supervisor_config });
      setQaConfig({ ...DEFAULT_ROLE_CONFIG, ...missionSettings.qa_config });
      setExecutionConfig({ ...DEFAULT_EXECUTION_CONFIG, ...missionSettings.execution_config });
    }
  }, [missionSettings]);

  const loadProviders = async () => {
    setIsLoadingProviders(true);
    try {
      const data = await llmApi.getAvailableProviders({ suppressErrorToast: true });
      setProviders(data);
    } catch {
      // providers will remain empty
    } finally {
      setIsLoadingProviders(false);
    }
  };

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    setSaveError(null);
    try {
      const data: Partial<MissionSettings> = {
        leader_config: leaderConfig,
        supervisor_config: supervisorConfig,
        qa_config: qaConfig,
        execution_config: executionConfig,
      };
      await updateMissionSettings(data);
      setSaveSuccess(true);
      toast.success(t('missions.settingsSaved'));
      onClose();
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (error) {
      let message = t('missions.settingsSaveFailed');
      if (axios.isAxiosError(error)) {
        const responseData = error.response?.data as { detail?: string; message?: string } | undefined;
        message = responseData?.detail || responseData?.message || error.message || message;
      } else if (error instanceof Error) {
        message = error.message;
      }
      setSaveError(message);
      toast.error(message);
    } finally {
      setIsSaving(false);
    }
  };

  const getConfigState = (key: RoleKey): [MissionRoleConfig, React.Dispatch<React.SetStateAction<MissionRoleConfig>>] => {
    switch (key) {
      case 'leader_config': return [leaderConfig, setLeaderConfig];
      case 'supervisor_config': return [supervisorConfig, setSupervisorConfig];
      case 'qa_config': return [qaConfig, setQaConfig];
    }
  };

  if (!isOpen) return null;

  const providerNames = Array.from(
    new Set(
      [
        ...Object.keys(providers),
        leaderConfig.llm_provider,
        supervisorConfig.llm_provider,
        qaConfig.llm_provider,
      ].filter((provider): provider is string => Boolean(provider))
    )
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <ModalPanel className="max-w-3xl w-full max-h-[85vh] overflow-hidden flex flex-col p-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
          <div className="flex items-center gap-2.5">
            <Settings className="w-5 h-5 text-emerald-500" />
            <div>
              <h2 className="text-lg font-bold text-zinc-800 dark:text-zinc-100">
                {t('missions.settingsTitle')}
              </h2>
              <p className="text-xs text-zinc-500 mt-0.5">
                {t('missions.settingsDescription')}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Role configuration sections */}
          {ROLES.map(({ key, labelKey }) => {
            const [config, setConfig] = getConfigState(key);
            const isExpanded = expandedSections[key];
            const configuredModels = config.llm_provider ? providers[config.llm_provider] || [] : [];
            const modelsForProvider = config.llm_model
              ? Array.from(new Set([config.llm_model, ...configuredModels]))
              : configuredModels;

            return (
              <div key={key} className="border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden">
                <button
                  onClick={() => toggleSection(key)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                    {t(labelKey)}
                  </span>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-zinc-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-zinc-400" />
                  )}
                </button>

                {isExpanded && (
                  <div className="p-4 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      {/* Provider */}
                      <div>
                        <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                          {t('missions.provider')}
                        </label>
                        <select
                          value={config.llm_provider}
                          onChange={(e) => {
                            const provider = e.target.value;
                            const models = providers[provider] || [];
                            setConfig((prev) => ({
                              ...prev,
                              llm_provider: provider,
                              llm_model: models[0] || '',
                            }));
                          }}
                          className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none dark:text-zinc-200"
                        >
                          <option value="">{t('missions.selectProvider')}</option>
                          {providerNames.map((p) => (
                            <option key={p} value={p}>{p}</option>
                          ))}
                        </select>
                      </div>

                      {/* Model */}
                      <div>
                        <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                          {t('missions.model')}
                        </label>
                        <select
                          value={config.llm_model}
                          onChange={(e) => setConfig((prev) => ({ ...prev, llm_model: e.target.value }))}
                          disabled={!config.llm_provider}
                          className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none disabled:opacity-50 dark:text-zinc-200"
                        >
                          <option value="">{t('missions.selectModel')}</option>
                          {modelsForProvider.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      {/* Temperature */}
                      <div>
                        <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                          {t('missions.temperature')}: {config.temperature.toFixed(1)}
                        </label>
                        <input
                          type="range"
                          min={0}
                          max={2}
                          step={0.1}
                          value={config.temperature}
                          onChange={(e) => setConfig((prev) => ({ ...prev, temperature: parseFloat(e.target.value) }))}
                          className="w-full accent-emerald-500"
                        />
                        <div className="flex justify-between text-[10px] text-zinc-400 mt-0.5">
                          <span>0.0</span>
                          <span>1.0</span>
                          <span>2.0</span>
                        </div>
                      </div>

                      {/* Max Tokens */}
                      <div>
                        <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                          {t('missions.maxTokens')}
                        </label>
                        <input
                          type="number"
                          min={1024}
                          max={32768}
                          step={1024}
                          value={config.max_tokens}
                          onChange={(e) => setConfig((prev) => ({ ...prev, max_tokens: parseInt(e.target.value) || 4096 }))}
                          className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none dark:text-zinc-200"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* Execution defaults */}
          <div className="border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden">
            <button
              onClick={() => toggleSection('execution')}
              className="w-full flex items-center justify-between px-4 py-3 bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                {t('missions.executionDefaults')}
              </span>
              {expandedSections.execution ? (
                <ChevronUp className="w-4 h-4 text-zinc-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-zinc-400" />
              )}
            </button>

            {expandedSections.execution && (
              <div className="p-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                      {t('missions.maxRetries')}
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={10}
                      value={executionConfig.max_retries}
                      onChange={(e) => setExecutionConfig((prev) => ({ ...prev, max_retries: parseInt(e.target.value) || 0 }))}
                      className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none dark:text-zinc-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                      {t('missions.taskTimeout')}
                    </label>
                    <input
                      type="number"
                      min={60}
                      max={3600}
                      step={60}
                      value={executionConfig.task_timeout_s}
                      onChange={(e) => setExecutionConfig((prev) => ({ ...prev, task_timeout_s: parseInt(e.target.value) || 600 }))}
                      className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none dark:text-zinc-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                      {t('missions.maxReworkCycles')}
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={5}
                      value={executionConfig.max_rework_cycles}
                      onChange={(e) => setExecutionConfig((prev) => ({ ...prev, max_rework_cycles: parseInt(e.target.value) || 0 }))}
                      className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none dark:text-zinc-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                      {t('missions.maxConcurrentTasks')}
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={executionConfig.max_concurrent_tasks}
                      onChange={(e) => setExecutionConfig((prev) => ({ ...prev, max_concurrent_tasks: parseInt(e.target.value) || 1 }))}
                      className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500/30 outline-none dark:text-zinc-200"
                    />
                  </div>
                  <div className="col-span-2 flex items-center gap-3">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={executionConfig.network_access}
                        onChange={(e) => setExecutionConfig((prev) => ({ ...prev, network_access: e.target.checked }))}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-zinc-200 dark:bg-zinc-700 peer-focus:ring-2 peer-focus:ring-emerald-500/30 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500" />
                    </label>
                    <span className="text-xs font-medium text-zinc-500">
                      {t('missions.networkAccess')}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-200 dark:border-zinc-700">
          <div className={`text-xs ${saveError ? 'text-red-600' : 'text-emerald-600'}`}>
            {saveError || (saveSuccess ? t('missions.settingsSaved') : null)}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2.5 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-xl transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || isLoadingProviders}
              className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {isSaving ? t('missions.saving') : t('missions.saveSettings')}
            </button>
          </div>
        </div>
      </ModalPanel>
    </div>
  );
};
