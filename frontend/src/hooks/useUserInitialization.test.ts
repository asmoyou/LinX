import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useUserInitialization } from './useUserInitialization';
import { useAuthStore, useUserStore, usePreferencesStore } from '../stores';
import { usersApi } from '../api';

// Mock the API
vi.mock('../api', () => ({
  usersApi: {
    getProfile: vi.fn(),
    getPreferences: vi.fn(),
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
      sidebarCollapsed: false,
      dashboardLayout: 'default',
      notificationsEnabled: true,
      soundEnabled: false,
      autoRefresh: true,
      refreshInterval: 30,
    });
  });

  it('should not fetch data when not authenticated', () => {
    renderHook(() => useUserInitialization());
    
    expect(usersApi.getProfile).not.toHaveBeenCalled();
    expect(usersApi.getPreferences).not.toHaveBeenCalled();
  });

  it('should fetch user data when authenticated', async () => {
    const mockProfile = {
      id: '123',
      username: 'testuser',
      email: 'test@example.com',
      role: 'user',
    };
    
    const mockPreferences = {
      language: 'zh',
      theme: 'dark',
      sidebar_collapsed: true,
      dashboard_layout: 'compact',
      notifications_enabled: false,
      sound_enabled: true,
      auto_refresh: false,
      refresh_interval: 60,
    };
    
    vi.mocked(usersApi.getProfile).mockResolvedValue(mockProfile);
    vi.mocked(usersApi.getPreferences).mockResolvedValue(mockPreferences);
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
    });
    
    // Check if stores were updated
    const userState = useUserStore.getState();
    expect(userState.profile).toEqual(mockProfile);
    
    const prefsState = usePreferencesStore.getState();
    expect(prefsState.language).toBe('zh');
    expect(prefsState.sidebarCollapsed).toBe(true);
  });

  it('should handle API errors gracefully', async () => {
    vi.mocked(usersApi.getProfile).mockRejectedValue(new Error('API Error'));
    vi.mocked(usersApi.getPreferences).mockRejectedValue(new Error('API Error'));
    
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
  });
});
