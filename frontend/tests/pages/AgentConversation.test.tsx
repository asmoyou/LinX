import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentConversation } from "@/pages/AgentConversation";

const { agentsApi } = vi.hoisted(() => ({
  agentsApi: {
    createConversation: vi.fn(),
    deleteConversation: vi.fn(),
    downloadConversationWorkspaceFile: vi.fn(),
    getById: vi.fn(),
    getConversation: vi.fn(),
    getConversationMessages: vi.fn(),
    getConversations: vi.fn(),
    releaseConversationRuntime: vi.fn(),
    sendConversationMessage: vi.fn(),
    transcribeVoice: vi.fn(),
    updateConversation: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string, vars?: Record<string, unknown>) => {
      if (typeof fallback === "string") {
        if (vars?.count !== undefined) {
          return fallback.replace("{{count}}", String(vars.count));
        }
        return fallback;
      }
      return key;
    },
  }),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    error: vi.fn(),
  },
}));

vi.mock("@/api", () => ({
  agentsApi,
}));

vi.mock("@/stores", () => ({
  useNotificationStore: (selector: (state: { addNotification: () => void }) => unknown) =>
    selector({ addNotification: vi.fn() }),
}));

vi.mock("@/components/workforce/CodeBlock", () => ({
  createMarkdownComponents: () => ({}),
}));

vi.mock("@/components/workforce/persistent/PersistentConversationAssistantMessage", () => ({
  PersistentConversationAssistantMessage: ({
    content,
    errorText,
  }: {
    content: string;
    errorText?: string | null;
  }) => (
    <div>
      <div>{content}</div>
      {errorText ? <div>{errorText}</div> : null}
    </div>
  ),
}));

vi.mock("@/components/workforce/persistent/PersistentConversationProcessLine", () => ({
  PersistentConversationProcessLine: () => null,
}));

vi.mock("@/components/workforce/persistent/persistentConversationHelpers", () => ({
  derivePersistentArtifacts: () => [],
  derivePersistentProcessDescriptor: () => null,
  derivePersistentScheduleEvents: () => [],
  getPersistentFallbackAssistantText: (message: { contentText?: string }) =>
    String(message.contentText || ""),
  mapChunkToPersistentPhase: () => null,
  mergePersistentScheduleEvents: (
    current: Record<string, unknown>[],
    next: Record<string, unknown>,
  ) => [...current, next],
  normalizeWorkspaceFilePath: (value: string) => value,
  shouldHideProcessLine: () => false,
}));

vi.mock("@/components/workforce/SessionWorkspacePanel", () => ({
  SessionWorkspacePanel: () => <div>workspace</div>,
}));

