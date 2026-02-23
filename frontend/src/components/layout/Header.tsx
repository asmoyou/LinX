import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Sun,
  Moon,
  Monitor,
  Bell,
  ShieldCheck,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronDown,
} from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';
import { useNotificationStore } from '@/stores/notificationStore';
import { usersApi } from '@/api/users';
import { healthApi, type DependencyHealth, type SystemHealthResponse } from '@/api/health';

interface HeaderProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export const Header: React.FC<HeaderProps> = ({ isCollapsed, onToggle }) => {
  const { i18n, t } = useTranslation();
  const navigate = useNavigate();
  const { theme, setTheme } = useThemeStore();
  const {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearAll,
    removeNotification,
  } = useNotificationStore();
  const [showNotifications, setShowNotifications] = React.useState(false);
  const [showSystemHealth, setShowSystemHealth] = React.useState(false);
  const [systemHealth, setSystemHealth] = React.useState<SystemHealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = React.useState(true);
  const [healthError, setHealthError] = React.useState<string | null>(null);

  const themeOptions = [
    { id: 'light' as const, icon: Sun },
    { id: 'system' as const, icon: Monitor },
    { id: 'dark' as const, icon: Moon }
  ];

  const savePreferences = async (updates: { language?: string; theme?: string }) => {
    try {
      // Get current preferences
      const currentPrefs = {
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

      // Save to backend using usersApi (fire and forget, don't block UI)
      usersApi.updatePreferences(newPrefs).catch((error) => {
        console.error('Failed to save preferences:', error);
      });
    } catch (error) {
      console.error('Failed to save preferences:', error);
    }
  };

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme);
    savePreferences({ theme: newTheme });
  };

  const handleLanguageChange = (newLanguage: string) => {
    i18n.changeLanguage(newLanguage);
    savePreferences({ language: newLanguage });
  };

  React.useEffect(() => {
    let mounted = true;

    const fetchHealth = async (initialLoad: boolean = false) => {
      if (initialLoad) {
        setHealthLoading(true);
      }

      try {
        const response = await healthApi.getSystemHealth();
        if (!mounted) {
          return;
        }

        setSystemHealth(response);
        setHealthError(null);
      } catch (error) {
        if (!mounted) {
          return;
        }
        const message = error instanceof Error ? error.message : 'Failed to fetch system health';
        setHealthError(message);
      } finally {
        if (mounted) {
          setHealthLoading(false);
        }
      }
    };

    void fetchHealth(true);
    const timer = window.setInterval(() => {
      void fetchHealth(false);
    }, 30000);

    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  type HeaderHealthState = 'checking' | 'unknown' | 'optimal' | 'degraded' | 'critical';

  const headerHealthState: HeaderHealthState = (() => {
    if (healthLoading && !systemHealth) return 'checking';
    if (!systemHealth) return 'unknown';
    return systemHealth.overall;
  })();

  const healthBadgeConfig: Record<
    HeaderHealthState,
    {
      label: string;
      textClass: string;
      iconClass: string;
      borderClass: string;
      bgClass: string;
    }
  > = {
    checking: {
      label: t('header.health.checking', 'Checking'),
      textClass: 'text-zinc-500 dark:text-zinc-300',
      iconClass: 'text-zinc-500 dark:text-zinc-300',
      borderClass: 'border-zinc-500/20',
      bgClass: 'bg-zinc-500/10',
    },
    unknown: {
      label: t('header.health.unknown', 'Unknown'),
      textClass: 'text-amber-600 dark:text-amber-400',
      iconClass: 'text-amber-500',
      borderClass: 'border-amber-500/30',
      bgClass: 'bg-amber-500/10',
    },
    optimal: {
      label: t('header.optimal', 'Optimal'),
      textClass: 'text-emerald-600 dark:text-emerald-500',
      iconClass: 'text-emerald-500',
      borderClass: 'border-emerald-500/30',
      bgClass: 'bg-emerald-500/10',
    },
    degraded: {
      label: t('header.health.degraded', 'Degraded'),
      textClass: 'text-amber-600 dark:text-amber-400',
      iconClass: 'text-amber-500',
      borderClass: 'border-amber-500/30',
      bgClass: 'bg-amber-500/10',
    },
    critical: {
      label: t('header.health.critical', 'Critical'),
      textClass: 'text-rose-600 dark:text-rose-400',
      iconClass: 'text-rose-500',
      borderClass: 'border-rose-500/30',
      bgClass: 'bg-rose-500/10',
    },
  };

  const getDependencyStatusText = (dependency: DependencyHealth): string => {
    if (dependency.status === 'up') {
      return t('header.health.running', 'Running');
    }
    if (dependency.status === 'disabled') {
      return t('header.health.disabled', 'Disabled');
    }
    return t('header.health.down', 'Down');
  };

  const getDependencyStatusClass = (dependency: DependencyHealth): string => {
    if (dependency.status === 'up') {
      return 'text-emerald-600 dark:text-emerald-400';
    }
    if (dependency.status === 'disabled') {
      return 'text-zinc-500 dark:text-zinc-400';
    }
    return dependency.required
      ? 'text-rose-600 dark:text-rose-400'
      : 'text-amber-600 dark:text-amber-400';
  };

  const getDependencyDotClass = (dependency: DependencyHealth): string => {
    if (dependency.status === 'up') {
      return 'bg-emerald-500';
    }
    if (dependency.status === 'disabled') {
      return 'bg-zinc-400';
    }
    return dependency.required ? 'bg-rose-500' : 'bg-amber-500';
  };

  const formatHealthTimestamp = (timestampSeconds: number): string => {
    const locale = i18n.language.startsWith('zh') ? 'zh-CN' : 'en-US';
    return new Date(timestampSeconds * 1000).toLocaleString(locale, {
      hour12: false,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatNotificationTimestamp = (value: string): string => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(i18n.language.startsWith('zh') ? 'zh-CN' : 'en-US', {
      hour12: false,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const badge = healthBadgeConfig[headerHealthState];

  return (
    <header
      className="h-16 border-b border-zinc-500/5 glass-panel flex items-center justify-between px-6 z-30"
      role="banner"
    >
      <div className="flex items-center gap-4">
        {/* Sidebar Toggle Button */}
        <button
          onClick={onToggle}
          className="p-2 rounded-xl hover:bg-zinc-500/10 text-zinc-500 dark:text-zinc-400 transition-all duration-300 active:scale-95 group"
          aria-label={isCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
          title={isCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
        >
          {isCollapsed ? (
            <PanelLeftOpen className="w-5 h-5 transition-all duration-300 group-hover:text-emerald-500" />
          ) : (
            <PanelLeftClose className="w-5 h-5 transition-all duration-300 group-hover:text-emerald-500" />
          )}
        </button>

        <div className="relative hidden md:block">
          <button
            onClick={() => setShowSystemHealth((prev) => !prev)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-[11px] font-medium uppercase tracking-widest transition-colors ${badge.borderClass} ${badge.bgClass}`}
            aria-label={t('header.health.openStatus', 'Open system status')}
            aria-expanded={showSystemHealth}
          >
            <ShieldCheck className={`w-3.5 h-3.5 ${badge.iconClass}`} />
            <span className="text-zinc-600 dark:text-zinc-300">
              {t('header.status', 'Status')}:
            </span>
            <span className={badge.textClass}>{badge.label}</span>
            <ChevronDown
              className={`w-3.5 h-3.5 text-zinc-500 transition-transform ${
                showSystemHealth ? 'rotate-180' : ''
              }`}
            />
          </button>

          {showSystemHealth && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowSystemHealth(false)}
              />
              <div className="absolute left-0 mt-2 w-[440px] rounded-[24px] border border-zinc-200/80 bg-white/95 p-5 shadow-2xl backdrop-blur-xl dark:border-zinc-700/80 dark:bg-zinc-900/95 z-50">
                <div className="flex items-start justify-between gap-3 mb-4">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-300">
                      {t('header.health.title', 'System Dependencies')}
                    </h3>
                    {systemHealth && (
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {t('header.health.lastUpdated', 'Updated')}: {' '}
                        {formatHealthTimestamp(systemHealth.timestamp)}
                      </p>
                    )}
                  </div>
                  <span
                    className={`px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider ${badge.bgClass} ${badge.textClass}`}
                  >
                    {badge.label}
                  </span>
                </div>

                {healthLoading && !systemHealth && (
                  <div className="text-sm text-zinc-500 dark:text-zinc-400 py-3">
                    {t('header.health.checkingDetails', 'Checking dependencies...')}
                  </div>
                )}

                {healthError && !systemHealth && (
                  <div className="text-sm text-rose-600 dark:text-rose-400 py-3">
                    {t('header.health.fetchFailed', 'Failed to load health status')}: {healthError}
                  </div>
                )}

                {systemHealth && (
                  <>
                    <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1 custom-scrollbar">
                      {systemHealth.dependencies.map((dependency) => (
                        <div
                          key={dependency.id}
                          className="p-3 rounded-xl border border-zinc-200/70 bg-white/80 dark:border-zinc-700/70 dark:bg-zinc-800/70"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className={`w-2 h-2 rounded-full ${getDependencyDotClass(dependency)}`} />
                              <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200 truncate">
                                {dependency.name}
                              </p>
                              <span className="px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wide bg-zinc-500/10 text-zinc-500 dark:text-zinc-400">
                                {dependency.required
                                  ? t('header.health.required', 'Required')
                                  : t('header.health.optional', 'Optional')}
                              </span>
                            </div>

                            <span className={`text-xs font-semibold uppercase tracking-wider ${getDependencyStatusClass(dependency)}`}>
                              {getDependencyStatusText(dependency)}
                            </span>
                          </div>

                          <p className="mt-1.5 text-xs text-zinc-600 dark:text-zinc-400">
                            {dependency.message}
                          </p>

                          {dependency.status === 'down' && (
                            <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">
                              {t('header.health.impact', 'Impact')}: {dependency.impact}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>

                    <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
                      {t('header.health.summary', 'Required healthy {{requiredHealthy}}/{{requiredTotal}}, optional down {{optionalDown}}', {
                        requiredHealthy: systemHealth.summary.required_healthy,
                        requiredTotal: systemHealth.summary.required_total,
                        optionalDown: systemHealth.summary.optional_unhealthy,
                      })}
                    </p>
                  </>
                )}
              </div>
            </>
          )}
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
                onClick={() => handleThemeChange(item.id)}
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
            {[
              { code: 'zh', label: '中文' },
              { code: 'en', label: 'EN' }
            ].map((lang) => (
              <button 
                key={lang.code}
                onClick={() => handleLanguageChange(lang.code)}
                className={`px-3 py-1 rounded-full text-[10px] font-bold transition-all duration-300 ${
                  i18n.language === lang.code 
                    ? 'bg-white dark:bg-zinc-700 shadow-sm text-emerald-600 dark:text-emerald-400' 
                    : 'text-zinc-400'
                }`}
                aria-label={`Switch to ${lang.code === 'zh' ? 'Chinese' : 'English'}`}
              >
                {lang.label}
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
            {unreadCount > 0 && (
              <>
                <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 bg-red-500 rounded-full border-2 border-white dark:border-black"></span>
                <span className="absolute -top-0.5 -right-0.5 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-red-500 text-white text-[10px] leading-[1.1rem] font-semibold text-center">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              </>
            )}
          </button>

          {showNotifications && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowNotifications(false)}
              />
              <div 
                className="absolute right-0 mt-2 w-80 glass-panel rounded-[24px] shadow-2xl p-6 animate-slide-in-right z-50"
                role="menu"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
                    Notifications
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={markAllAsRead}
                      className="text-[10px] text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                    >
                      Mark all read
                    </button>
                    <button
                      onClick={clearAll}
                      className="text-[10px] text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1 custom-scrollbar">
                  {notifications.length === 0 ? (
                    <div className="text-sm text-zinc-600 dark:text-zinc-400 p-3 rounded-xl">
                      No new notifications
                    </div>
                  ) : (
                    notifications.map((notification) => (
                      <div
                        key={notification.id}
                        className={`p-3 rounded-xl border transition-colors ${
                          notification.read
                            ? 'border-zinc-200/70 dark:border-zinc-700/70 bg-white/60 dark:bg-zinc-800/40'
                            : 'border-emerald-200 dark:border-emerald-500/40 bg-emerald-50/70 dark:bg-emerald-500/10'
                        }`}
                      >
                        <button
                          className="w-full text-left"
                          onClick={() => {
                            if (!notification.read) {
                              markAsRead(notification.id);
                            }
                            if (notification.actionUrl) {
                              navigate(notification.actionUrl);
                              setShowNotifications(false);
                            }
                          }}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 truncate">
                                {notification.title}
                              </div>
                              <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300 whitespace-pre-wrap break-words">
                                {notification.message}
                              </div>
                              <div className="mt-1 text-[10px] text-zinc-400">
                                {formatNotificationTimestamp(notification.timestamp)}
                              </div>
                            </div>
                            {!notification.read && (
                              <span className="mt-1 w-2 h-2 rounded-full bg-emerald-500" />
                            )}
                          </div>
                        </button>
                        <div className="mt-2 flex items-center justify-end gap-2">
                          {notification.actionUrl && (
                            <button
                              onClick={() => {
                                markAsRead(notification.id);
                                navigate(notification.actionUrl as string);
                                setShowNotifications(false);
                              }}
                              className="text-[10px] px-2 py-1 rounded-md border border-emerald-300 dark:border-emerald-500/40 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10"
                            >
                              {notification.actionLabel || 'Open'}
                            </button>
                          )}
                          <button
                            onClick={() => removeNotification(notification.id)}
                            className="text-[10px] px-2 py-1 rounded-md border border-zinc-200 dark:border-zinc-700 text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
                          >
                            Dismiss
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
