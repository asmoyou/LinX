import { useEffect, useCallback } from 'react';
import { useAuthStore, useUserStore, usePreferencesStore } from '../stores';
import { usersApi } from '../api';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

/**
 * Hook to initialize user data after login
 * Fetches user profile, quotas, and preferences
 */
export const useUserInitialization = () => {
  const { isAuthenticated, token } = useAuthStore();
  const { setProfile, setQuotas } = useUserStore();
  const { updatePreferences } = usePreferencesStore();
  const { i18n } = useTranslation();

  const initializeUserData = useCallback(async () => {
    if (!isAuthenticated || !token) {
      return;
    }

    try {
      // Fetch user data in parallel
      const [profile, preferences] = await Promise.allSettled([
        usersApi.getProfile(),
        usersApi.getPreferences(),
      ]);

      // Handle profile
      if (profile.status === 'fulfilled') {
        setProfile(profile.value);
      } else {
        console.error('Failed to fetch user profile:', profile.reason);
      }

      // Handle preferences
      if (preferences.status === 'fulfilled') {
        const prefs = preferences.value;
        
        // Update preferences store
        updatePreferences({
          language: prefs.language as 'en' | 'zh',
          sidebarCollapsed: prefs.sidebar_collapsed,
          dashboardLayout: prefs.dashboard_layout as any,
          notificationsEnabled: prefs.notifications_enabled,
          soundEnabled: prefs.sound_enabled,
          autoRefresh: prefs.auto_refresh,
          refreshInterval: prefs.refresh_interval,
        });

        // Update i18n language
        if (prefs.language && i18n.language !== prefs.language) {
          i18n.changeLanguage(prefs.language);
        }
      } else {
        console.error('Failed to fetch user preferences:', preferences.reason);
      }

      // Fetch quotas (non-critical, don't block on failure)
      try {
        const quotas = await usersApi.getQuotas();
        setQuotas(quotas);
      } catch (error) {
        console.warn('Failed to fetch user quotas:', error);
        // Quotas are not critical, continue without them
      }
    } catch (error) {
      console.error('Failed to initialize user data:', error);
      toast.error('Failed to load user data');
    }
  }, [isAuthenticated, token, setProfile, setQuotas, updatePreferences, i18n]);

  // Initialize on mount and when authentication changes
  useEffect(() => {
    initializeUserData();
  }, [initializeUserData]);

  return { initializeUserData };
};
