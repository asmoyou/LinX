import { Monitor, Sun, Moon, Globe } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useThemeStore } from '../../stores/themeStore';
import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { usersApi } from '@/api/users';
import toast from 'react-hot-toast';

interface UserPreferences {
  language: string;
  theme: string;
  sidebar_collapsed: boolean;
  dashboard_layout: string;
  notifications_enabled: boolean;
  sound_enabled: boolean;
  auto_refresh: boolean;
  refresh_interval: number;
}

export const PreferencesSection = () => {
  const { theme, setTheme } = useThemeStore();
  const { i18n, t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);

  // Load preferences from backend on mount
  useEffect(() => {
    loadPreferences();
  }, []);

  const loadPreferences = async () => {
    try {
      const prefs = await usersApi.getPreferences();
      
      // Apply loaded preferences
      if (prefs.language && prefs.language !== i18n.language) {
        i18n.changeLanguage(prefs.language);
      }
      if (prefs.theme && prefs.theme !== theme) {
        setTheme(prefs.theme as 'light' | 'dark' | 'system');
      }
    } catch (error) {
      console.error('Failed to load preferences:', error);
      // Don't show error toast on initial load, use defaults
    }
  };

  const savePreferences = async (updates: Partial<UserPreferences>) => {
    setIsLoading(true);
    try {
      // Get current preferences
      const currentPrefs: UserPreferences = {
        language: i18n.language,
        theme: theme,
        sidebar_collapsed: false,
        dashboard_layout: 'default',
        notifications_enabled: true,
        sound_enabled: false,
        auto_refresh: true,
        refresh_interval: 30,
      };

      // Merge with updates
      const newPrefs = { ...currentPrefs, ...updates };

      // Save to backend using usersApi
      await usersApi.updatePreferences(newPrefs);
      
      toast.success(t('profileSettings.preferences.preferencesSaved'));
    } catch (error) {
      console.error('Failed to save preferences:', error);
      toast.error(t('profileSettings.preferences.preferencesSaveFailed'));
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

  const themes = [
    { id: 'light' as const, label: t('profileSettings.preferences.theme.light'), icon: Sun },
    { id: 'dark' as const, label: t('profileSettings.preferences.theme.dark'), icon: Moon },
    { id: 'system' as const, label: t('profileSettings.preferences.theme.system'), icon: Monitor },
  ];

  const languages = [
    { id: 'en' as const, label: 'English', flag: '🇺🇸' },
    { id: 'zh' as const, label: '中文', flag: '🇨🇳' },
  ];

  return (
    <div className="space-y-6">
      {/* Theme Preferences */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Monitor className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-white">{t('profileSettings.preferences.theme.title')}</h2>
              <p className="text-sm text-gray-400 mt-1">
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
                      : 'border-white/10 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <Icon className={`w-8 h-8 mx-auto mb-2 ${
                    isActive ? 'text-emerald-400' : 'text-gray-400'
                  }`} />
                  <p className={`text-sm font-medium ${
                    isActive ? 'text-emerald-400' : 'text-gray-300'
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
              <h2 className="text-xl font-semibold text-white">{t('profileSettings.preferences.language.title')}</h2>
              <p className="text-sm text-gray-400 mt-1">
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
                      : 'border-white/10 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="text-3xl mb-2">{lang.flag}</div>
                  <p className={`text-sm font-medium ${
                    isActive ? 'text-emerald-400' : 'text-gray-300'
                  }`}>
                    {lang.label}
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
