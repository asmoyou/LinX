import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { TestAgentModal } from '@/components/workforce/TestAgentModal';

const { agentsApi, sessionWorkspacePanelSpy } = vi.hoisted(() => ({
  agentsApi: {
    downloadSessionWorkspaceFile: vi.fn(),
    endSession: vi.fn(),
    testAgent: vi.fn(),
    transcribeVoiceInput: vi.fn(),
  },
  sessionWorkspacePanelSpy: vi.fn(
    ({
      displayMode,
      isOpen,
      zIndexClassName,
    }: {
      displayMode?: 'portal' | 'embedded';
      isOpen: boolean;
      zIndexClassName?: string;
    }) =>
      isOpen ? (
        <div data-testid="workspace-panel">
          {(displayMode || 'portal') + '|' + (zIndexClassName || '')}
        </div>
      ) : null,
  ),
}));

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => undefined,
  },
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

vi.mock('@/api', () => ({
  agentsApi,
}));

vi.mock('@/stores', () => ({
  useNotificationStore: (selector: (state: { addNotification: () => void }) => unknown) =>
    selector({ addNotification: vi.fn() }),
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

vi.mock('@/components/workforce/CodeBlock', () => ({
  createMarkdownComponents: () => ({}),
}));

vi.mock('@/components/workforce/SessionWorkspacePanel', () => ({
  SessionWorkspacePanel: sessionWorkspacePanelSpy,
}));

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

describe('TestAgentModal', () => {
  beforeAll(() => {
    class ResizeObserverStub {
      observe() {}
      disconnect() {}
      unobserve() {}
    }

    Object.defineProperty(window, 'ResizeObserver', {
      writable: true,
      value: ResizeObserverStub,
    });
    Object.defineProperty(window, 'requestAnimationFrame', {
      writable: true,
      value: (callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      },
    });
    Object.defineProperty(window, 'cancelAnimationFrame', {
      writable: true,
      value: () => undefined,
    });
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      writable: true,
      value(options: ScrollToOptions) {
        if (typeof options.top === 'number') {
          this.scrollTop = options.top;
        }
      },
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
    agentsApi.endSession.mockResolvedValue({ success: true });
    agentsApi.testAgent.mockImplementation(
      async (
        _agentId: string,
        _message: string,
        onChunk: (chunk: { type: string; session_id?: string }) => void,
        _onError?: (error: string) => void,
        onComplete?: () => void,
      ) => {
        onChunk({ type: 'session', session_id: 'session-1' });
        onComplete?.();
      },
    );
  });

  afterEach(() => {
    sessionWorkspacePanelSpy.mockClear();
  });

  it('renders workspace panel as the full portal drawer for test agent sessions', async () => {
    render(
      <TestAgentModal
        agent={{
          id: 'agent-1',
          name: 'Planner',
          type: 'assistant',
          status: 'idle',
          provider: 'openai',
          model: 'gpt-4o-mini',
          tasksCompleted: 0,
          uptime: '0',
          ownerUserId: 'user-1',
        }}
        isOpen={true}
        onClose={vi.fn()}
      />,
    );

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'test workspace' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    const workspaceButton = screen.getByTitle('Workspace');
    await waitFor(() => {
      expect(workspaceButton).toBeEnabled();
    });

    fireEvent.click(workspaceButton);

    expect(await screen.findByTestId('workspace-panel')).toHaveTextContent('portal|z-[80]');
  });
});
