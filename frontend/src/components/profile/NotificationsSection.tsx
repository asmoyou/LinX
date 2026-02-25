import { useEffect, useState } from 'react';
import { Bell, Volume2, RefreshCw, Mail } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { usersApi } from '@/api/users';
import { useNotificationStore } from '@/stores/notificationStore';
import { usePreferencesStore } from '@/stores';

interface NotificationPreferences {
  notificationsEnabled: boolean;
  soundEnabled: boolean;
  autoRefresh: boolean;
  refreshInterval: number;
}

export const NotificationsSection = () => {
  const { t } = useTranslation();
  const { addNotification } = useNotificationStore();
  const { updatePreferences: updatePreferenceStore } = usePreferencesStore();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [preferences, setPreferences] = useState<NotificationPreferences>({
    notificationsEnabled: true,
    soundEnabled: false,
    autoRefresh: true,
    refreshInterval: 30,
  });

  useEffect(() => {
    let mounted = true;

    const loadPreferences = async () => {
      setIsLoading(true);
      try {
        const data = await usersApi.getPreferences();
        if (!mounted) return;
        setPreferences({
          notificationsEnabled: data.notifications_enabled,
          soundEnabled: data.sound_enabled,
          autoRefresh: data.auto_refresh,
          refreshInterval: data.refresh_interval,
        });
      } catch (error) {
        console.error('Failed to load notification preferences:', error);
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    void loadPreferences();

    return () => {
      mounted = false;
    };
  }, []);

  const handleToggle = (key: keyof NotificationPreferences) => {
    setPreferences((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const nextPreferences = {
        notifications_enabled: preferences.notificationsEnabled,
        sound_enabled: preferences.soundEnabled,
        auto_refresh: preferences.autoRefresh,
        refresh_interval: preferences.refreshInterval,
      };

      await usersApi.updatePreferences(nextPreferences);

      updatePreferenceStore({
        notificationsEnabled: preferences.notificationsEnabled,
        soundEnabled: preferences.soundEnabled,
        autoRefresh: preferences.autoRefresh,
        refreshInterval: preferences.refreshInterval,
      });

      addNotification({
        type: 'success',
        title: t('profileSettings.notifications.savedTitle', 'Preferences Saved'),
        message: t(
          'profileSettings.notifications.savedMessage',
          'Your notification preferences have been updated.'
        ),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.notifications.saveFailedTitle', 'Save Failed'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.notifications.saveFailedMessage', 'Failed to save preferences'),
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Bell className="w-5 h-5 text-emerald-500" />
          <div>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {t('profileSettings.notifications.title', 'Notification Preferences')}
            </h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
              {t('profileSettings.notifications.subtitle', 'Manage delivery and refresh behavior')}
            </p>
          </div>
        </div>

        {isLoading ? (
          <div className="text-sm text-zinc-600 dark:text-zinc-300">
            {t('profileSettings.notifications.loading', 'Loading preferences...')}
          </div>
        ) : (
          <>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-white dark:bg-white/5 rounded-lg border border-zinc-200 dark:border-white/10">
                <div className="flex items-start gap-3">
                  <Mail className="w-5 h-5 text-zinc-500 mt-0.5" />
                  <div>
                    <h3 className="text-zinc-900 dark:text-white font-medium">
                      {t('profileSettings.notifications.enableTitle', 'Enable Notifications')}
                    </h3>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                      {t(
                        'profileSettings.notifications.enableDescription',
                        'Receive in-app alerts for missions and system updates.'
                      )}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleToggle('notificationsEnabled')}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    preferences.notificationsEnabled ? 'bg-emerald-500' : 'bg-zinc-400'
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      preferences.notificationsEnabled ? 'translate-x-7' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-white dark:bg-white/5 rounded-lg border border-zinc-200 dark:border-white/10">
                <div className="flex items-start gap-3">
                  <Volume2 className="w-5 h-5 text-zinc-500 mt-0.5" />
                  <div>
                    <h3 className="text-zinc-900 dark:text-white font-medium">
                      {t('profileSettings.notifications.soundTitle', 'Enable Sound')}
                    </h3>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                      {t(
                        'profileSettings.notifications.soundDescription',
                        'Play sound when new high-priority notifications arrive.'
                      )}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleToggle('soundEnabled')}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    preferences.soundEnabled ? 'bg-emerald-500' : 'bg-zinc-400'
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      preferences.soundEnabled ? 'translate-x-7' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="p-4 bg-white dark:bg-white/5 rounded-lg border border-zinc-200 dark:border-white/10 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-start gap-3">
                    <RefreshCw className="w-5 h-5 text-zinc-500 mt-0.5" />
                    <div>
                      <h3 className="text-zinc-900 dark:text-white font-medium">
                        {t('profileSettings.notifications.autoRefreshTitle', 'Auto Refresh')}
                      </h3>
                      <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                        {t(
                          'profileSettings.notifications.autoRefreshDescription',
                          'Automatically refresh mission and dashboard data in the background.'
                        )}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleToggle('autoRefresh')}
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      preferences.autoRefresh ? 'bg-emerald-500' : 'bg-zinc-400'
                    }`}
                  >
                    <div
                      className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                        preferences.autoRefresh ? 'translate-x-7' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {t('profileSettings.notifications.refreshInterval', 'Refresh Interval (seconds)')}
                  </label>
                  <input
                    type="number"
                    min={10}
                    max={300}
                    step={5}
                    disabled={!preferences.autoRefresh}
                    value={preferences.refreshInterval}
                    onChange={(e) =>
                      setPreferences((prev) => ({
                        ...prev,
                        refreshInterval: Math.min(300, Math.max(10, Number(e.target.value) || 30)),
                      }))
                    }
                    className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                </div>
              </div>
            </div>

            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving
                ? t('profileSettings.notifications.saving', 'Saving...')
                : t('profileSettings.notifications.save', 'Save Preferences')}
            </button>
          </>
        )}
      </div>
    </GlassPanel>
  );
};
