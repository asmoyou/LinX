import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { AgentDetailsModal } from '@/components/workforce/AgentDetailsModal';
import { agentsApi } from '@/api/agents';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, options?: Record<string, unknown>) => {
      const templates: Record<string, string> = {
        'agent.details.queueValue': '{{pending}} pending / {{running}} running',
        'agent.details.knowledgeSelected': '{{count}} selected',
      };
      const template = templates[key] ?? key;
      return template.replace(/\{\{(\w+)\}\}/g, (_, token: string) => {
        const value = options?.[token];
        return value === undefined || value === null ? '' : String(value);
      });
    },
  }),
}));

vi.mock('@/components/LayoutModal', () => ({
  LayoutModal: ({
    isOpen,
    children,
  }: {
    isOpen: boolean;
    children: React.ReactNode;
  }) => (isOpen ? <div>{children}</div> : null),
}));

vi.mock('@/api/agents', () => ({
  agentsApi: {
    getById: vi.fn(),
    getMetrics: vi.fn(),
    getLogs: vi.fn(),
  },
}));

const baseAgent = {
  id: 'agent-123',
  name: 'Report Agent',
  type: 'general',
  status: 'idle' as const,
  tasksCompleted: 0,
  uptime: '0h 0m',
};

describe('AgentDetailsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads details, metrics and logs when opened', async () => {
    vi.mocked(agentsApi.getById).mockResolvedValue({
      ...baseAgent,
      provider: 'openai',
      model: 'gpt-4o-mini',
      tasksCompleted: 6,
      tasksFailed: 2,
      tasksExecuted: 8,
      completionRate: 0.75,
      uptime: '8h 0m',
    });
    vi.mocked(agentsApi.getMetrics).mockResolvedValue({
      tasksExecuted: 8,
      tasksCompleted: 6,
      tasksFailed: 2,
      completionRate: 0.75,
      successRate: 0.75,
      failureRate: 0.25,
      pendingTasks: 3,
      inProgressTasks: 1,
      lastActivityAt: '2026-02-25T10:15:00Z',
    });
    vi.mocked(agentsApi.getLogs).mockResolvedValue([
      {
        timestamp: '2026-02-25T10:12:00Z',
        level: 'SUCCESS',
        message: 'Task completed: Finalize quarterly report',
        source: 'task',
      },
    ]);

    render(
      <AgentDetailsModal
        agent={baseAgent}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(agentsApi.getById).toHaveBeenCalledWith('agent-123');
      expect(agentsApi.getMetrics).toHaveBeenCalledWith('agent-123');
      expect(agentsApi.getLogs).toHaveBeenCalledWith('agent-123', 50);
    });

    expect(screen.getByText('3 pending / 1 running')).toBeInTheDocument();
    expect(screen.getByText('75.0%')).toBeInTheDocument();
    expect(screen.getByText('openai / gpt-4o-mini')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'agent.details.recentLogs' }));

    expect(
      await screen.findByText('Task completed: Finalize quarterly report', {}, { timeout: 10000 })
    ).toBeInTheDocument();
  });
});
