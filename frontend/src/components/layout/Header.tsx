import React from 'react';
import { useTranslation } from 'react-i18next';
import { Sun, Moon, Monitor, Globe, Bell } from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';

interface HeaderProps {
  sidebarCollapsed: boolean;
}

export const Header: React.FC<HeaderProps> = ({ sidebarCollapsed }) => {
  const { i18n } = useTranslation();
  const { theme, setTheme } = useThemeStore();
  const [showNotifications, setShowNotifications] = React.useState(false);

  const toggleTheme = () => {
    const themes: Array<'light' | 'dark' | 'system'> = ['light', 'dark', 'system'];
    const currentIndex = themes.indexOf(theme);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    setTheme(nextTheme);
    
    // Apply theme
    if (nextTheme === 'dark' || (nextTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'zh' : 'en';
    i18n.changeLanguage(newLang);
  };

  const getThemeIcon = () => {
    switch (theme) {
      case 'light':
        return <Sun className="w-5 h-5" />;
      case 'dark':
        return <Moon className="w-5 h-5" />;
      case 'system':
        return <Monitor className="w-5 h-5" />;
    }
  };

  return (
    <header
      className={`glass fixed top-0 right-0 h-16 z-30 transition-all duration-300 ${
        sidebarCollapsed ? 'left-16' : 'left-64'
      }`}
      role="banner"
    >
      <div className="flex items-center justify-between h-full px-6">
        {/* Status Indicator */}
        <div className="flex items-center gap-2" role="status" aria-live="polite">
          <div 
            className="w-2 h-2 bg-green-500 rounded-full animate-pulse" 
            aria-hidden="true"
          />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            System Online
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2" role="toolbar" aria-label="Header actions">
          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg hover:bg-white/20 transition-colors text-gray-700 dark:text-gray-300"
            aria-label={`Toggle theme. Current: ${theme}`}
            title={`Current: ${theme}`}
          >
            {getThemeIcon()}
          </button>

          {/* Language Selector */}
          <button
            onClick={toggleLanguage}
            className="p-2 rounded-lg hover:bg-white/20 transition-colors text-gray-700 dark:text-gray-300"
            aria-label={`Toggle language. Current: ${i18n.language === 'en' ? 'English' : 'Chinese'}`}
            title={`Current: ${i18n.language}`}
          >
            <Globe className="w-5 h-5" aria-hidden="true" />
          </button>

          {/* Notifications */}
          <div className="relative">
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="p-2 rounded-lg hover:bg-white/20 transition-colors text-gray-700 dark:text-gray-300 relative"
              aria-label="Notifications"
              aria-expanded={showNotifications}
              aria-haspopup="true"
            >
              <Bell className="w-5 h-5" aria-hidden="true" />
              <span 
                className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" 
                aria-label="New notifications"
              />
            </button>

            {/* Notification Dropdown */}
            {showNotifications && (
              <div 
                className="absolute right-0 mt-2 w-80 glass rounded-lg shadow-lg p-4"
                role="menu"
                aria-label="Notification menu"
              >
                <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-2">
                  Notifications
                </h3>
                <div className="space-y-2">
                  <div 
                    className="text-sm text-gray-600 dark:text-gray-400 p-2 hover:bg-white/10 rounded"
                    role="menuitem"
                  >
                    No new notifications
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
