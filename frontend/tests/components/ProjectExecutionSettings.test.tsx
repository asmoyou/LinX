import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { platformApi } from '@/api/platform';
import { ProjectExecutionSettings } from '@/components/settings/ProjectExecutionSettings';
import { useAuthStore, useUserStore } from '@/stores';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string | { defaultValue?: string }) => {
        if (typeof fallback === 'string') {
          return fallback;
        }
        return fallback?.defaultValue || _key;
      },
    }),
  };
});

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

vi.mock('@/api/platform', () => ({
  platformApi: {
    getProjectExecutionSettings: vi.fn(),
    updateProjectExecutionSettings: vi.fn(),
  },
}));

describe('ProjectExecutionSettings', () => {
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
    vi.mocked(platformApi.getProjectExecutionSettings).mockResolvedValue({
      default_launch_command_template: 'codex exec "$LINX_AGENT_PROMPT"',
    });
    vi.mocked(platformApi.updateProjectExecutionSettings).mockResolvedValue({
      default_launch_command_template: 'codex exec "$LINX_AGENT_PROMPT"',
    });
  });

  afterEach(() => {
    cleanup();
    useAuthStore.getState().logout();
    useUserStore.getState().reset();
  });

  it('loads the platform default launch command template', async () => {
    render(<ProjectExecutionSettings />);

    await waitFor(() => {
      expect(platformApi.getProjectExecutionSettings).toHaveBeenCalledTimes(1);
    });

    const textarea = screen.getByPlaceholderText(
      'Example: codex exec --skip-git-repo-check --sandbox danger-full-access --cd "$LINX_WORKSPACE_ROOT" "$LINX_AGENT_PROMPT"',
    );
    expect(textarea).toHaveValue('codex exec "$LINX_AGENT_PROMPT"');
    expect(screen.getByRole('button', { name: 'Save Defaults' })).toBeInTheDocument();
  });
});
