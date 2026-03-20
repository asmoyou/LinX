import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PersistentConversationProcessLine } from '@/components/workforce/persistent/PersistentConversationProcessLine';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'zh' },
    t: (key: string, fallbackOrOptions?: string | Record<string, unknown>) =>
      typeof fallbackOrOptions === 'string' ? fallbackOrOptions : key,
  }),
}));

describe('PersistentConversationProcessLine', () => {
  it('renders a single compact phase label when visible', () => {
    render(
      <PersistentConversationProcessLine
        descriptor={{
          phase: 'using_tools',
          kind: 'tool',
          detail: 'npm run build',
          accent: 'bash',
        }}
        isVisible={true}
      />,
    );

    expect(screen.getByText('调用工具')).toBeInTheDocument();
    expect(screen.getByText('bash')).toBeInTheDocument();
    expect(screen.getByText('npm run build')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText('查看详情')).not.toBeInTheDocument();
  });

  it('renders nothing when hidden', () => {
    const { container } = render(
      <PersistentConversationProcessLine
        descriptor={{
          phase: 'thinking',
          kind: 'memory',
          detail: '命中 2 条',
          accent: 'skills',
        }}
        isVisible={false}
      />,
    );

    expect(container.firstChild).toBeNull();
  });
});
