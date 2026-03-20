import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ScheduleDetail } from '@/pages/ScheduleDetail';
import { schedulesApi } from '@/api/schedules';
import { useNotificationStore } from '@/stores/notificationStore';

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

describe('ScheduleDetail page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNotificationStore.getState().reset();

    vi.mocked(schedulesApi.getById).mockResolvedValue({
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
      lastRunAt: '2025-01-01T01:00:00+00:00',
      lastRunStatus: 'succeeded',
      lastError: null,
      createdAt: '2025-01-01T00:00:00+00:00',
      updatedAt: '2025-01-01T00:00:00+00:00',
      latestRun: null,
    } as any);

    vi.mocked(schedulesApi.listRuns).mockResolvedValue({
      items: [
        {
          id: 'run-1',
          scheduleId: 'schedule-1',
          status: 'succeeded',
          scheduledFor: '2025-01-02T01:00:00+00:00',
          completedAt: '2025-01-02T01:00:10+00:00',
          deliveryChannel: 'web',
          createdAt: '2025-01-02T01:00:00+00:00',
        },
      ],
      total: 1,
    });
  });

  it('loads the schedule detail view with recent runs', async () => {
    render(
      <MemoryRouter initialEntries={['/schedules/schedule-1']}>
        <Routes>
          <Route path="/schedules/:scheduleId" element={<ScheduleDetail />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('日报提醒')).toBeInTheDocument();
    expect(screen.getByText('查看完整排班信息、绑定会话和最近执行记录。')).toBeInTheDocument();
    expect(screen.getByText('执行内容')).toBeInTheDocument();
    expect(screen.getByText('最近运行')).toBeInTheDocument();
    expect(screen.getByText('每个工作日上午提醒我写日报')).toBeInTheDocument();
    expect(vi.mocked(schedulesApi.listRuns)).toHaveBeenCalledWith('schedule-1', { limit: 10 });
  });
});
