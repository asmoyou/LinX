import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentConfigModal } from '@/components/workforce/AgentConfigModal';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string | { defaultValue?: string; value?: string }) => {
        if (typeof fallback === 'string') {
          return fallback;
        }
        return fallback?.defaultValue || _key;
      },
      i18n: { language: 'en' },
    }),
  };
});

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

vi.mock('@/components/LayoutModal', () => ({
  LayoutModal: ({
    isOpen,
    children,
    footer,
  }: {
    isOpen: boolean;
    children: React.ReactNode;
    footer?: React.ReactNode;
  }) => (isOpen ? <div>{children}{footer}</div> : null),
}));

vi.mock('@/components/settings/ModelMetadataCard', () => ({
  ModelMetadataCard: () => null,
}));

vi.mock('@/components/common/ImageCropModal', () => ({
  ImageCropModal: () => null,
}));

vi.mock('@/api', () => ({
  llmApi: {
    getAvailableProviders: vi.fn().mockResolvedValue({}),
    getModelMetadata: vi.fn().mockResolvedValue(null),
  },
  agentsApi: {
    getFeishuPublication: vi.fn().mockResolvedValue({
      status: 'draft',
      channelType: 'feishu',
      deliveryMode: 'long_connection',
      hasAppSecret: false,
      connectionState: 'inactive',
    }),
    getExternalRuntime: vi.fn().mockResolvedValue({
      state: {
        status: 'online',
        bound: true,
        availableForConversation: true,
        availableForExecution: true,
        hostName: 'mac-mini',
        hostOs: 'darwin',
        hostArch: 'arm64',
        currentVersion: '0.1.0',
        desiredVersion: '0.1.0',
        updateAvailable: false,
      },
      profile: {
        path_allowlist: ['/tmp/workspace'],
        install_channel: 'stable',
        desired_version: '0.1.0',
      },
    }),
    updateExternalRuntimeProfile: vi.fn(),
  },
}));

vi.mock('@/api/knowledge', () => ({
  knowledgeApi: {
    getCollections: vi.fn().mockResolvedValue({
      collections: [],
      total: 0,
    }),
  },
}));

vi.mock('@/api/skills', () => ({
  skillsApi: {
    getAgentBindings: vi.fn().mockResolvedValue({
      available_skills: [],
      bindings: [],
    }),
  },
}));

describe('AgentConfigModal external runtime wizard', () => {
  const originalNavigatorPlatform = window.navigator.platform;
  const originalNavigatorUserAgent = window.navigator.userAgent;

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window.navigator, 'platform', {
      configurable: true,
      value: 'Win32',
    });
    Object.defineProperty(window.navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    });
  });

  afterEach(() => {
    cleanup();
    Object.defineProperty(window.navigator, 'platform', {
      configurable: true,
      value: originalNavigatorPlatform,
    });
    Object.defineProperty(window.navigator, 'userAgent', {
      configurable: true,
      value: originalNavigatorUserAgent,
    });
  });

  it('opens directly on the runtime guide for external agents', async () => {
    render(
      <AgentConfigModal
        agent={{
          id: 'agent-1',
          name: 'External Ops',
          type: 'external_general',
          status: 'offline',
          tasksCompleted: 0,
          uptime: '0h',
          accessLevel: 'private',
          ownerUserId: 'user-1',
          runtimeType: 'external_worktree',
          externalRuntime: {
            status: 'uninstalled',
            bound: false,
            availableForConversation: false,
            availableForExecution: false,
            updateAvailable: false,
          },
        }}
        isOpen={true}
        initialTab="runtime"
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText('Generate the one-line install command'),
      ).toBeInTheDocument();
    });

    expect(screen.getByText('Host Binding Status')).toBeInTheDocument();
    expect(
      screen.getByText('Optional Runtime Host access settings'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Detected from this browser: Windows'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Windows' }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('How to use this command')).toBeInTheDocument();
    expect(
      screen.getByText('Open PowerShell on the target host.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Open Projects')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update Now' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Uninstall Now' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy Uninstall Command' })).toBeInTheDocument();
  });
});
