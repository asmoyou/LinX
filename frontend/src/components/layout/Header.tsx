import React from 'react';
import { useTranslation } from 'react-i18next';
import { Sun, Moon, Monitor, Bell, ShieldCheck } from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';

export const Header: React.FC = () => {
  const { i18n, t } = useTranslation();
  const { theme, setTheme } = useThemeStore();
  const [showNotifications, setShowNotifications] = React.useState(false);

  const themeOptions = [
    { id: 'light' as const, icon: Sun },
    { id: 'system' as const, icon: Monitor },
    { id: 'dark' as const, icon: Moon }
  ];

  return (
    <header
      className="h-16 border-b border-zinc-500/5 glass-panel flex items-center justify-between px-6 z-10"
      role="banner"
    >
      <div className="flex items-center gap-4">
        <div className="hidden md:flex items-center gap-2 text-[11px] font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-widest">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
          <span>
            {t('header.status', 'Status')}: <span className="text-emerald-600 dark:text-emerald-500">{t('header.optimal', 'Optimal')}</span>
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Theme & Lang Controls */}
        <div className="flex items-center gap-2">
          {/* Theme Selector */}
          <div className="flex items-center bg-zinc-500/5 rounded-full p-1 border border-zinc-500/5">
            {themeOptions.map((item) => (
              <button 
                key={item.id}
                onClick={() => setTheme(item.id)}
                className={`p-1.5 rounded-full transition-all duration-300 ${
                  theme === item.id 
                    ? 'bg-white dark:bg-zinc-700 shadow-sm text-emerald-600 dark:text-emerald-400' 
                    : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'
                }`}
                aria-label={`Set theme to ${item.id}`}
                title={item.id}
              >
                <item.icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>

          {/* Language Selector */}
          <div className="flex items-center bg-zinc-500/5 rounded-full p-1 border border-zinc-500/5">
            {['zh', 'en'].map((lang) => (
              <button 
                key={lang}
                onClick={() => i18n.changeLanguage(lang)}
                className={`px-3 py-1 rounded-full text-[10px] font-bold transition-all duration-300 ${
                  i18n.language === lang 
                    ? 'bg-white dark:bg-zinc-700 shadow-sm text-emerald-600 dark:text-emerald-400' 
                    : 'text-zinc-400'
                }`}
                aria-label={`Switch to ${lang === 'zh' ? 'Chinese' : 'English'}`}
              >
                {lang.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2.5 hover:bg-zinc-500/5 rounded-full transition-colors text-zinc-400"
            aria-label="Notifications"
            aria-expanded={showNotifications}
          >
            <Bell className="w-5 h-5" />
            <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 bg-red-500 rounded-full border-2 border-white dark:border-black"></span>
          </button>

          {showNotifications && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowNotifications(false)}
              />
              <div 
                className="absolute right-0 mt-2 w-80 glass-panel rounded-[24px] shadow-2xl p-6 animate-slide-in-right z-20"
                role="menu"
              >
                <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400 mb-4">
                  Notifications
                </h3>
                <div className="space-y-3">
                  <div className="text-sm text-zinc-600 dark:text-zinc-400 p-3 hover:bg-zinc-500/5 rounded-xl transition-colors">
                    No new notifications
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
