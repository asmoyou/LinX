import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { llmApi } from '@/api/llm';
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

vi.mock('@/api/llm', () => ({
  llmApi: {
    getProvidersConfig: vi.fn(),
    getProviderModelsMetadata: vi.fn(),
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
      planner_provider: 'ollama',
      planner_model: 'qwen3-vl:30b',
      planner_temperature: 0.2,
      planner_max_tokens: 4000,
    });
    vi.mocked(platformApi.updateProjectExecutionSettings).mockResolvedValue({
      planner_provider: 'ollama',
      planner_model: 'qwen3-vl:30b',
      planner_temperature: 0.2,
      planner_max_tokens: 4000,
    });
    vi.mocked(llmApi.getProvidersConfig).mockResolvedValue({
      providers: {
        ollama: {
          name: 'ollama',
          healthy: true,
          available_models: ['qwen3-vl:30b', 'bge-m3'],
          is_config_based: false,
        },
      },
      default_provider: 'ollama',
      fallback_enabled: false,
      model_mapping: {},
    });
    vi.mocked(llmApi.getProviderModelsMetadata).mockResolvedValue({
      provider_name: 'ollama',
      protocol: 'ollama',
      models: {
        'qwen3-vl:30b': {
          model_id: 'qwen3-vl:30b',
          model_type: 'chat',
          default_temperature: 0.7,
          temperature_range: [0, 2],
          supports_streaming: true,
          supports_system_prompt: true,
          supports_function_calling: true,
          supports_vision: true,
          supports_reasoning: false,
          deprecated: false,
        },
        'bge-m3': {
          model_id: 'bge-m3',
          model_type: 'embedding',
          default_temperature: 0,
          temperature_range: [0, 0],
          supports_streaming: false,
          supports_system_prompt: false,
          supports_function_calling: false,
          supports_vision: false,
          supports_reasoning: false,
          deprecated: false,
        },
      },
    });
  });

  afterEach(() => {
    cleanup();
    useAuthStore.getState().logout();
    useUserStore.getState().reset();
  });

  it('loads the planner defaults for project execution', async () => {
    render(<ProjectExecutionSettings />);

    await waitFor(() => {
      expect(platformApi.getProjectExecutionSettings).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByText('Native Runtime Execution'),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue('ollama')).toBeInTheDocument();
    expect(screen.getByDisplayValue('qwen3-vl:30b')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save Defaults' })).toBeInTheDocument();
  });
});
