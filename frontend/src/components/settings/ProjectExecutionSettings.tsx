import { useEffect, useMemo, useState } from 'react';
import { Loader2, ShieldAlert, SlidersHorizontal } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';

import { llmApi, type LLMConfig, type ProviderModelsMetadata } from '@/api/llm';
import { platformApi, type ProjectExecutionPlatformSettings } from '@/api/platform';
import { GlassPanel } from '@/components/GlassPanel';
import { useAuthStore, useUserStore } from '@/stores';

const EMPTY_SETTINGS: ProjectExecutionPlatformSettings = {
  planner_provider: '',
  planner_model: '',
  planner_temperature: 0.2,
  planner_max_tokens: 4000,
};

const isGenerationModel = (metadata?: ProviderModelsMetadata, modelName?: string): boolean => {
  if (!metadata || !modelName) return true;
  const model = metadata.models[modelName];
  if (!model) return true;
  return !['embedding', 'rerank', 'audio', 'asr'].includes(String(model.model_type || '').toLowerCase());
};

export const ProjectExecutionSettings = () => {
  const { t } = useTranslation();
  const authRole = useAuthStore((state) => state.user?.role);
  const profileRole = useUserStore((state) => state.profile?.role);
  const effectiveRole = (profileRole ?? authRole ?? '').toLowerCase();
  const canManageProjectExecution =
    effectiveRole === 'admin' || effectiveRole === 'manager';
  const [settings, setSettings] =
    useState<ProjectExecutionPlatformSettings>(EMPTY_SETTINGS);
  const [isLoading, setIsLoading] = useState(canManageProjectExecution);
  const [isSaving, setIsSaving] = useState(false);
  const [providersConfig, setProvidersConfig] = useState<LLMConfig | null>(null);
  const [providerMetadata, setProviderMetadata] = useState<Record<string, ProviderModelsMetadata>>({});

  useEffect(() => {
    if (!canManageProjectExecution) {
      setIsLoading(false);
      return;
    }

    let active = true;
    const loadSettings = async () => {
      setIsLoading(true);
      try {
        const [response, llmConfig] = await Promise.all([
          platformApi.getProjectExecutionSettings(),
          llmApi.getProvidersConfig(),
        ]);
        if (!active) {
          return;
        }
        setSettings(response);
        setProvidersConfig(llmConfig);
      } catch (error: any) {
        if (!active) {
          return;
        }
        toast.error(
          error?.response?.data?.detail ||
            t(
              'settings.projectExecution.loadFailed',
              'Failed to load project execution defaults.',
            ),
        );
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    void loadSettings();
    return () => {
      active = false;
    };
  }, [canManageProjectExecution, t]);

  useEffect(() => {
    if (!settings.planner_provider || providerMetadata[settings.planner_provider]) {
      return;
    }

    let active = true;
    const loadMetadata = async () => {
      try {
        const metadata = await llmApi.getProviderModelsMetadata(settings.planner_provider);
        if (active) {
          setProviderMetadata((current) => ({
            ...current,
            [settings.planner_provider]: metadata,
          }));
        }
      } catch {
        // Best-effort only.
      }
    };

    void loadMetadata();
    return () => {
      active = false;
    };
  }, [providerMetadata, settings.planner_provider]);

  const plannerProviders = Object.entries(providersConfig?.providers || {})
    .filter(([, provider]) => provider.available_models.length > 0)
    .map(([name]) => name);

  const plannerModels = useMemo(() => {
    if (!settings.planner_provider || !providersConfig?.providers[settings.planner_provider]) {
      return [];
    }
    const availableModels = providersConfig.providers[settings.planner_provider].available_models || [];
    const metadata = providerMetadata[settings.planner_provider];
    return availableModels.filter((modelName) => isGenerationModel(metadata, modelName));
  }, [providerMetadata, providersConfig, settings.planner_provider]);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const saved = await platformApi.updateProjectExecutionSettings({
        planner_provider: settings.planner_provider.trim(),
        planner_model: settings.planner_model.trim(),
        planner_temperature: settings.planner_temperature,
        planner_max_tokens: settings.planner_max_tokens,
      });
      setSettings(saved);
      toast.success(
        t(
          'settings.projectExecution.saved',
          'Project execution defaults saved.',
        ),
      );
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          t(
            'settings.projectExecution.saveFailed',
            'Failed to save project execution defaults.',
          ),
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (!canManageProjectExecution) {
    return (
      <GlassPanel className="p-6">
        <div className="flex items-start gap-3">
          <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-500" />
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('settings.projectExecution.title', 'Project Execution')}
            </h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {t(
                'settings.projectExecution.permissionHint',
                'Only admin and manager roles can manage platform launch defaults for external runtimes.',
              )}
            </p>
          </div>
        </div>
      </GlassPanel>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {t('settings.projectExecution.title', 'Project Execution')}
        </h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t(
            'settings.projectExecution.subtitle',
            'Manage project planning defaults. External Runtime Hosts now use LinX native remote execution instead of a user-configured launch command template.',
          )}
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>
            {t(
              'settings.projectExecution.loading',
              'Loading project execution defaults...',
            )}
          </span>
        </div>
      ) : null}

      <GlassPanel className="p-6">
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-zinc-200 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/40">
            <SlidersHorizontal className="mt-0.5 h-5 w-5 text-indigo-500" />
            <div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                {t(
                  'settings.projectExecution.nativeRuntimeExecution',
                  'Native Runtime Execution',
                )}
              </p>
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                {t(
                  'settings.projectExecution.nativeRuntimeExecutionHelp',
                  'Runtime Hosts no longer require a user-managed launch command. The native remote executor is bundled with the Runtime Host and updated from the control plane.',
                )}
              </p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 block">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('settings.projectExecution.plannerProvider', 'Planner Provider')}
              </span>
              <select
                value={settings.planner_provider}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    planner_provider: event.target.value,
                    planner_model:
                      event.target.value === current.planner_provider ? current.planner_model : '',
                  }))
                }
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              >
                <option value="">
                  {t('settings.projectExecution.plannerProviderDefault', 'Use platform default provider')}
                </option>
                {plannerProviders.map((providerName) => (
                  <option key={providerName} value={providerName}>
                    {providerName}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-2 block">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('settings.projectExecution.plannerModel', 'Planner Model')}
              </span>
              <select
                value={settings.planner_model}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    planner_model: event.target.value,
                  }))
                }
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                disabled={!settings.planner_provider}
              >
                <option value="">
                  {t('settings.projectExecution.plannerModelDefault', 'Use provider default chat model')}
                </option>
                {plannerModels.map((modelName) => (
                  <option key={modelName} value={modelName}>
                    {modelName}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 block">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('settings.projectExecution.plannerTemperature', 'Planner Temperature')}
              </span>
              <input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={settings.planner_temperature}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    planner_temperature: Number(event.target.value),
                  }))
                }
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>

            <label className="space-y-2 block">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('settings.projectExecution.plannerMaxTokens', 'Planner Max Tokens')}
              </span>
              <input
                type="number"
                min={1}
                step={1}
                value={settings.planner_max_tokens}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    planner_max_tokens: Number(event.target.value),
                  }))
                }
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={isLoading || isSaving}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSaving
                ? t('settings.projectExecution.saving', 'Saving...')
                : t('settings.projectExecution.saveAction', 'Save Defaults')}
            </button>
          </div>
        </div>
      </GlassPanel>
    </div>
  );
};
