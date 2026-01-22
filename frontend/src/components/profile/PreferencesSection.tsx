import { Monitor, Sun, Moon, Globe } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useThemeStore } from '../../stores/themeStore';
import { usePreferencesStore } from '../../stores/preferencesStore';

export const PreferencesSection = () => {
  const { theme, setTheme } = useThemeStore();
  const { language, setLanguage } = usePreferencesStore();

  const themes = [
    { id: 'light' as const, label: 'Light', icon: Sun },
    { id: 'dark' as const, label: 'Dark', icon: Moon },
    { id: 'system' as const, label: 'System', icon: Monitor },
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
              <h2 className="text-xl font-semibold text-white">Theme</h2>
              <p className="text-sm text-gray-400 mt-1">
                Choose your preferred color scheme
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
                  onClick={() => setTheme(themeOption.id)}
                  className={`p-4 rounded-lg border-2 transition-all ${
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
              <h2 className="text-xl font-semibold text-white">Language</h2>
              <p className="text-sm text-gray-400 mt-1">
                Select your preferred language
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {languages.map((lang) => {
              const isActive = language === lang.id;
              
              return (
                <button
                  key={lang.id}
                  onClick={() => setLanguage(lang.id)}
                  className={`p-4 rounded-lg border-2 transition-all ${
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