describe("AgentConversation", () => {
  afterEach(() => {
    cleanup();
  });

  beforeAll(() => {
    class ResizeObserverStub {
      observe() {}
      disconnect() {}
      unobserve() {}
    }

    Object.defineProperty(window, "ResizeObserver", {
      writable: true,
      value: ResizeObserverStub,
    });
    Object.defineProperty(window, "requestAnimationFrame", {
      writable: true,
      value: (callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      },
    });
    Object.defineProperty(window, "cancelAnimationFrame", {
      writable: true,
      value: () => undefined,
    });
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      writable: true,
      value(options: ScrollToOptions) {
        if (typeof options.top === "number") {
          this.scrollTop = options.top;
        }
      },
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
    agentsApi.getById.mockResolvedValue({
      id: "agent-1",
      name: "Planner",
      type: "assistant",
      status: "idle",
      tasksCompleted: 0,
      uptime: "0",
      ownerUserId: "user-1",
    });
    agentsApi.getConversation.mockResolvedValue({
      id: "conversation-current",
      agentId: "agent-1",
      ownerUserId: "user-1",
      title: "Deep link current",
      status: "active",
      source: "web",
      compactedMessageCount: 12,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:10:00Z",
    });
    agentsApi.releaseConversationRuntime.mockResolvedValue(undefined);
  });

  function renderPage() {
    return render(
      <MemoryRouter
        initialEntries={["/workforce/agent-1/conversations/conversation-current"]}
      >
        <Routes>
          <Route
            path="/workforce/:agentId/conversations/:conversationId"
            element={<AgentConversation />}
          />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("loads paged conversation and message data on first render", async () => {
    agentsApi.getConversations.mockResolvedValue({
      items: Array.from({ length: 30 }, (_, index) => ({
        id: `conversation-${index}`,
        agentId: "agent-1",
        ownerUserId: "user-1",
        title: `Conversation ${index}`,
        status: "active",
        source: "web",
        lastMessagePreview: `Preview ${index}`,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      })),
      total: 42,
      hasMore: true,
      nextCursor: "cursor-1",
    });
    agentsApi.getConversationMessages.mockResolvedValue({
      items: [
        {
          id: "message-1",
          conversationId: "conversation-current",
          role: "user",
          contentText: "hello",
          attachments: [],
          source: "web",
          createdAt: "2026-01-01T00:00:00Z",
        },
      ],
      total: 1,
      historySummary: null,
      compactedMessageCount: 12,
      archivedSegmentCount: 1,
      recentWindowSize: 40,
      hasOlderLiveMessages: true,
      olderCursor: "older-1",
    });

    renderPage();

    await screen.findAllByText("Deep link current");

    expect(agentsApi.getConversations).toHaveBeenCalledWith("agent-1", {
      limit: 30,
    });
    expect(agentsApi.getConversationMessages).toHaveBeenCalledWith(
      "agent-1",
      "conversation-current",
      { limit: 50 },
    );
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getAllByText("Deep link current").length).toBeGreaterThanOrEqual(
      2,
    );
  });

  it("loads older live messages at the top and only shows compacted summary after live history is exhausted", async () => {
    agentsApi.getConversations.mockResolvedValue({
      items: [],
      total: 1,
      hasMore: false,
      nextCursor: null,
    });
    agentsApi.getConversationMessages
      .mockResolvedValueOnce({
        items: [
          {
            id: "message-newer",
            conversationId: "conversation-current",
            role: "assistant",
            contentText: "newer",
            attachments: [],
            source: "web",
            createdAt: "2026-01-01T00:02:00Z",
          },
        ],
        total: 1,
        historySummary: {
          summaryText: "Goals:\n- preserved",
          rawMessageCount: 12,
        },
        compactedMessageCount: 12,
        archivedSegmentCount: 1,
        recentWindowSize: 40,
        hasOlderLiveMessages: true,
        olderCursor: "older-1",
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: "message-older",
            conversationId: "conversation-current",
            role: "user",
            contentText: "older",
            attachments: [],
            source: "web",
            createdAt: "2026-01-01T00:01:00Z",
          },
        ],
        total: 1,
        historySummary: {
          summaryText: "Goals:\n- preserved",
          rawMessageCount: 12,
        },
        compactedMessageCount: 12,
        archivedSegmentCount: 1,
        recentWindowSize: 40,
        hasOlderLiveMessages: false,
        olderCursor: null,
      });

    const { getByTestId, queryByTestId } = renderPage();

    await screen.findByText("newer");
    expect(queryByTestId("compacted-history-summary")).not.toBeInTheDocument();

    const scrollContainer = getByTestId("conversation-messages-scroll");
    let scrollHeight = 400;
    Object.defineProperty(scrollContainer, "clientHeight", {
      configurable: true,
      value: 200,
    });
    Object.defineProperty(scrollContainer, "scrollHeight", {
      configurable: true,
      get: () => scrollHeight,
    });
    scrollContainer.scrollTop = 0;

    fireEvent.scroll(scrollContainer);

    await waitFor(() => {
      expect(agentsApi.getConversationMessages).toHaveBeenLastCalledWith(
        "agent-1",
        "conversation-current",
        { limit: 50, before: "older-1" },
      );
    });

    scrollHeight = 700;

    await screen.findByText("older");
    await waitFor(() => {
      expect(queryByTestId("compacted-history-summary")).toBeInTheDocument();
    });
  });

  it("loads more conversations when the sidebar reaches the bottom", async () => {
    agentsApi.getConversations
      .mockResolvedValueOnce({
        items: Array.from({ length: 30 }, (_, index) => ({
          id: `conversation-${index}`,
          agentId: "agent-1",
          ownerUserId: "user-1",
          title: `Conversation ${index}`,
          status: "active",
          source: "web",
          lastMessagePreview: `Preview ${index}`,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
        })),
        total: 35,
        hasMore: true,
        nextCursor: "cursor-next",
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: "conversation-31",
            agentId: "agent-1",
            ownerUserId: "user-1",
            title: "Conversation 31",
            status: "active",
            source: "web",
            lastMessagePreview: "Preview 31",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
          },
        ],
        total: 35,
        hasMore: false,
        nextCursor: null,
      });
    agentsApi.getConversationMessages.mockResolvedValue({
      items: [],
      total: 0,
      historySummary: null,
      compactedMessageCount: 0,
      archivedSegmentCount: 0,
      recentWindowSize: 40,
      hasOlderLiveMessages: false,
      olderCursor: null,
    });

    const { getByTestId } = renderPage();

    await screen.findByText("Conversation 0");

    const scrollContainer = getByTestId("conversation-list-scroll");
    Object.defineProperty(scrollContainer, "clientHeight", {
      configurable: true,
      value: 200,
    });
    Object.defineProperty(scrollContainer, "scrollHeight", {
      configurable: true,
      value: 320,
    });
    scrollContainer.scrollTop = 140;

    fireEvent.scroll(scrollContainer);

    await waitFor(() => {
      expect(agentsApi.getConversations).toHaveBeenLastCalledWith("agent-1", {
        limit: 30,
        cursor: "cursor-next",
      });
    });

    await screen.findByText("Conversation 31");
  }, 10000);

  it("does not release runtime when the page becomes hidden", async () => {
    agentsApi.getConversations.mockResolvedValue({
      items: [],
      total: 1,
      hasMore: false,
      nextCursor: null,
    });
    agentsApi.getConversationMessages.mockResolvedValue({
      items: [],
      total: 0,
      historySummary: null,
      compactedMessageCount: 0,
      archivedSegmentCount: 0,
      recentWindowSize: 40,
      hasOlderLiveMessages: false,
      olderCursor: null,
    });

    renderPage();
    await screen.findAllByText("Deep link current");

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));

    expect(agentsApi.releaseConversationRuntime).not.toHaveBeenCalled();
  });

  it("does not release runtime while a message send is still in progress", async () => {
    agentsApi.getConversations.mockResolvedValue({
      items: [],
      total: 1,
      hasMore: false,
      nextCursor: null,
    });
    agentsApi.getConversationMessages.mockResolvedValue({
      items: [],
      total: 0,
      historySummary: null,
      compactedMessageCount: 0,
      archivedSegmentCount: 0,
      recentWindowSize: 40,
      hasOlderLiveMessages: false,
      olderCursor: null,
    });
    agentsApi.sendConversationMessage.mockImplementation(
      () => new Promise<void>(() => undefined),
    );

    const view = renderPage();
    const textarea = await screen.findByPlaceholderText(
      "Send a message to this agent",
    );

    fireEvent.change(textarea, { target: { value: "hello" } });
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(agentsApi.sendConversationMessage).toHaveBeenCalled();
    });
    await screen.findByPlaceholderText("Thinking...");

    view.unmount();

    expect(agentsApi.releaseConversationRuntime).not.toHaveBeenCalled();
  });

});
