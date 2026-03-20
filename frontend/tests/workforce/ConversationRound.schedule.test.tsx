import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ConversationRoundComponent } from '@/components/workforce/ConversationRound';
import type { ConversationRound } from '@/types/streaming';

vi.mock('@/components/workforce/CodeBlock', () => ({
  createMarkdownComponents: () => ({}),
}));

describe('ConversationRound schedule cards', () => {
  it('renders schedule-created cards from round data', () => {
    const round: ConversationRound = {
      roundNumber: 1,
      thinking: '',
      content: '',
      statusMessages: [],
      scheduleEvents: [
        {
          schedule_id: 'schedule-1',
          agent_id: 'agent-1',
          name: '日报提醒',
          status: 'active',
          next_run_at: '2025-01-02T01:00:00+00:00',
          timezone: 'Asia/Shanghai',
          created_via: 'agent_auto',
          bound_conversation_id: 'conversation-1',
          bound_conversation_title: '日报会话',
          origin_surface: 'persistent_chat',
        },
      ],
    };

    render(
      <MemoryRouter>
        <ConversationRoundComponent round={round} />
      </MemoryRouter>
    );

    expect(screen.getByText('定时任务已创建')).toBeInTheDocument();
    expect(screen.getByText('日报提醒')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看定时任务' })).toBeInTheDocument();
  });
});
