import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  KeyRound,
  Loader2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Users,
} from 'lucide-react';
import { llmApi } from '@/api/llm';
import { skillsApi } from '@/api/skills';
import { platformApi } from '@/api/platform';
import { useAuthStore } from '@/stores';

type PlatformTab = 'experience' | 'llm' | 'envVars' | 'projectExecution';

interface BusinessBaselineSettingsProps {
  onOpenTab: (tab: PlatformTab) => void;
}

interface BaselineSummary {
  providerCount: number;
  healthyProviderCount: number;
  hasDefaultProvider: boolean;
  envVarCount: number;
  hasProjectExecutionPolicy: boolean;
  hasUiExperiencePolicy: boolean;
  defaultMotionPreference: string;
  emergencyMotionDisabled: boolean;
}

const INITIAL_SUMMARY: BaselineSummary = {
  providerCount: 0,
  healthyProviderCount: 0,
  hasDefaultProvider: false,
  envVarCount: 0,
  hasProjectExecutionPolicy: false,
  hasUiExperiencePolicy: false,
  defaultMotionPreference: 'auto',
  emergencyMotionDisabled: false,
};

export const BusinessBaselineSettings = ({ onOpenTab }: BusinessBaselineSettingsProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<BaselineSummary>(INITIAL_SUMMARY);

  const canManageAccess = ['admin', 'manager'].includes(user?.role || '');
  const translatedMotionPreference = t(
    `settings.experience.option.${summary.defaultMotionPreference}`,
    summary.defaultMotionPreference,
  );
  const translatedEmergencyState = summary.emergencyMotionDisabled
    ? t('settings.enabled', 'Enabled')
    : t('settings.disabled', 'Disabled');

  useEffect(() => {
    let active = true;

    const loadBaseline = async () => {
      setLoading(true);
      try {
        const [llmResult, envResult, experienceResult, projectExecutionResult] =
          await Promise.allSettled([
            llmApi.getProvidersConfig(),
            skillsApi.listEnvVars(),
            platformApi.getUiExperience(),
            platformApi.getProjectExecutionSettings(),
          ]);

        if (!active) return;

        const nextSummary: BaselineSummary = { ...INITIAL_SUMMARY };

        if (llmResult.status === 'fulfilled') {
          const providers = Object.values(llmResult.value.providers || {});
          nextSummary.providerCount = providers.length;
          nextSummary.healthyProviderCount = providers.filter((provider) => provider.healthy).length;
          nextSummary.hasDefaultProvider = Boolean(llmResult.value.default_provider);
        }

        if (envResult.status === 'fulfilled') {
          nextSummary.envVarCount = envResult.value.length;
        }


        if (experienceResult.status === 'fulfilled') {
          nextSummary.hasUiExperiencePolicy = true;
          nextSummary.defaultMotionPreference =
            experienceResult.value.default_motion_preference;
          nextSummary.emergencyMotionDisabled =
            experienceResult.value.emergency_disable_motion;
        }

        if (projectExecutionResult.status === 'fulfilled') {
          nextSummary.hasProjectExecutionPolicy = Boolean(
            projectExecutionResult.value.default_launch_command_template?.trim(),
          );
        }

        setSummary(nextSummary);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void loadBaseline();

    return () => {
      active = false;
    };
  }, []);

  const statusIcon = (ok: boolean) =>
    ok ? (
      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
    ) : (
      <AlertCircle className="w-4 h-4 text-amber-500" />
    );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {t('settings.baseline.title', 'Business Platform Baseline')}
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
          {t(
            'settings.baseline.subtitle',
            'Validate and complete the core platform setup before scaling collaboration.'
          )}
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>{t('settings.baseline.loading', 'Checking baseline configuration...')}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 bg-white dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-emerald-500" />
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                {t('settings.baseline.uiExperience', 'UI Motion Policy')}
              </p>
            </div>
            {statusIcon(summary.hasUiExperiencePolicy)}
          </div>
          <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
            {t(
              'settings.baseline.uiExperienceSummary',
              'Default {{preference}} · emergency {{status}}',
              {
                preference: translatedMotionPreference,
                status: translatedEmergencyState,
              },
            )}
          </p>
          <button
            onClick={() => onOpenTab('experience')}
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            {t('settings.baseline.configure', 'Configure')}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 bg-white dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-emerald-500" />
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                {t('settings.baseline.llm', 'LLM Providers')}
              </p>
            </div>
            {statusIcon(
              summary.providerCount > 0 && summary.healthyProviderCount > 0 && summary.hasDefaultProvider
            )}
          </div>
          <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
            {t('settings.baseline.llmSummary', '{{healthy}}/{{total}} healthy, default provider ready', {
              healthy: summary.healthyProviderCount,
              total: summary.providerCount,
            })}
          </p>
          <button
            onClick={() => onOpenTab('llm')}
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            {t('settings.baseline.review', 'Review')}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 bg-white dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-emerald-500" />
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                {t('settings.baseline.secrets', 'Skill Secrets')}
              </p>
            </div>
            {statusIcon(summary.envVarCount > 0)}
          </div>
          <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
            {t('settings.baseline.secretsSummary', '{{count}} environment variables configured', {
              count: summary.envVarCount,
            })}
          </p>
          <button
            onClick={() => onOpenTab('envVars')}
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            {t('settings.baseline.manage', 'Manage')}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 bg-white dark:bg-zinc-900/40">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-emerald-500" />
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                {t('settings.baseline.projectExecution', 'Project Execution')}
              </p>
            </div>
            {statusIcon(summary.hasProjectExecutionPolicy)}
          </div>
          <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
            {t(
              'settings.baseline.projectExecutionSummary',
              'Project execution defaults are {{status}}',
              { status: summary.hasProjectExecutionPolicy ? t('settings.enabled', 'Enabled') : t('settings.disabled', 'Disabled') }
            )}
          </p>
          <button
            onClick={() => onOpenTab('projectExecution')}
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            {t('settings.baseline.configure', 'Configure')}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-5 bg-zinc-50/70 dark:bg-zinc-800/30">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {t('settings.baseline.governance', 'Access Governance')}
          </h3>
        </div>
        <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
          {t(
            'settings.baseline.governanceSubtitle',
            'Keep role assignments and department responsibilities aligned with your org chart.'
          )}
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            onClick={() => navigate('/user-management')}
            disabled={!canManageAccess}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-600 text-sm text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Users className="w-4 h-4" />
            {t('settings.baseline.userManagement', 'User Management')}
          </button>
          <button
            onClick={() => navigate('/role-management')}
            disabled={!canManageAccess}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-600 text-sm text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ShieldCheck className="w-4 h-4" />
            {t('settings.baseline.roleManagement', 'Role Management')}
          </button>
        </div>
        {!canManageAccess && (
          <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
            {t(
              'settings.baseline.governancePermissionHint',
              'Only admin or manager roles can update platform access policies.'
            )}
          </p>
        )}
      </div>
    </div>
  );
};
