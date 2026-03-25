import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useUserInitialization } from '@/hooks/useUserInitialization';
import { useAuthStore, useUserStore, usePreferencesStore } from '@/stores';
import { usersApi } from '@/api';
import { usePrivacyStore } from '@/stores/privacyStore';

// Mock the API
vi.mock('@/api', () => ({
  usersApi: {
    getProfile: vi.fn(),
    getPreferences: vi.fn(),
    getPrivacySettings: vi.fn(),
    getQuotas: vi.fn(),
  },
}));

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: {
      language: 'en',
      changeLanguage: vi.fn(),
    },
  }),
}));

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: {
    error: vi.fn(),
  },
}));

describe('useUserInitialization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Reset stores
    useAuthStore.setState({
      user: null,
      token: null,
      isAuthenticated: false,
    });
    
    useUserStore.setState({
      profile: null,
      quotas: null,
    });
    
    usePreferencesStore.setState({
      language: 'en',
      motionPreference: 'auto',
      sidebarCollapsed: false,
      dashboardLayout: 'default',
      notificationsEnabled: true,
      soundEnabled: false,
      autoRefresh: true,
      refreshInterval: 30,
    });

    usePrivacyStore.getState().reset();
  });

  it('should not fetch data when not authenticated', () => {
    renderHook(() => useUserInitialization());
    
    expect(usersApi.getProfile).not.toHaveBeenCalled();
    expect(usersApi.getPreferences).not.toHaveBeenCalled();
    expect(usersApi.getPrivacySettings).not.toHaveBeenCalled();
  });

  it('should fetch user data when authenticated', async () => {
    const mockProfile = {
      id: '123',
      username: 'testuser',
      email: 'test@example.com',
      role: 'user',
      attributes: {
        preferences: {
          motion_preference: 'full',
        },
      },
    };
    
    const mockPreferences = {
      language: 'zh',
      theme: 'dark',
      motion_preference: 'full',
      sidebar_collapsed: true,
      dashboard_layout: 'compact',
      notifications_enabled: false,
      sound_enabled: true,
      auto_refresh: false,
      refresh_interval: 60,
    };

    const mockPrivacy = {
      profile_visibility: 'organization',
      searchable_profile: true,
      allow_telemetry: false,
      allow_training: false,
      data_retention_days: 365,
    };
    
    vi.mocked(usersApi.getProfile).mockResolvedValue(mockProfile);
    vi.mocked(usersApi.getPreferences).mockResolvedValue(mockPreferences);
    vi.mocked(usersApi.getPrivacySettings).mockResolvedValue(mockPrivacy);
    vi.mocked(usersApi.getQuotas).mockResolvedValue({
      maxAgents: 10,
      maxStorageGb: 100,
      currentAgents: 2,
      currentStorageGb: 15.5,
    });
    
    // Set authenticated state
    useAuthStore.setState({
      user: mockProfile as any,
      token: 'test-token',
      isAuthenticated: true,
    });
    
    renderHook(() => useUserInitialization());
    
    await waitFor(() => {
      expect(usersApi.getProfile).toHaveBeenCalled();
      expect(usersApi.getPreferences).toHaveBeenCalled();
      expect(usersApi.getPrivacySettings).toHaveBeenCalled();
    });
    
    // Check if stores were updated
    const userState = useUserStore.getState();
    expect(userState.profile).toEqual(mockProfile);
    
    const prefsState = usePreferencesStore.getState();
    expect(prefsState.language).toBe('zh');
    expect(prefsState.motionPreference).toBe('full');
    expect(prefsState.sidebarCollapsed).toBe(true);
    expect(usePrivacyStore.getState().allowTelemetry).toBe(false);
  });

  it('should handle API errors gracefully', async () => {
    vi.mocked(usersApi.getProfile).mockRejectedValue(new Error('API Error'));
    vi.mocked(usersApi.getPreferences).mockRejectedValue(new Error('API Error'));
    vi.mocked(usersApi.getPrivacySettings).mockRejectedValue(new Error('API Error'));
    
    // Set authenticated state
    useAuthStore.setState({
      user: { id: '123', username: 'test', email: 'test@test.com', role: 'user' },
      token: 'test-token',
      isAuthenticated: true,
    });
    
    renderHook(() => useUserInitialization());
    
    await waitFor(() => {
      expect(usersApi.getProfile).toHaveBeenCalled();
    });
    
    // Should not crash, stores should remain empty
    const userState = useUserStore.getState();
    expect(userState.profile).toBeNull();
    expect(usePrivacyStore.getState().allowTelemetry).toBe(true);
  });

  it('should not re-fetch data on re-render after initialization', async () => {
    const mockProfile = {
      id: '123',
      username: 'testuser',
      email: 'test@example.com',
      role: 'user',
    };
    
    const mockPreferences = {
      language: 'en',
      theme: 'dark',
      motion_preference: 'auto',
      sidebar_collapsed: false,
      dashboard_layout: 'default',
      notifications_enabled: true,
      sound_enabled: false,
      auto_refresh: true,
      refresh_interval: 30,
    };
    
    vi.mocked(usersApi.getProfile).mockResolvedValue(mockProfile);
    vi.mocked(usersApi.getPreferences).mockResolvedValue(mockPreferences);
    vi.mocked(usersApi.getPrivacySettings).mockResolvedValue({
      profile_visibility: 'organization',
      searchable_profile: true,
      allow_telemetry: true,
      allow_training: false,
      data_retention_days: 365,
    });
    vi.mocked(usersApi.getQuotas).mockResolvedValue({
      maxAgents: 10,
      maxStorageGb: 100,
      currentAgents: 2,
      currentStorageGb: 15.5,
    });
    
    // Set authenticated state
    useAuthStore.setState({
      user: mockProfile as any,
      token: 'test-token',
      isAuthenticated: true,
    });
    
    const { rerender } = renderHook(() => useUserInitialization());
    
    await waitFor(() => {
      expect(usersApi.getProfile).toHaveBeenCalled();
      expect(usersApi.getPreferences).toHaveBeenCalled();
    });

    const profileCallsBeforeRerender = vi.mocked(usersApi.getProfile).mock.calls.length;
    const preferenceCallsBeforeRerender = vi.mocked(usersApi.getPreferences).mock.calls.length;
    const privacyCallsBeforeRerender = vi.mocked(usersApi.getPrivacySettings).mock.calls.length;
    const quotaCallsBeforeRerender = vi.mocked(usersApi.getQuotas).mock.calls.length;
    
    // Re-render the hook (simulating language change or other re-render)
    rerender();
    
    // Wait a bit to ensure no new calls are made
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Should NOT fetch data again
    expect(vi.mocked(usersApi.getProfile).mock.calls.length).toBe(profileCallsBeforeRerender);
    expect(vi.mocked(usersApi.getPreferences).mock.calls.length).toBe(preferenceCallsBeforeRerender);
    expect(vi.mocked(usersApi.getPrivacySettings).mock.calls.length).toBe(privacyCallsBeforeRerender);
    expect(vi.mocked(usersApi.getQuotas).mock.calls.length).toBe(quotaCallsBeforeRerender);
  });
});
