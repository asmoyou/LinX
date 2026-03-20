import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PersistentConversationAssistantMessage } from '@/components/workforce/persistent/PersistentConversationAssistantMessage';
import type { ScheduleCreatedEvent } from '@/types/schedule';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      i18n: { language: 'zh' },
      t: (key: string, fallbackOrOptions?: string | Record<string, unknown>) =>
        typeof fallbackOrOptions === 'string' ? fallbackOrOptions : key,
    }),
  };
});

vi.mock('@/components/workforce/CodeBlock', () => ({
  createMarkdownComponents: () => ({}),
}));

describe('PersistentConversationAssistantMessage', () => {
  it('renders final content with compact result actions and inline error notice', () => {
    const onOpenArtifact = vi.fn();
    const onDownloadArtifact = vi.fn();
    const scheduleItem: ScheduleCreatedEvent = {
      schedule_id: 'schedule-1',
      agent_id: 'agent-1',
      name: '日报提醒',
      status: 'active',
      next_run_at: '2025-01-02T01:00:00+00:00',
      timezone: 'Asia/Shanghai',
      created_via: 'agent_auto',
      bound_conversation_id: 'conversation-1',
      origin_surface: 'persistent_chat',
    };

    const { container } = render(
      <MemoryRouter>
        <PersistentConversationAssistantMessage
          content="最终答案 **已生成**。"
          artifactItems={[
            {
              path: '/workspace/output/report.csv',
              name: 'report.csv',
            },
          ]}
          scheduleItems={[scheduleItem]}
          errorText="network interrupted"
          onOpenArtifact={onOpenArtifact}
          onDownloadArtifact={onDownloadArtifact}
        />
      </MemoryRouter>,
    );

    expect(container.querySelector('.markdown-content')?.textContent).toContain(
      '最终答案 已生成。',
    );
    expect(screen.getByText('report.csv')).toBeInTheDocument();
    expect(screen.getByText('/workspace/output/report.csv')).toBeInTheDocument();
    expect(screen.getByText('日报提醒')).toBeInTheDocument();
    expect(screen.getByText('执行未完整完成')).toBeInTheDocument();
    expect(screen.getByText('network interrupted')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '在工作区打开' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下载' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '查看定时任务' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Operational Steps')).not.toBeInTheDocument();
    expect(screen.queryByText(/^Round$/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '在工作区打开' }));
    fireEvent.click(screen.getByRole('button', { name: '下载' }));

    expect(onOpenArtifact).toHaveBeenCalledWith('/workspace/output/report.csv');
    expect(onDownloadArtifact).toHaveBeenCalledWith(
      '/workspace/output/report.csv',
    );
  });
});
