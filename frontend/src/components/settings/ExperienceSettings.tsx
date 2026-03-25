import { useEffect, useMemo, useState } from 'react';
import { Gauge, Loader2, PauseCircle, ShieldAlert, SlidersHorizontal, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';

import { platformApi } from '@/api';
import { GlassPanel } from '@/components/GlassPanel';
import { useMotionPolicy, type MotionPreference, type UiExperienceSettings } from '@/motion';
import { useAuthStore, useUserStore } from '@/stores';

const MOTION_OPTIONS: Array<{
  id: MotionPreference;
  label: string;
  description: string;
  icon: typeof Sparkles;
}> = [
  {
    id: 'auto',
    label: 'Auto',
    description: 'Start from device class and allow runtime downgrades.',
    icon: Sparkles,
  },
  {
    id: 'full',
    label: 'Full',
    description: 'Keep the richest motion profile when accessibility allows it.',
    icon: Gauge,
  },
  {
    id: 'reduced',
    label: 'Reduced',
    description: 'Prefer lightweight fades and lower-cost visual effects.',
    icon: SlidersHorizontal,
  },
  {
    id: 'off',
    label: 'Off',
    description: 'Disable decorative motion and keep the UI static.',
    icon: PauseCircle,
  },
];

export const ExperienceSettings = () => {
  const { t } = useTranslation();
  const authRole = useAuthStore((state) => state.user?.role);
  const profileRole = useUserStore((state) => state.profile?.role);
  const effectiveRole = (profileRole ?? authRole ?? '').toLowerCase();
  const canManageExperience = effectiveRole === 'admin' || effectiveRole === 'manager';
  const {
    effectiveTier,
    source,
    platformSettings,
    setPlatformSettings,
  } = useMotionPolicy();

  const [settings, setSettings] = useState<UiExperienceSettings>(platformSettings);
  const [isLoading, setIsLoading] = useState(canManageExperience);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!canManageExperience) {
      setIsLoading(false);
      return;
    }

    let isActive = true;

    const loadSettings = async () => {
      setIsLoading(true);
      try {
        const response = await platformApi.getUiExperience();
        if (!isActive) {
          return;
        }

        setSettings(response);
        setPlatformSettings(response);
      } catch (error: any) {
        if (!isActive) {
          return;
        }

        toast.error(
          error?.response?.data?.detail ||
            t(
              'settings.experience.loadFailed',
              'Failed to load platform UI experience settings.',
            ),
        );
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    void loadSettings();

    return () => {
      isActive = false;
    };
  }, [canManageExperience, setPlatformSettings, t]);

  useEffect(() => {
    setSettings(platformSettings);
  }, [platformSettings]);

  const effectiveSummary = useMemo(
    () => {
      const sourceLabel = (() => {
        switch (source) {
          case 'user_preference':
            return t('settings.experience.source.userPreference', 'User preference');
          case 'system_reduced_motion':
            return t('settings.experience.source.systemReducedMotion', 'System reduced motion');
          case 'emergency_disable_motion':
            return t('settings.experience.source.emergencyOverride', 'Emergency override');
          default:
            return t('settings.experience.source.platformDefault', 'Platform default');
        }
      })();

      return `${t('settings.experience.liveTier', 'Live tier')}: ${effectiveTier} · ${sourceLabel}`;
    },
    [effectiveTier, source, t],
  );

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const saved = await platformApi.updateUiExperience(settings);
      setSettings(saved);
      setPlatformSettings(saved);
      toast.success(
        t('settings.experience.saved', 'Platform UI experience settings saved.'),
      );
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          t('settings.experience.saveFailed', 'Failed to save platform UI experience settings.'),
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (!canManageExperience) {
    return (
      <GlassPanel className="p-6">
        <div className="flex items-start gap-3">
          <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-500" />
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('settings.experience.title', 'UI Experience')}
            </h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {t(
                'settings.experience.permissionHint',
                'Only admin and manager roles can manage the platform motion policy.',
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
          {t('settings.experience.title', 'UI Experience')}
        </h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t(
            'settings.experience.subtitle',
            'Define the default motion policy, emergency kill switch, and telemetry sampling rate.',
          )}
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>{t('settings.experience.loading', 'Loading UI experience settings...')}</span>
        </div>
      ) : null}

      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div>
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('settings.experience.defaultMotion', 'Default Motion Policy')}
            </p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{effectiveSummary}</p>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {MOTION_OPTIONS.map((option) => {
              const Icon = option.icon;
              const isActive = settings.default_motion_preference === option.id;

              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() =>
                    setSettings((currentSettings) => ({
                      ...currentSettings,
                      default_motion_preference: option.id,
                    }))
                  }
                  className={`rounded-xl border p-4 text-left transition-all ${
                    isActive
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900/40'
                  }`}
                >
                  <Icon
                    className={`h-5 w-5 ${
                      isActive ? 'text-emerald-500' : 'text-zinc-500 dark:text-zinc-400'
                    }`}
                  />
                  <p className="mt-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                    {t(`settings.experience.option.${option.id}`, option.label)}
                  </p>
                  <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                    {t(`settings.experience.option.${option.id}Description`, option.description)}
                  </p>
                </button>
              );
            })}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
            <label className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900/40">
              <div>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {t('settings.experience.emergencyDisable', 'Emergency Disable Motion')}
                </p>
                <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                  {t(
                    'settings.experience.emergencyDisableHint',
                    'Force the entire app into off mode without shipping a new frontend build.',
                  )}
                </p>
              </div>
              <input
                type="checkbox"
                checked={settings.emergency_disable_motion}
                onChange={(event) =>
                  setSettings((currentSettings) => ({
                    ...currentSettings,
                    emergency_disable_motion: event.target.checked,
                  }))
                }
                className="h-4 w-4 accent-emerald-500"
              />
            </label>

            <label className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900/40">
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {t('settings.experience.sampleRate', 'Telemetry Sample Rate')}
              </p>
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={settings.telemetry_sample_rate}
                onChange={(event) =>
                  setSettings((currentSettings) => ({
                    ...currentSettings,
                    telemetry_sample_rate: Math.min(
                      Math.max(Number(event.target.value || 0), 0),
                      1,
                    ),
                  }))
                }
                className="mt-3 w-full rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm text-zinc-900 outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
              <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
                {t(
                  'settings.experience.sampleRateHint',
                  'Use a value between 0 and 1. Example: 0.2 means 20% of authenticated sessions.',
                )}
              </p>
            </label>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={isSaving}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-600 disabled:opacity-60"
            >
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              <span>{t('settings.experience.save', 'Save UI Experience')}</span>
            </button>
          </div>
        </div>
      </GlassPanel>
    </div>
  );
};
