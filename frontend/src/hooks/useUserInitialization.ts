import { useEffect, useCallback, useRef, useState } from 'react';
import { useAuthStore, useUserStore, usePreferencesStore } from '../stores';
import { usePrivacyStore } from '../stores/privacyStore';
import { usersApi } from '../api';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { useMotionPolicy } from '@/motion';
import type { MotionPreference } from '@/motion';

/**
 * Hook to initialize user data after login
 * Fetches user profile, quotas, and preferences
 */
export const useUserInitialization = () => {
  const { isAuthenticated, token } = useAuthStore();
  const { setProfile, setQuotas } = useUserStore();
  const { updatePreferences } = usePreferencesStore();
  const setAllowTelemetry = usePrivacyStore((state) => state.setAllowTelemetry);
  const { i18n } = useTranslation();
  const { setUserPreference, clearUserPreference } = useMotionPolicy();
  const [isInitializing, setIsInitializing] = useState(false);
  
  // Track if we've already initialized to prevent re-fetching on language change
  const hasInitialized = useRef(false);

  const initializeUserData = useCallback(async () => {
    if (!isAuthenticated || !token) {
      hasInitialized.current = false;
      setIsInitializing(false);
      setAllowTelemetry(true);
      clearUserPreference();
      return;
    }

    // Skip if already initialized (prevents re-fetch on language change)
    if (hasInitialized.current) {
      return;
    }

    setIsInitializing(true);

    try {
      // Fetch user data in parallel
      const [profile, preferences, privacy] = await Promise.allSettled([
        usersApi.getProfile(),
        usersApi.getPreferences(),
        usersApi.getPrivacySettings(),
      ]);

      const rawMotionPreference = (
        profile.status === 'fulfilled'
          ? profile.value.attributes?.preferences?.motion_preference
          : undefined
      ) as MotionPreference | undefined;
      const hasRawMotionPreference = typeof rawMotionPreference === 'string';

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
          motionPreference: prefs.motion_preference,
          sidebarCollapsed: prefs.sidebar_collapsed,
          dashboardLayout: prefs.dashboard_layout as any,
          notificationsEnabled: prefs.notifications_enabled,
          soundEnabled: prefs.sound_enabled,
          autoRefresh: prefs.auto_refresh,
          refreshInterval: prefs.refresh_interval,
        });
        setUserPreference(prefs.motion_preference, hasRawMotionPreference);

        // Update i18n language
        if (prefs.language && i18n.language !== prefs.language) {
          i18n.changeLanguage(prefs.language);
        }
      } else {
        console.error('Failed to fetch user preferences:', preferences.reason);
        setUserPreference('auto', false);
      }

      if (privacy.status === 'fulfilled') {
        setAllowTelemetry(privacy.value.allow_telemetry);
      } else {
        console.error('Failed to fetch user privacy settings:', privacy.reason);
        setAllowTelemetry(true);
      }

      // Fetch quotas (non-critical, don't block on failure)
      try {
        const quotas = await usersApi.getQuotas();
        setQuotas(quotas);
      } catch (error) {
        console.warn('Failed to fetch user quotas:', error);
        // Quotas are not critical, continue without them
      }

      // Mark as initialized
      hasInitialized.current = true;
    } catch (error) {
      console.error('Failed to initialize user data:', error);
      toast.error('Failed to load user data');
    } finally {
      setIsInitializing(false);
    }
  }, [
    clearUserPreference,
    i18n,
    isAuthenticated,
    setAllowTelemetry,
    setProfile,
    setQuotas,
    setUserPreference,
    token,
    updatePreferences,
  ]);

  // Initialize on mount and when authentication changes
  useEffect(() => {
    initializeUserData();
  }, [initializeUserData]);

  return { initializeUserData, isInitializing, hasInitialized: hasInitialized.current };
};
