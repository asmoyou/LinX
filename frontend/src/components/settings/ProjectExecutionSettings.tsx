import { useEffect, useState } from 'react';
import { Loader2, ShieldAlert, SlidersHorizontal } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';

import { platformApi, type ProjectExecutionPlatformSettings } from '@/api/platform';
import { GlassPanel } from '@/components/GlassPanel';
import { useAuthStore, useUserStore } from '@/stores';

const EMPTY_SETTINGS: ProjectExecutionPlatformSettings = {
  default_launch_command_template: '',
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

  useEffect(() => {
    if (!canManageProjectExecution) {
      setIsLoading(false);
      return;
    }

    let active = true;
    const loadSettings = async () => {
      setIsLoading(true);
      try {
        const response = await platformApi.getProjectExecutionSettings();
        if (!active) {
          return;
        }
        setSettings(response);
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

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const saved = await platformApi.updateProjectExecutionSettings({
        default_launch_command_template:
          settings.default_launch_command_template.trim(),
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
            'Define the platform default launch command for external runtimes. External agents inherit this value unless they set an agent-level override.',
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
                  'settings.projectExecution.defaultLaunchCommand',
                  'Default Launch Command Template',
                )}
              </p>
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                {t(
                  'settings.projectExecution.defaultLaunchCommandHelp',
                  'Leave blank only if every external agent will define its own override. When both levels are empty, the runtime stays installed but cannot accept work.',
                )}
              </p>
            </div>
          </div>

          <textarea
            value={settings.default_launch_command_template}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                default_launch_command_template: event.target.value,
              }))
            }
            rows={6}
            className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            placeholder={t(
              'settings.projectExecution.defaultLaunchCommandPlaceholder',
              'Example: codex exec --skip-git-repo-check --sandbox danger-full-access --cd "$LINX_WORKSPACE_ROOT" "$LINX_AGENT_PROMPT"',
            )}
          />

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
