import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Schedules } from '@/pages/Schedules';
import { agentsApi } from '@/api';
import { schedulesApi } from '@/api/schedules';
import { useAuthStore } from '@/stores/authStore';
import { useNotificationStore } from '@/stores/notificationStore';
import { useScheduleStore } from '@/stores/scheduleStore';
import type { AgentSchedule } from '@/types/schedule';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      i18n: { language: 'zh-CN' },
      t: (_key: string, options?: string | { defaultValue?: string }) => {
        if (typeof options === 'string') {
          return options;
        }
        if (options && typeof options === 'object' && 'defaultValue' in options) {
          return options.defaultValue || _key;
        }
        return _key;
      },
    }),
  };
});

vi.mock('@/api', () => ({
  agentsApi: {
    getAll: vi.fn(),
  },
}));

vi.mock('@/api/schedules', () => ({
  schedulesApi: {
    list: vi.fn(),
    getById: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    runNow: vi.fn(),
    listRuns: vi.fn(),
    preview: vi.fn(),
  },
}));

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

const scheduleFixture: AgentSchedule = {
  id: 'schedule-1',
  ownerUserId: 'user-1',
  ownerUsername: 'alice',
  agentId: 'agent-1',
  agentName: '日报助理',
  boundConversationId: 'conversation-1',
  boundConversationTitle: '日报会话',
  boundConversationSource: 'web',
  name: '日报提醒',
  promptTemplate: '每个工作日上午提醒我写日报',
  scheduleType: 'recurring',
  cronExpression: '0 9 * * 1-5',
  runAtUtc: null,
  timezone: 'Asia/Shanghai',
  status: 'active',
  createdVia: 'agent_auto',
  originSurface: 'persistent_chat',
  originMessageId: 'message-1',
  nextRunAt: '2025-01-02T01:00:00+00:00',
  lastRunAt: null,
  lastRunStatus: null,
  lastError: null,
  createdAt: '2025-01-01T00:00:00+00:00',
  updatedAt: '2025-01-01T00:00:00+00:00',
  latestRun: null,
};

describe('Schedules page', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useNotificationStore.getState().reset();
    useScheduleStore.getState().reset();
    useAuthStore.setState({
      user: {
        id: 'user-1',
        username: 'alice',
        email: 'alice@example.com',
        role: 'admin',
      },
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });

    vi.mocked(agentsApi.getAll).mockResolvedValue([
      {
        id: 'agent-1',
        name: '日报助理',
        type: 'general',
        status: 'idle',
        tasksCompleted: 0,
        uptime: '1h',
        ownerUserId: 'user-1',
        canExecute: true,
      },
    ] as any);
    vi.mocked(schedulesApi.list).mockResolvedValue({
      items: [scheduleFixture],
      total: 1,
    });
    vi.mocked(schedulesApi.preview).mockResolvedValue({
      is_valid: true,
      human_summary: 'Every weekday at 09:00 (Asia/Shanghai)',
      normalized_cron: '0 9 * * 1-5',
      next_occurrences: ['2025-01-02T01:00:00+00:00'],
    });
  });

  it('loads schedules, supports filters, and renders modal preview', async () => {
    render(
      <MemoryRouter initialEntries={['/schedules']}>
        <Schedules />
      </MemoryRouter>
    );

    expect((await screen.findAllByText('日报提醒')).length).toBeGreaterThan(0);
    expect(vi.mocked(schedulesApi.list)).toHaveBeenCalledWith(
      expect.objectContaining({
        scope: 'mine',
        status: 'all',
        type: 'all',
        createdVia: 'all',
      })
    );

    fireEvent.change(screen.getByLabelText('筛选状态'), {
      target: { value: 'paused' },
    });

    await waitFor(() => {
      expect(vi.mocked(schedulesApi.list).mock.calls.at(-1)?.[0]).toMatchObject({
        status: 'paused',
      });
    });

    fireEvent.click(screen.getByRole('button', { name: '新建任务' }));

    expect(await screen.findByText('新建定时任务')).toBeInTheDocument();
    expect(await screen.findByText('Every weekday at 09:00 (Asia/Shanghai)')).toBeInTheDocument();
    expect(vi.mocked(schedulesApi.preview)).toHaveBeenCalled();
  }, 10000);

  it('renders compact summary cards with detail actions', async () => {
    render(
      <MemoryRouter initialEntries={['/schedules']}>
        <Schedules />
      </MemoryRouter>
    );

    expect((await screen.findAllByText('日报提醒')).length).toBeGreaterThan(0);
    expect(screen.getByText('管理手动创建和 Agent 自动创建的任务。循环任务基于 cron，触发后会继续在绑定会话内执行。')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '查看详情' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: '查看最近运行' })).not.toBeInTheDocument();
  });

  it('hides run and pause actions for terminal one-time schedules', async () => {
    vi.mocked(schedulesApi.list).mockResolvedValue({
      items: [
        {
          ...scheduleFixture,
          scheduleType: 'once',
          status: 'completed',
          runAtUtc: '2025-01-02T01:00:00+00:00',
          nextRunAt: null,
        },
      ],
      total: 1,
    });

    render(
      <MemoryRouter initialEntries={['/schedules']}>
        <Schedules />
      </MemoryRouter>
    );

    expect((await screen.findAllByText('日报提醒')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: '立即执行' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '暂停' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '编辑' }).length).toBeGreaterThan(0);
  });
});
