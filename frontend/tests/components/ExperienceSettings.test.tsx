import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { platformApi } from '@/api';
import { ExperienceSettings } from '@/components/settings/ExperienceSettings';
import { useAuthStore, useUserStore } from '@/stores';

const platformSettingsFixture = {
  default_motion_preference: 'auto',
  emergency_disable_motion: false,
  telemetry_sample_rate: 0.2,
};

const setPlatformSettingsMock = vi.fn();

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback || _key,
    }),
  };
});

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

vi.mock('@/api', () => ({
  platformApi: {
    getUiExperience: vi.fn(),
    updateUiExperience: vi.fn(),
  },
}));

vi.mock('@/motion', () => ({
  useMotionPolicy: () => ({
    effectiveTier: 'full',
    source: 'platform_default',
    platformSettings: platformSettingsFixture,
    setPlatformSettings: setPlatformSettingsMock,
  }),
}));

describe('ExperienceSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        id: 'user-1',
        username: 'alice',
        email: 'alice@example.com',
        role: 'viewer',
      },
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
    useUserStore.setState({
      profile: {
        id: 'user-1',
        username: 'alice',
        email: 'alice@example.com',
        role: 'admin',
      },
      quotas: null,
      isLoading: false,
      error: null,
    });

    vi.mocked(platformApi.getUiExperience).mockResolvedValue(platformSettingsFixture);
  });

  afterEach(() => {
    cleanup();
    useAuthStore.getState().logout();
    useUserStore.getState().reset();
  });

  it('prefers the refreshed profile role when deciding whether settings are manageable', async () => {
    render(<ExperienceSettings />);

    await waitFor(() => {
      expect(vi.mocked(platformApi.getUiExperience)).toHaveBeenCalledTimes(1);
    });

    expect(screen.getAllByText('UI Experience').length).toBeGreaterThan(0);
    expect(
      screen.queryByText('Only admin and manager roles can manage the platform motion policy.'),
    ).not.toBeInTheDocument();
    expect(setPlatformSettingsMock).toHaveBeenCalledWith(platformSettingsFixture);
  });
});
