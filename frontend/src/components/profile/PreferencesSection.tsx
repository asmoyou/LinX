import { Gauge, Globe, Monitor, Moon, PauseCircle, SlidersHorizontal, Sparkles, Sun } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useThemeStore } from '../../stores/themeStore';
import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { usersApi } from '@/api/users';
import { usePreferencesStore } from '@/stores';
import toast from 'react-hot-toast';
import { useMotionPolicy, type MotionPreference } from '@/motion';

interface UserPreferences {
  language: string;
  theme: string;
  motion_preference: MotionPreference;
  sidebar_collapsed: boolean;
  dashboard_layout: string;
  notifications_enabled: boolean;
  sound_enabled: boolean;
  auto_refresh: boolean;
  refresh_interval: number;
}

export const PreferencesSection = () => {
  const { theme, setTheme } = useThemeStore();
  const { updatePreferences: updatePreferenceStore, ...storedPreferences } = usePreferencesStore();
  const { i18n, t } = useTranslation();
  const {
    effectiveTier,
    hasUserPreferenceOverride,
    platformSettings,
    setUserPreference,
    source,
  } = useMotionPolicy();
  const [isLoading, setIsLoading] = useState(false);
  const [serverPreferences, setServerPreferences] = useState<UserPreferences | null>(null);

  // Load preferences from backend on mount
  useEffect(() => {
    loadPreferences();
  }, []);

  const loadPreferences = async () => {
    try {
      const prefs = await usersApi.getPreferences();
      setServerPreferences(prefs);
      
      // Apply loaded preferences
      if (prefs.language && prefs.language !== i18n.language) {
        i18n.changeLanguage(prefs.language);
      }
      if (prefs.theme && prefs.theme !== theme) {
        setTheme(prefs.theme as 'light' | 'dark' | 'system');
      }
      updatePreferenceStore({
        language: prefs.language as 'en' | 'zh',
        motionPreference: prefs.motion_preference,
        sidebarCollapsed: prefs.sidebar_collapsed,
        dashboardLayout: prefs.dashboard_layout as 'default' | 'compact' | 'detailed',
        notificationsEnabled: prefs.notifications_enabled,
        soundEnabled: prefs.sound_enabled,
        autoRefresh: prefs.auto_refresh,
        refreshInterval: prefs.refresh_interval,
      });
    } catch (error) {
      console.error('Failed to load preferences:', error);
      // Don't show error toast on initial load, use defaults
    }
  };

  const savePreferences = async (updates: Partial<UserPreferences>) => {
    setIsLoading(true);
    try {
      const currentPrefs: UserPreferences = serverPreferences ?? {
        language: (storedPreferences.language || i18n.language) as string,
        theme,
        motion_preference: storedPreferences.motionPreference,
        sidebar_collapsed: storedPreferences.sidebarCollapsed,
        dashboard_layout: storedPreferences.dashboardLayout,
        notifications_enabled: storedPreferences.notificationsEnabled,
        sound_enabled: storedPreferences.soundEnabled,
        auto_refresh: storedPreferences.autoRefresh,
        refresh_interval: storedPreferences.refreshInterval,
      };

      // Merge with updates
      const newPrefs = { ...currentPrefs, ...updates };

      // Save to backend using usersApi
      const savedPreferences = await usersApi.updatePreferences(newPrefs);
      setServerPreferences(savedPreferences);
      updatePreferenceStore({
        language: savedPreferences.language as 'en' | 'zh',
        motionPreference: savedPreferences.motion_preference,
        sidebarCollapsed: savedPreferences.sidebar_collapsed,
        dashboardLayout: savedPreferences.dashboard_layout as 'default' | 'compact' | 'detailed',
        notificationsEnabled: savedPreferences.notifications_enabled,
        soundEnabled: savedPreferences.sound_enabled,
        autoRefresh: savedPreferences.auto_refresh,
        refreshInterval: savedPreferences.refresh_interval,
      });
      
      toast.success(t('profileSettings.preferences.preferencesSaved'));
      return savedPreferences;
    } catch (error) {
      console.error('Failed to save preferences:', error);
      toast.error(t('profileSettings.preferences.preferencesSaveFailed'));
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  const handleThemeChange = async (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme);
    await savePreferences({ theme: newTheme });
  };

  const handleLanguageChange = async (newLanguage: 'en' | 'zh') => {
    i18n.changeLanguage(newLanguage);
    await savePreferences({ language: newLanguage });
  };

  const handleMotionChange = async (motionPreference: MotionPreference) => {
    const savedPreferences = await savePreferences({ motion_preference: motionPreference });
    if (savedPreferences) {
      setUserPreference(savedPreferences.motion_preference, true);
    }
  };

  const themes = [
    { id: 'light' as const, label: t('profileSettings.preferences.theme.light'), icon: Sun },
    { id: 'dark' as const, label: t('profileSettings.preferences.theme.dark'), icon: Moon },
    { id: 'system' as const, label: t('profileSettings.preferences.theme.system'), icon: Monitor },
  ];

  const languages = [
    { id: 'en' as const, label: 'English', flag: '🇺🇸' },
    { id: 'zh' as const, label: '中文', flag: '🇨🇳' },
  ];

  const motionOptions: Array<{
    id: MotionPreference;
    label: string;
    icon: typeof Sparkles;
    description: string;
  }> = [
    {
      id: 'auto',
      label: t('profileSettings.preferences.motion.auto', 'Auto'),
      icon: Sparkles,
      description: t(
        'profileSettings.preferences.motion.autoDescription',
        'Adapt based on the platform policy and runtime performance.',
      ),
    },
    {
      id: 'full',
      label: t('profileSettings.preferences.motion.full', 'Full'),
      icon: Gauge,
      description: t(
        'profileSettings.preferences.motion.fullDescription',
        'Prefer richer transitions whenever accessibility allows them.',
      ),
    },
    {
      id: 'reduced',
      label: t('profileSettings.preferences.motion.reduced', 'Reduced'),
      icon: SlidersHorizontal,
      description: t(
        'profileSettings.preferences.motion.reducedDescription',
        'Use lightweight fades and lower-cost visuals.',
      ),
    },
    {
      id: 'off',
      label: t('profileSettings.preferences.motion.off', 'Off'),
      icon: PauseCircle,
      description: t(
        'profileSettings.preferences.motion.offDescription',
        'Disable decorative motion and keep the UI static.',
      ),
    },
  ];

  const selectedMotionPreference = hasUserPreferenceOverride
    ? storedPreferences.motionPreference
    : platformSettings.default_motion_preference;

  const motionSourceLabel =
    source === 'user_preference'
      ? t('profileSettings.preferences.motion.source.user', 'User preference')
      : source === 'system_reduced_motion'
        ? t('profileSettings.preferences.motion.source.system', 'System reduced motion')
        : source === 'emergency_disable_motion'
          ? t('profileSettings.preferences.motion.source.emergency', 'Emergency override')
          : t('profileSettings.preferences.motion.source.platform', 'Platform default');

  return (
    <div className="space-y-6">
      {/* Theme Preferences */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Monitor className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.preferences.theme.title')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.preferences.theme.subtitle')}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {themes.map((themeOption) => {
              const Icon = themeOption.icon;
              const isActive = theme === themeOption.id;
              
              return (
                <button
                  key={themeOption.id}
                  onClick={() => handleThemeChange(themeOption.id)}
                  disabled={isLoading}
                  className={`p-4 rounded-lg border-2 transition-all disabled:opacity-50 ${
                    isActive
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-white/5 hover:border-zinc-300 dark:hover:border-white/20'
                  }`}
                >
                  <Icon className={`w-8 h-8 mx-auto mb-2 ${
                    isActive ? 'text-emerald-400' : 'text-zinc-500 dark:text-zinc-400'
                  }`} />
                  <p className={`text-sm font-medium ${
                    isActive ? 'text-emerald-400' : 'text-zinc-700 dark:text-zinc-300'
                  }`}>
                    {themeOption.label}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      </GlassPanel>

      {/* Language Preferences */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Globe className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.preferences.language.title')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.preferences.language.subtitle')}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {languages.map((lang) => {
              const isActive = i18n.language === lang.id;
              
              return (
                <button
                  key={lang.id}
                  onClick={() => handleLanguageChange(lang.id)}
                  disabled={isLoading}
                  className={`p-4 rounded-lg border-2 transition-all disabled:opacity-50 ${
                    isActive
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-white/5 hover:border-zinc-300 dark:hover:border-white/20'
                  }`}
                >
                  <div className="text-3xl mb-2">{lang.flag}</div>
                  <p className={`text-sm font-medium ${
                    isActive ? 'text-emerald-400' : 'text-zinc-700 dark:text-zinc-300'
                  }`}>
                    {lang.label}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      </GlassPanel>

      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.preferences.motion.title', 'Motion Preferences')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t(
                  'profileSettings.preferences.motion.subtitle',
                  'Choose how aggressively LinX animates the interface on this account.',
                )}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-900/40">
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
              {t('profileSettings.preferences.motion.current', 'Current effective tier')}: {effectiveTier}
            </p>
            <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
              {t('profileSettings.preferences.motion.sourceLabel', 'Source')}: {motionSourceLabel}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {motionOptions.map((option) => {
              const Icon = option.icon;
              const isActive = selectedMotionPreference === option.id;

              return (
                <button
                  key={option.id}
                  onClick={() => void handleMotionChange(option.id)}
                  disabled={isLoading}
                  className={`p-4 rounded-lg border-2 text-left transition-all disabled:opacity-50 ${
                    isActive
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-white/5 hover:border-zinc-300 dark:hover:border-white/20'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon
                      className={`w-5 h-5 ${
                        isActive ? 'text-emerald-400' : 'text-zinc-500 dark:text-zinc-400'
                      }`}
                    />
                    <p
                      className={`text-sm font-medium ${
                        isActive ? 'text-emerald-400' : 'text-zinc-700 dark:text-zinc-300'
                      }`}
                    >
                      {option.label}
                    </p>
                  </div>
                  <p className="mt-3 text-xs text-zinc-600 dark:text-zinc-400">
                    {option.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      </GlassPanel>
    </div>
  );
};
