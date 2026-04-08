import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  FolderOpen,
  Image as ImageIcon,
  Loader2,
  MessageSquarePlus,
  Mic,
  Paperclip,
  Pencil,
  Send,
  Square,
  Trash2,
  X as XIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";

import { agentsApi } from "@/api";
import { createMarkdownComponents } from "@/components/workforce/CodeBlock";
import { PersistentConversationAssistantMessage } from "@/components/workforce/persistent/PersistentConversationAssistantMessage";
import { PersistentConversationProcessLine } from "@/components/workforce/persistent/PersistentConversationProcessLine";
import {
  derivePersistentArtifacts,
  derivePersistentProcessDescriptor,
  derivePersistentScheduleEvents,
  getPersistentFallbackAssistantText,
  mapChunkToPersistentPhase,
  mergePersistentScheduleEvents,
  normalizeWorkspaceFilePath,
  shouldHideProcessLine,
  type PersistentConversationArtifactItem,
  type PersistentConversationPhase,
  type PersistentProcessDescriptor,
} from "@/components/workforce/persistent/persistentConversationHelpers";
import { SessionWorkspacePanel } from "@/components/workforce/SessionWorkspacePanel";
import { useMeasuredVirtualWindow } from "@/hooks/useMeasuredVirtualWindow";
import { useNotificationStore } from "@/stores";
import type {
  Agent,
  AgentConversationDetail,
  AgentConversationHistorySummary,
  AgentConversationSummary,
  ConversationMessage,
} from "@/types/agent";
import type { AttachedFile } from "@/types/streaming";
import type { ScheduleCreatedEvent } from "@/types/schedule";

const ATTACHMENT_ACCEPT_TYPES =
  "image/*,.pdf,.doc,.docx,.pptx,.xls,.xlsx,.txt,.md,.markdown,.html,.htm,.csv";
const STREAM_RENDER_THROTTLE_MS = 60;
const AUTO_SCROLL_THRESHOLD_PX = 120;
const HISTORY_MESSAGE_GAP_PX = 32;
const HISTORY_MESSAGE_ESTIMATED_HEIGHT_PX = 320;
const HISTORY_OVERSCAN_PX = 900;
const HISTORY_VIRTUALIZATION_MIN_ITEMS = 24;
const CONVERSATION_LIST_PAGE_SIZE = 30;
const CONVERSATION_LIST_LOAD_MORE_THRESHOLD_PX = 160;
const CONVERSATION_LIST_ESTIMATED_HEIGHT_PX = 112;
const CONVERSATION_LIST_OVERSCAN_PX = 480;
const CONVERSATION_LIST_VIRTUALIZATION_MIN_ITEMS = 18;
const MESSAGE_PAGE_SIZE = 50;
const MESSAGE_LOAD_MORE_THRESHOLD_PX = 80;
const INITIAL_BOTTOM_ANCHOR_SCROLL_TOP = Number.MAX_SAFE_INTEGER;

interface ConversationListState {
  hasMore: boolean;
  isLoadingMore: boolean;
  items: AgentConversationSummary[];
  nextCursor: string | null;
  total: number;
}

interface MessageListState {
  hasOlderLiveMessages: boolean;
  isLoadingOlder: boolean;
  items: ConversationMessage[];
  olderCursor: string | null;
}

const EMPTY_CONVERSATION_LIST_STATE: ConversationListState = {
  items: [],
  total: 0,
  hasMore: false,
  nextCursor: null,
  isLoadingMore: false,
};

const EMPTY_MESSAGE_LIST_STATE: MessageListState = {
  items: [],
  hasOlderLiveMessages: false,
  olderCursor: null,
  isLoadingOlder: false,
};

interface StreamingViewState {
  assistantText: string;
  phase: PersistentConversationPhase | null;
  processDescriptor: PersistentProcessDescriptor | null;
  hasContentStarted: boolean;
  inlineError: string | null;
  scheduleEvents: ScheduleCreatedEvent[];
}

function createEmptyStreamingViewState(): StreamingViewState {
  return {
    assistantText: "",
    phase: null,
    processDescriptor: null,
    hasContentStarted: false,
    inlineError: null,
    scheduleEvents: [],
  };
}

function downloadBlob(blob: Blob, fileName: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

function buildAttachmentPreview(file: File): AttachedFile {
  const type: AttachedFile["type"] = file.type.startsWith("image/")
    ? "image"
    : file.type.includes("pdf") ||
        file.type.includes("text") ||
        file.type.includes("json")
      ? "document"
      : "other";
  return {
    id: `${file.name}-${file.size}-${file.lastModified}`,
    file,
    preview: type === "image" ? URL.createObjectURL(file) : undefined,
    type,
  };
}

interface MeasuredVirtualItemProps {
  gapPx?: number;
  index: number;
  onHeightChange: (index: number, height: number) => void;
  children: React.ReactNode;
}

const MeasuredVirtualItem: React.FC<MeasuredVirtualItemProps> = ({
  gapPx = HISTORY_MESSAGE_GAP_PX,
  index,
  onHeightChange,
  children,
}) => {
  const itemRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = itemRef.current;
    if (!element) return;

    const updateHeight = () => {
      onHeightChange(index, element.getBoundingClientRect().height);
    };

    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [index, onHeightChange]);

  return (
    <div ref={itemRef} style={{ paddingBottom: `${gapPx}px` }}>
      {children}
    </div>
  );
};

type ConversationMessageRowProps = {
  downloadingArtifactPath: string | null;
  generatedOutputLabel: string;
  message: ConversationMessage;
  onDownloadArtifact: (path: string) => Promise<void>;
  onOpenArtifact: (path: string) => void;
};

const ConversationMessageRow = React.memo<ConversationMessageRowProps>(
  ({
    downloadingArtifactPath,
    generatedOutputLabel,
    message,
    onDownloadArtifact,
    onOpenArtifact,
  }) => {
    if (message.role === "user") {
      return (
        <div className="flex justify-end">
          <div className="max-w-[80%] rounded-[28px] rounded-tr-none bg-emerald-600 px-5 py-4 text-white shadow-lg shadow-emerald-500/10">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {message.contentText}
            </p>
            {message.attachments.length > 0 && (
              <div className="mt-3 grid gap-2">
                {message.attachments.map((attachment, index) => (
                  <div
                    key={`${message.id}-attachment-${index}`}
                    className="rounded-xl border border-white/15 bg-white/10 px-3 py-2"
                  >
                    <p className="text-xs font-semibold">
                      {String(
                        attachment.name || attachment.file_name || "Attachment",
                      )}
                    </p>
                    <p className="text-[11px] opacity-80">
                      {String(
                        attachment.type || attachment.content_type || "",
                      )}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      );
    }

    if (message.role === "system") {
      return (
        <div className="flex justify-center">
          <div className="rounded-full border border-zinc-200/80 bg-zinc-100 px-5 py-2 dark:border-zinc-800/80 dark:bg-zinc-900/50">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-500">
              {message.contentText}
            </p>
          </div>
        </div>
      );
    }

    const artifactItems = derivePersistentArtifacts(
      message,
    ) as PersistentConversationArtifactItem[];
    const scheduleItems = derivePersistentScheduleEvents(message);
    const displayContent = getPersistentFallbackAssistantText(
      message,
      generatedOutputLabel,
    );
    const inlineError =
      typeof message.contentJson?.inlineError === "string"
        ? message.contentJson.inlineError
        : null;

    return (
      <PersistentConversationAssistantMessage
        content={displayContent}
        artifactItems={artifactItems}
        scheduleItems={scheduleItems}
        errorText={inlineError}
        onOpenArtifact={onOpenArtifact}
        onDownloadArtifact={onDownloadArtifact}
        downloadingArtifactPath={downloadingArtifactPath}
      />
    );
  },
);

type ConversationListItemCardProps = {
  activeConversationId: string;
  deletingConversationIds: Set<string>;
  item: AgentConversationSummary;
  noMessagesLabel: string;
  onDeleteConversation: (item: AgentConversationSummary) => void;
  onOpenConversation: (conversationId: string) => void;
  onRenameConversation: (item: AgentConversationSummary) => void;
};

const ConversationListItemCard = React.memo<ConversationListItemCardProps>(
  ({
    activeConversationId,
    deletingConversationIds,
    item,
    noMessagesLabel,
    onDeleteConversation,
    onOpenConversation,
    onRenameConversation,
  }) => (
    <div
      className={`flex items-start justify-between gap-3 rounded-2xl border px-3 py-3 transition-colors ${
        item.id === activeConversationId
          ? "border-emerald-500 bg-emerald-500/10"
          : "border-zinc-200 bg-zinc-50 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950/60 dark:hover:bg-zinc-800/80"
      }`}
    >
      <button
        type="button"
        onClick={() => onOpenConversation(item.id)}
        className="min-w-0 flex-1 text-left"
      >
        <p className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {item.title}
        </p>
        <p className="mt-1 line-clamp-2 text-xs text-zinc-500 dark:text-zinc-400">
          {item.lastMessagePreview || noMessagesLabel}
        </p>
        <div className="mt-2 flex items-center gap-2">
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
            {item.source}
          </span>
          {item.storageTier && item.storageTier !== "hot" && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
              {item.storageTier}
            </span>
          )}
          {item.latestSnapshotStatus && (
            <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
              {item.latestSnapshotStatus}
            </span>
          )}
        </div>
      </button>
      <div className="flex shrink-0 flex-col gap-1">
        <button
          type="button"
          onClick={() => onRenameConversation(item)}
          className="rounded-lg p-1 text-zinc-400 transition-colors hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={() => onDeleteConversation(item)}
          disabled={deletingConversationIds.has(item.id)}
          className="rounded-lg p-1 text-zinc-400 transition-colors hover:bg-red-100 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-red-950/40 dark:hover:text-red-400"
        >
          {deletingConversationIds.has(item.id) ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Trash2 className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
    </div>
  ),
);

function mergeConversationIntoList(
  items: AgentConversationSummary[],
  conversationItem: AgentConversationSummary | AgentConversationDetail | null,
): AgentConversationSummary[] {
  if (!conversationItem) {
    return items;
  }
  if (items.some((item) => item.id === conversationItem.id)) {
    return items;
  }
  const deduped = items.filter((item) => item.id !== conversationItem.id);
  return [conversationItem, ...deduped];
}

function buildConversationListState(
  items: AgentConversationSummary[],
  options?: {
    activeConversation?: AgentConversationSummary | AgentConversationDetail | null;
    hasMore?: boolean;
    isLoadingMore?: boolean;
    nextCursor?: string | null;
    total?: number;
  },
): ConversationListState {
  return {
    items: mergeConversationIntoList(items, options?.activeConversation ?? null),
    total: options?.total ?? items.length,
    hasMore: options?.hasMore ?? false,
    nextCursor: options?.nextCursor ?? null,
    isLoadingMore: options?.isLoadingMore ?? false,
  };
}

function buildMessageListState(
  items: ConversationMessage[],
  options?: {
    hasOlderLiveMessages?: boolean;
    isLoadingOlder?: boolean;
    olderCursor?: string | null;
  },
): MessageListState {
  return {
    items,
    hasOlderLiveMessages: options?.hasOlderLiveMessages ?? false,
    olderCursor: options?.olderCursor ?? null,
    isLoadingOlder: options?.isLoadingOlder ?? false,
  };
}

export const AgentConversation: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { agentId = "", conversationId = "" } = useParams();
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);
  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const addNotification = useNotificationStore(
    (state) => state.addNotification,
  );
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const conversationListContainerRef = useRef<HTMLDivElement | null>(null);
  const historyPrefixRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isSendingRef = useRef(false);
  const attachedFilesRef = useRef<AttachedFile[]>([]);
  const activeConversationRef = useRef<{
    agentId?: string;
    conversationId?: string;
  }>({});
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const recordingStreamRef = useRef<MediaStream | null>(null);
  const abortStreamingHandlerRef = useRef<(() => void) | null>(null);
  const streamFlushTimerRef = useRef<number | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const initialHistoryAnchorPendingRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const messageScrollFrameRef = useRef<number | null>(null);
  const conversationListScrollFrameRef = useRef<number | null>(null);
  const conversationListStateRef =
    useRef<ConversationListState>(EMPTY_CONVERSATION_LIST_STATE);
  const messageListStateRef = useRef<MessageListState>(EMPTY_MESSAGE_LIST_STATE);
  const pendingPrependScrollAdjustmentRef = useRef<{
    previousScrollHeight: number;
    previousScrollTop: number;
  } | null>(null);
  const streamingViewRef = useRef<StreamingViewState>(
    createEmptyStreamingViewState(),
  );

  const [agent, setAgent] = useState<Agent | null>(null);
  const [conversationListState, setConversationListState] =
    useState<ConversationListState>(EMPTY_CONVERSATION_LIST_STATE);
  const [conversation, setConversation] =
    useState<AgentConversationDetail | null>(null);
  const [messageListState, setMessageListState] =
    useState<MessageListState>(EMPTY_MESSAGE_LIST_STATE);
  const [historySummary, setHistorySummary] =
    useState<AgentConversationHistorySummary | null>(null);
  const [inputMessage, setInputMessage] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [isTranscribingVoice, setIsTranscribingVoice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWorkspacePanel, setShowWorkspacePanel] = useState(false);
  const [workspaceFocusPath, setWorkspaceFocusPath] = useState<string | null>(
    null,
  );
  const [downloadingArtifactPath, setDownloadingArtifactPath] = useState<
    string | null
  >(null);
  const [streamingAssistantText, setStreamingAssistantText] = useState("");
  const [streamingPhase, setStreamingPhase] =
    useState<PersistentConversationPhase | null>(null);
  const [streamingProcessDescriptor, setStreamingProcessDescriptor] =
    useState<PersistentProcessDescriptor | null>(null);
  const [hasStreamingContentStarted, setHasStreamingContentStarted] =
    useState(false);
  const [streamingInlineError, setStreamingInlineError] = useState<
    string | null
  >(null);
  const [streamingScheduleItems, setStreamingScheduleItems] = useState<
    ScheduleCreatedEvent[]
  >([]);
  const [draftConversationId, setDraftConversationId] = useState<string | null>(
    null,
  );
  const [, setIsCreatingConversation] = useState(false);
  const [pendingConversationTitle, setPendingConversationTitle] = useState<
    string | null
  >(null);
  const [showDraftPlaceholder, setShowDraftPlaceholder] = useState(false);
  const [deletingConversationIds, setDeletingConversationIds] = useState<
    Set<string>
  >(new Set());
  const [messagesScrollTop, setMessagesScrollTop] = useState(0);
  const [messagesViewportHeight, setMessagesViewportHeight] = useState(0);
  const [historyPrefixHeight, setHistoryPrefixHeight] = useState(0);
  const [conversationListScrollTop, setConversationListScrollTop] = useState(0);
  const [conversationListViewportHeight, setConversationListViewportHeight] =
    useState(0);

  const activeConversationId = conversationId || draftConversationId || "";
  const conversations = conversationListState.items;
  const messages = messageListState.items;
  const isExternalRuntimeBlocked = Boolean(
    agent?.externalRuntime && !agent.externalRuntime.availableForConversation,
  );
  const externalRuntimeSetupHref = agentId
    ? `/workforce?configureAgent=${encodeURIComponent(agentId)}&tab=runtime`
    : "/workforce";
  const externalRuntimeBlockedMessage = useMemo(() => {
    const runtime = agent?.externalRuntime;
    if (!runtime) {
      return t(
        "agent.externalRuntimeBlockedConversation",
        "This external agent is not online yet. Install or reconnect its host before chatting.",
      );
    }
    if (runtime.runtimeCompatible === false || runtime.status === "upgrade_required") {
      return t(
        "agent.externalRuntimeBlockedConversationUpgradeRequired",
        "This external agent's Runtime Host must be upgraded before web chat can run on that machine.",
      );
    }
    switch (runtime.status) {
      case "uninstalled":
        return t(
          "agent.externalRuntimeBlockedConversationUninstalled",
          "This external agent has not been installed on a Runtime Host yet.",
        );
      case "offline":
        return t(
          "agent.externalRuntimeBlockedConversationOffline",
          "This external agent is currently offline. Reconnect its Runtime Host before chatting.",
        );
      case "error":
        return (
          runtime.lastErrorMessage ||
          t(
            "agent.externalRuntimeBlockedConversationError",
            "This external agent reported a Runtime Host error.",
          )
        );
      case "upgrade_required":
        return (
          runtime.compatibilityMessage ||
          t(
            "agent.externalRuntimeBlockedConversationUpgradeRequired",
            "This external agent's Runtime Host must be upgraded before web chat can run on that machine.",
          )
        );
      default:
        return t(
          "agent.externalRuntimeBlockedConversation",
          "This external agent is not online yet. Install or reconnect its host before chatting.",
        );
    }
  }, [agent?.externalRuntime, t]);

  const loadConversationData = useCallback(async () => {
    if (!agentId) {
      return;
    }

    setIsLoading(true);
    try {
      const [agentData, listData, detailData, messagesData] = await Promise.all(
        [
          agentsApi.getById(agentId),
          agentsApi.getConversations(agentId, {
            limit: CONVERSATION_LIST_PAGE_SIZE,
          }),
          conversationId
            ? agentsApi.getConversation(agentId, conversationId)
            : Promise.resolve(null),
          conversationId
            ? agentsApi.getConversationMessages(agentId, conversationId, {
                limit: MESSAGE_PAGE_SIZE,
              })
            : Promise.resolve(null),
        ],
      );
      setAgent(agentData);
      setConversation(detailData);
      const nextConversationListState = buildConversationListState(
        listData.items,
        {
          activeConversation: conversationId ? detailData : null,
          hasMore: listData.hasMore,
          nextCursor: listData.nextCursor || null,
          total: listData.total,
        },
      );
      const nextMessageListState = buildMessageListState(
        messagesData?.items || [],
        {
          hasOlderLiveMessages: messagesData?.hasOlderLiveMessages || false,
          olderCursor: messagesData?.olderCursor || null,
        },
      );
      conversationListStateRef.current = nextConversationListState;
      messageListStateRef.current = nextMessageListState;
      setConversationListState(nextConversationListState);
      setMessageListState(nextMessageListState);
      setHistorySummary(messagesData?.historySummary || null);
      setPendingConversationTitle(detailData?.title || null);
      setError(null);
    } catch (loadError) {
      console.error("Failed to load conversation data:", loadError);
      const message =
        loadError instanceof Error
          ? loadError.message
          : "Failed to load conversation";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [agentId, conversationId]);

  useEffect(() => {
    void loadConversationData();
  }, [loadConversationData]);

  const loadMoreConversations = useCallback(async () => {
    if (!agentId) {
      return;
    }

    const currentListState = conversationListStateRef.current;
    if (
      currentListState.isLoadingMore ||
      !currentListState.hasMore ||
      !currentListState.nextCursor
    ) {
      return;
    }
    const cursorToLoad = currentListState.nextCursor;
    setConversationListState((prev) => {
      const nextState = {
        ...prev,
        isLoadingMore: true,
      };
      conversationListStateRef.current = nextState;
      return nextState;
    });

    try {
      const nextPage = await agentsApi.getConversations(agentId, {
        limit: CONVERSATION_LIST_PAGE_SIZE,
        cursor: cursorToLoad,
      });
      setConversationListState((prev) => {
        const existingIds = new Set(prev.items.map((item) => item.id));
        const appendedItems = nextPage.items.filter(
          (item) => !existingIds.has(item.id),
        );
        const nextState = {
          ...prev,
          items: [...prev.items, ...appendedItems],
          total: nextPage.total,
          hasMore: nextPage.hasMore,
          nextCursor: nextPage.nextCursor || null,
          isLoadingMore: false,
        };
        conversationListStateRef.current = nextState;
        return nextState;
      });
    } catch (loadMoreError) {
      console.error("Failed to load more conversations:", loadMoreError);
      setConversationListState((prev) => {
        const nextState = {
          ...prev,
          isLoadingMore: false,
        };
        conversationListStateRef.current = nextState;
        return nextState;
      });
    }
  }, [agentId]);

  const loadOlderMessages = useCallback(async () => {
    if (!agentId || !activeConversationId) {
      return;
    }

    const currentMessageListState = messageListStateRef.current;
    if (
      currentMessageListState.isLoadingOlder ||
      !currentMessageListState.hasOlderLiveMessages ||
      !currentMessageListState.olderCursor
    ) {
      return;
    }
    const olderCursorToLoad = currentMessageListState.olderCursor;
    setMessageListState((prev) => {
      const nextState = {
        ...prev,
        isLoadingOlder: true,
      };
      messageListStateRef.current = nextState;
      return nextState;
    });

    const container = messagesContainerRef.current;
    const previousScrollHeight = container?.scrollHeight || 0;
    const previousScrollTop = container?.scrollTop || 0;

    try {
      const olderPage = await agentsApi.getConversationMessages(
        agentId,
        activeConversationId,
        {
          limit: MESSAGE_PAGE_SIZE,
          before: olderCursorToLoad,
        },
      );
      setHistorySummary(olderPage.historySummary || null);
      setMessageListState((prev) => {
        const existingIds = new Set(prev.items.map((item) => item.id));
        const prependedItems = olderPage.items.filter(
          (item) => !existingIds.has(item.id),
        );
        if (prependedItems.length > 0) {
          pendingPrependScrollAdjustmentRef.current = {
            previousScrollHeight,
            previousScrollTop,
          };
        }
        const nextState = {
          items: [...prependedItems, ...prev.items],
          hasOlderLiveMessages: olderPage.hasOlderLiveMessages || false,
          olderCursor: olderPage.olderCursor || null,
          isLoadingOlder: false,
        };
        messageListStateRef.current = nextState;
        return nextState;
      });
    } catch (loadOlderError) {
      console.error("Failed to load older messages:", loadOlderError);
      setMessageListState((prev) => {
        const nextState = {
          ...prev,
          isLoadingOlder: false,
        };
        messageListStateRef.current = nextState;
        return nextState;
      });
    }
  }, [activeConversationId, agentId]);

  useEffect(() => {
    attachedFilesRef.current = attachedFiles;
  }, [attachedFiles]);

  useEffect(() => {
    isSendingRef.current = isSending;
  }, [isSending]);

  useEffect(() => {
    conversationListStateRef.current = conversationListState;
  }, [conversationListState]);

  useEffect(() => {
    messageListStateRef.current = messageListState;
  }, [messageListState]);

  useEffect(() => {
    activeConversationRef.current = {
      agentId: agentId || undefined,
      conversationId: activeConversationId || undefined,
    };
  }, [activeConversationId, agentId]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [inputMessage]);

  useEffect(() => {
    const releaseRuntime = () => {
      if (isSendingRef.current || abortControllerRef.current) {
        return;
      }
      const currentAgentId = activeConversationRef.current.agentId;
      const currentConversationId =
        activeConversationRef.current.conversationId;
      if (!currentAgentId || !currentConversationId) {
        return;
      }
      void agentsApi
        .releaseConversationRuntime(currentAgentId, currentConversationId)
        .catch(() => undefined);
    };

    const handlePageHide = () => {
      releaseRuntime();
    };

    window.addEventListener("pagehide", handlePageHide);

    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      releaseRuntime();
    };
  }, []);

  useEffect(() => {
    return () => {
      attachedFilesRef.current.forEach((file) => {
        if (file.preview) {
          URL.revokeObjectURL(file.preview);
        }
      });
    };
  }, []);

  useEffect(() => {
    if (conversationId) {
      setDraftConversationId(null);
      setIsCreatingConversation(false);
      setShowDraftPlaceholder(false);
    }
  }, [conversationId]);

  const syncStreamingStateToView = useCallback(() => {
    const {
      assistantText,
      phase,
      processDescriptor,
      hasContentStarted,
      inlineError,
      scheduleEvents,
    } = streamingViewRef.current;
    setStreamingAssistantText(assistantText);
    setStreamingPhase(phase);
    setStreamingProcessDescriptor(processDescriptor);
    setHasStreamingContentStarted(hasContentStarted);
    setStreamingInlineError(inlineError);
    setStreamingScheduleItems([...scheduleEvents]);
  }, []);

  const scheduleStreamingStateSync = useCallback(
    (immediate = false) => {
      if (immediate) {
        if (streamFlushTimerRef.current !== null) {
          window.clearTimeout(streamFlushTimerRef.current);
          streamFlushTimerRef.current = null;
        }
        syncStreamingStateToView();
        return;
      }

      if (streamFlushTimerRef.current !== null) {
        return;
      }

      streamFlushTimerRef.current = window.setTimeout(() => {
        streamFlushTimerRef.current = null;
        syncStreamingStateToView();
      }, STREAM_RENDER_THROTTLE_MS);
    },
    [syncStreamingStateToView],
  );

  const scrollMessagesToBottom = useCallback(
    (behavior: ScrollBehavior = "auto") => {
      const container = messagesContainerRef.current;
      if (!container) return;
      container.scrollTo({ top: container.scrollHeight, behavior });
    },
    [],
  );

  const historyVirtualization = useMeasuredVirtualWindow({
    estimatedItemHeight: HISTORY_MESSAGE_ESTIMATED_HEIGHT_PX,
    itemCount: messages.length,
    overscan: HISTORY_OVERSCAN_PX,
    prefixHeight: historyPrefixHeight,
    scrollTop: messagesScrollTop,
    viewportHeight: messagesViewportHeight,
  });
  const conversationListVirtualization = useMeasuredVirtualWindow({
    estimatedItemHeight: CONVERSATION_LIST_ESTIMATED_HEIGHT_PX,
    itemCount: conversations.length,
    overscan: CONVERSATION_LIST_OVERSCAN_PX,
    scrollTop: conversationListScrollTop,
    viewportHeight: conversationListViewportHeight,
  });

  const handleMessagesScroll = useCallback(() => {
    if (messageScrollFrameRef.current !== null) {
      return;
    }
    messageScrollFrameRef.current = window.requestAnimationFrame(() => {
      messageScrollFrameRef.current = null;
      const container = messagesContainerRef.current;
      if (!container) return;

      const currentScrollTop = container.scrollTop;
      const previousScrollTop = lastScrollTopRef.current;
      lastScrollTopRef.current = currentScrollTop;

      setMessagesScrollTop(currentScrollTop);
      setMessagesViewportHeight(container.clientHeight);

      const distanceFromBottom =
        container.scrollHeight - currentScrollTop - container.clientHeight;
      const currentMessageListState = messageListStateRef.current;

      if (currentScrollTop < previousScrollTop - 4) {
        shouldAutoScrollRef.current = false;
      } else if (distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX) {
        shouldAutoScrollRef.current = true;
      }

      if (
        currentScrollTop <= MESSAGE_LOAD_MORE_THRESHOLD_PX &&
        currentMessageListState.hasOlderLiveMessages &&
        !currentMessageListState.isLoadingOlder
      ) {
        void loadOlderMessages();
      }
    });
  }, [loadOlderMessages]);

  const handleConversationListScroll = useCallback(() => {
    if (conversationListScrollFrameRef.current !== null) {
      return;
    }
    conversationListScrollFrameRef.current = window.requestAnimationFrame(() => {
      conversationListScrollFrameRef.current = null;
      const container = conversationListContainerRef.current;
      if (!container) return;

      setConversationListScrollTop(container.scrollTop);
      setConversationListViewportHeight(container.clientHeight);

      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      const currentConversationListState = conversationListStateRef.current;
      if (
        distanceFromBottom <= CONVERSATION_LIST_LOAD_MORE_THRESHOLD_PX &&
        currentConversationListState.hasMore &&
        !currentConversationListState.isLoadingMore
      ) {
        void loadMoreConversations();
      }
    });
  }, [loadMoreConversations]);

  const resetStreamingState = useCallback(() => {
    if (streamFlushTimerRef.current !== null) {
      window.clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }
    setStreamingAssistantText("");
    setStreamingPhase(null);
    setStreamingProcessDescriptor(null);
    setHasStreamingContentStarted(false);
    setStreamingInlineError(null);
    setStreamingScheduleItems([]);
    abortControllerRef.current = null;
    abortStreamingHandlerRef.current = null;
    streamingViewRef.current = createEmptyStreamingViewState();
  }, []);

  useEffect(
    () => () => {
      if (streamFlushTimerRef.current !== null) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
      if (messageScrollFrameRef.current !== null) {
        window.cancelAnimationFrame(messageScrollFrameRef.current);
      }
      if (conversationListScrollFrameRef.current !== null) {
        window.cancelAnimationFrame(conversationListScrollFrameRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const syncMetrics = () => {
      if (initialHistoryAnchorPendingRef.current && shouldAutoScrollRef.current) {
        container.scrollTop = container.scrollHeight;
      }
      lastScrollTopRef.current = container.scrollTop;
      setMessagesScrollTop(container.scrollTop);
      setMessagesViewportHeight(container.clientHeight);
    };

    syncMetrics();
    const observer = new ResizeObserver(syncMetrics);
    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, [activeConversationId, showWorkspacePanel]);

  useEffect(() => {
    const container = conversationListContainerRef.current;
    if (!container) return;

    const syncMetrics = () => {
      setConversationListScrollTop(container.scrollTop);
      setConversationListViewportHeight(container.clientHeight);
    };

    syncMetrics();
    const observer = new ResizeObserver(syncMetrics);
    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, [conversations.length]);

  useEffect(() => {
    const prefix = historyPrefixRef.current;
    if (!prefix) {
      setHistoryPrefixHeight(0);
      return;
    }

    const updateHeight = () => {
      setHistoryPrefixHeight(
        Math.max(0, Math.round(prefix.getBoundingClientRect().height)),
      );
    };

    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(prefix);

    return () => {
      observer.disconnect();
    };
  }, [
    historySummary,
    conversation?.compactedMessageCount,
    messageListState.hasOlderLiveMessages,
    messageListState.isLoadingOlder,
  ]);

  useEffect(() => {
    shouldAutoScrollRef.current = true;
    initialHistoryAnchorPendingRef.current = true;
    lastScrollTopRef.current = 0;
    setMessagesScrollTop(INITIAL_BOTTOM_ANCHOR_SCROLL_TOP);
    historyVirtualization.resetMeasurements();
  }, [
    activeConversationId,
    historyVirtualization.resetMeasurements,
  ]);

  useLayoutEffect(() => {
    const container = messagesContainerRef.current;
    if (!container || !initialHistoryAnchorPendingRef.current) {
      return;
    }

    container.scrollTop = container.scrollHeight;
    lastScrollTopRef.current = container.scrollTop;
    setMessagesScrollTop(container.scrollTop);
    setMessagesViewportHeight(container.clientHeight);

    if (!activeConversationId) {
      initialHistoryAnchorPendingRef.current = false;
      return;
    }

    if (isLoading) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      const currentContainer = messagesContainerRef.current;
      if (!currentContainer) {
        return;
      }
      currentContainer.scrollTop = currentContainer.scrollHeight;
      lastScrollTopRef.current = currentContainer.scrollTop;
      setMessagesScrollTop(currentContainer.scrollTop);
      setMessagesViewportHeight(currentContainer.clientHeight);
      initialHistoryAnchorPendingRef.current = false;
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [
    activeConversationId,
    historyPrefixHeight,
    historyVirtualization.bottomSpacerHeight,
    historyVirtualization.topSpacerHeight,
    isLoading,
    messages.length,
  ]);

  useEffect(() => {
    conversationListVirtualization.resetMeasurements();
  }, [conversationListVirtualization.resetMeasurements, conversations.length]);

  useEffect(() => {
    const adjustment = pendingPrependScrollAdjustmentRef.current;
    const container = messagesContainerRef.current;
    if (!adjustment || !container) {
      return;
    }
    pendingPrependScrollAdjustmentRef.current = null;
    const frameId = window.requestAnimationFrame(() => {
      const delta = container.scrollHeight - adjustment.previousScrollHeight;
      container.scrollTop = adjustment.previousScrollTop + delta;
      lastScrollTopRef.current = container.scrollTop;
      setMessagesScrollTop(container.scrollTop);
    });
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [messages.length]);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      scrollMessagesToBottom("auto");
    });
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [
    historyPrefixHeight,
    historyVirtualization.bottomSpacerHeight,
    historyVirtualization.topSpacerHeight,
    hasStreamingContentStarted,
    messages,
    scrollMessagesToBottom,
    showWorkspacePanel,
    streamingAssistantText,
    streamingInlineError,
    streamingPhase,
    streamingProcessDescriptor,
    streamingScheduleItems,
  ]);

  const handleRefreshConversation = useCallback(async () => {
    await loadConversationData();
  }, [loadConversationData]);

  const replaceConversationUrl = useCallback(
    (nextConversationId: string) => {
      if (!agentId || !nextConversationId) return;
      window.history.replaceState(
        window.history.state,
        "",
        `/workforce/${agentId}/conversations/${nextConversationId}`,
      );
    },
    [agentId],
  );

  const upsertConversationItem = useCallback(
    (nextItem: AgentConversationSummary) => {
      setConversationListState((prev) => {
        const existingIds = new Set(prev.items.map((item) => item.id));
        const deduped = prev.items.filter((item) => item.id !== nextItem.id);
        return {
          ...prev,
          items: [nextItem, ...deduped],
          total: existingIds.has(nextItem.id) ? prev.total : prev.total + 1,
        };
      });
    },
    [],
  );

  const syncConversationState = useCallback(
    async (targetConversationId: string, includeMessages = true) => {
      if (!agentId || !targetConversationId) return;
      try {
        const [listData, detailData, messagesData] = await Promise.all([
          agentsApi.getConversations(agentId, {
            limit: CONVERSATION_LIST_PAGE_SIZE,
          }),
          agentsApi.getConversation(agentId, targetConversationId),
          includeMessages
            ? agentsApi.getConversationMessages(agentId, targetConversationId, {
                limit: MESSAGE_PAGE_SIZE,
              })
            : Promise.resolve(null),
        ]);
        setConversation(detailData);
        const nextConversationListState = buildConversationListState(
          listData.items,
          {
            activeConversation: detailData,
            hasMore: listData.hasMore,
            nextCursor: listData.nextCursor || null,
            total: listData.total,
          },
        );
        conversationListStateRef.current = nextConversationListState;
        setConversationListState(nextConversationListState);
        setPendingConversationTitle(detailData.title || null);
        if (messagesData) {
          const nextMessageListState = buildMessageListState(
            messagesData.items,
            {
              hasOlderLiveMessages: messagesData.hasOlderLiveMessages || false,
              olderCursor: messagesData.olderCursor || null,
            },
          );
          messageListStateRef.current = nextMessageListState;
          setMessageListState(nextMessageListState);
          setHistorySummary(messagesData.historySummary || null);
        }
        return messagesData;
      } catch (syncError) {
        console.error("Failed to sync conversation state:", syncError);
        return null;
      }
    },
    [agentId],
  );

  const handleCreateConversation = useCallback(() => {
    if (!agentId) return;
    setAttachedFiles((prev) => {
      prev.forEach((item) => {
        if (item.preview) {
          URL.revokeObjectURL(item.preview);
        }
      });
      return [];
    });
    setConversation(null);
    messageListStateRef.current = EMPTY_MESSAGE_LIST_STATE;
    setMessageListState(EMPTY_MESSAGE_LIST_STATE);
    setHistorySummary(null);
    setInputMessage("");
    setError(null);
    setShowWorkspacePanel(false);
    setWorkspaceFocusPath(null);
    setDraftConversationId(null);
    setIsCreatingConversation(false);
    setPendingConversationTitle(null);
    setShowDraftPlaceholder(false);
    resetStreamingState();
    navigate(`/workforce/${agentId}/conversations`);
  }, [agentId, navigate, resetStreamingState]);

  const handleRenameConversation = useCallback(
    async (item: AgentConversationSummary) => {
      const nextTitle = window.prompt(
        t("agent.renameConversation", "Rename conversation"),
        item.title,
      );
      if (!nextTitle || nextTitle.trim() === item.title) {
        return;
      }
      try {
        await agentsApi.updateConversation(agentId, item.id, nextTitle.trim());
        await loadConversationData();
      } catch (renameError) {
        console.error("Failed to rename conversation:", renameError);
        toast.error(
          t("agent.renameConversationFailed", "Failed to rename conversation"),
        );
      }
    },
    [agentId, loadConversationData, t],
  );

  const handleDeleteConversation = useCallback(
    async (item: AgentConversationSummary) => {
      if (deletingConversationIds.has(item.id)) {
        return;
      }
      if (
        !window.confirm(
          t("agent.deleteConversationConfirm", "Delete this conversation?"),
        )
      ) {
        return;
      }
      setDeletingConversationIds((prev) => {
        const next = new Set(prev);
        next.add(item.id);
        return next;
      });
      try {
        await agentsApi.deleteConversation(agentId, item.id);
        const remainingConversations = conversations.filter(
          (conversationItem) => conversationItem.id !== item.id,
        );
        setConversationListState((prev) => ({
          ...prev,
          items: remainingConversations,
          total: Math.max(0, prev.total - 1),
        }));

        if (item.id === activeConversationId) {
          setConversation(null);
          messageListStateRef.current = EMPTY_MESSAGE_LIST_STATE;
          setMessageListState(EMPTY_MESSAGE_LIST_STATE);
          setPendingConversationTitle(null);
          setDraftConversationId(null);
          setShowDraftPlaceholder(false);
          setShowWorkspacePanel(false);
          setWorkspaceFocusPath(null);
          setDownloadingArtifactPath(null);
          resetStreamingState();
          if (remainingConversations.length > 0) {
            navigate(
              `/workforce/${agentId}/conversations/${remainingConversations[0].id}`,
            );
          } else {
            navigate(`/workforce/${agentId}/conversations`);
          }
        }
      } catch (deleteError) {
        console.error("Failed to delete conversation:", deleteError);
        toast.error(
          t("agent.deleteConversationFailed", "Failed to delete conversation"),
        );
      } finally {
        setDeletingConversationIds((prev) => {
          const next = new Set(prev);
          next.delete(item.id);
          return next;
        });
      }
    },
    [
      activeConversationId,
      agentId,
      conversations,
      deletingConversationIds,
      navigate,
      resetStreamingState,
      t,
    ],
  );

  const handleDownloadArtifact = useCallback(
    async (path: string) => {
      const normalizedPath = normalizeWorkspaceFilePath(path);
      if (!normalizedPath || !agentId || !activeConversationId) return;

      setDownloadingArtifactPath(normalizedPath);
      try {
        const blob = await agentsApi.downloadConversationWorkspaceFile(
          agentId,
          activeConversationId,
          normalizedPath,
        );
        const fileName =
          normalizedPath.split("/").filter(Boolean).pop() || "artifact";
        downloadBlob(blob, fileName);
      } catch (downloadError) {
        const message =
          downloadError instanceof Error
            ? downloadError.message
            : "Failed to download file";
        toast.error(message);
      } finally {
        setDownloadingArtifactPath(null);
      }
    },
    [activeConversationId, agentId],
  );

  const handleOpenArtifactInWorkspace = useCallback((path: string) => {
    const normalizedPath = normalizeWorkspaceFilePath(path);
    if (!normalizedPath) return;
    setWorkspaceFocusPath(normalizedPath);
    setShowWorkspacePanel(true);
  }, []);

  const handleFilesSelected = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const nextFiles = Array.from(event.target.files || []);
      if (nextFiles.length === 0) return;

      setAttachedFiles((prev) => [
        ...prev,
        ...nextFiles.map(buildAttachmentPreview),
      ]);
      event.target.value = "";
    },
    [],
  );

  const removeAttachedFile = useCallback((fileId: string) => {
    setAttachedFiles((prev) => {
      const target = prev.find((item) => item.id === fileId);
      if (target?.preview) {
        URL.revokeObjectURL(target.preview);
      }
      return prev.filter((item) => item.id !== fileId);
    });
  }, []);

  const releaseVoiceRecordingResources = useCallback(() => {
    if (recordingStreamRef.current) {
      recordingStreamRef.current.getTracks().forEach((track) => track.stop());
      recordingStreamRef.current = null;
    }
    mediaRecorderRef.current = null;
    recordingChunksRef.current = [];
    setIsRecordingVoice(false);
  }, []);

  const cancelVoiceRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onerror = null;
      recorder.onstop = null;
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
    }
    releaseVoiceRecordingResources();
  }, [releaseVoiceRecordingResources]);

  const resolveVoiceFileExtension = useCallback((mimeType: string): string => {
    const normalized = String(mimeType || "").toLowerCase();
    if (normalized.includes("wav")) return "wav";
    if (normalized.includes("mp4") || normalized.includes("m4a")) return "m4a";
    if (normalized.includes("flac")) return "flac";
    if (normalized.includes("ogg")) return "ogg";
    if (normalized.includes("aac")) return "aac";
    if (normalized.includes("mpeg") || normalized.includes("mp3")) return "mp3";
    return "webm";
  }, []);

  const transcribeVoiceBlob = useCallback(
    async (audioBlob: Blob, mimeType: string) => {
      if (!audioBlob.size) {
        setError(t("agent.voiceInputEmpty"));
        return;
      }

      setIsTranscribingVoice(true);
      setError(null);
      try {
        const extension = resolveVoiceFileExtension(mimeType);
        const timestamp = Date.now();
        const audioFile = new File(
          [audioBlob],
          `voice-input-${timestamp}.${extension}`,
          {
            type: mimeType || `audio/${extension}`,
          },
        );

        const response = await agentsApi.transcribeVoiceInput(audioFile);
        const transcript = String(response.text || "").trim();
        if (!transcript) {
          setError(t("agent.voiceInputEmpty"));
          return;
        }

        setInputMessage((prev) => {
          if (!prev.trim()) {
            return transcript;
          }
          return `${prev}${/\s$/.test(prev) ? "" : " "}${transcript}`;
        });
        textareaRef.current?.focus();
      } catch (transcribeError) {
        setError(
          transcribeError instanceof Error
            ? transcribeError.message
            : t("agent.voiceInputFailed"),
        );
      } finally {
        setIsTranscribingVoice(false);
      }
    },
    [resolveVoiceFileExtension, t],
  );

  const startVoiceRecording = useCallback(async () => {
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setError(t("agent.voiceInputUnsupported"));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordingStreamRef.current = stream;

      const preferredMimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus",
        "audio/ogg",
      ];

      const selectedMimeType = preferredMimeTypes.find((type) =>
        MediaRecorder.isTypeSupported(type),
      );

      const recorder = selectedMimeType
        ? new MediaRecorder(stream, { mimeType: selectedMimeType })
        : new MediaRecorder(stream);

      mediaRecorderRef.current = recorder;
      recordingChunksRef.current = [];

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          recordingChunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setError(t("agent.voiceInputFailed"));
        cancelVoiceRecording();
      };

      recorder.onstop = () => {
        const finalMimeType =
          recorder.mimeType || selectedMimeType || "audio/webm";
        const chunks = [...recordingChunksRef.current];
        releaseVoiceRecordingResources();
        void transcribeVoiceBlob(
          new Blob(chunks, { type: finalMimeType }),
          finalMimeType,
        );
      };

      recorder.start();
      setError(null);
      setIsRecordingVoice(true);
    } catch (recordError) {
      const isPermissionDenied =
        recordError instanceof DOMException &&
        (recordError.name === "NotAllowedError" ||
          recordError.name === "PermissionDeniedError");

      setError(
        isPermissionDenied
          ? t("agent.voiceInputPermissionDenied")
          : recordError instanceof Error
            ? recordError.message
            : t("agent.voiceInputFailed"),
      );
      cancelVoiceRecording();
    }
  }, [
    cancelVoiceRecording,
    releaseVoiceRecordingResources,
    t,
    transcribeVoiceBlob,
  ]);

  const handleVoiceInput = useCallback(async () => {
    if (isSending || isTranscribingVoice) {
      return;
    }

    const recorder = mediaRecorderRef.current;
    if (isRecordingVoice && recorder && recorder.state !== "inactive") {
      recorder.stop();
      return;
    }

    await startVoiceRecording();
  }, [isRecordingVoice, isSending, isTranscribingVoice, startVoiceRecording]);

  useEffect(
    () => () => {
      const recorder = mediaRecorderRef.current;
      if (recorder) {
        recorder.ondataavailable = null;
        recorder.onerror = null;
        recorder.onstop = null;
        if (recorder.state !== "inactive") {
          recorder.stop();
        }
      }
      if (recordingStreamRef.current) {
        recordingStreamRef.current.getTracks().forEach((track) => track.stop());
        recordingStreamRef.current = null;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    },
    [],
  );

  const handleAbortStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    abortStreamingHandlerRef.current?.();
    abortStreamingHandlerRef.current = null;
  }, []);

  const handleSendMessage = useCallback(async () => {
    if (!agentId || isSending || isRecordingVoice || isTranscribingVoice) {
      return;
    }
    if (agent?.externalRuntime && !agent.externalRuntime.availableForConversation) {
      toast.error(externalRuntimeBlockedMessage);
      return;
    }

    const text = inputMessage.trim();
    if (!text && attachedFiles.length === 0) {
      return;
    }

    let targetConversationId = conversationId || draftConversationId;

    if (!targetConversationId) {
      setIsCreatingConversation(true);
      setShowDraftPlaceholder(true);
      setPendingConversationTitle(null);
      try {
        const nextConversation = await agentsApi.createConversation(agentId);
        targetConversationId = nextConversation.id;
        setDraftConversationId(nextConversation.id);
        replaceConversationUrl(nextConversation.id);
      } catch (createError) {
        console.error("Failed to create conversation:", createError);
        setIsCreatingConversation(false);
        setShowDraftPlaceholder(false);
        toast.error(
          t("agent.startConversationFailed", "Failed to start conversation"),
        );
        return;
      }
    }

    if (!targetConversationId) {
      setIsCreatingConversation(false);
      setShowDraftPlaceholder(false);
      return;
    }

    const optimisticAttachments = attachedFiles.map((item) => ({
      id: item.id,
      name: item.file.name,
      size: item.file.size,
      type: item.type,
    }));
    const optimisticMessage: ConversationMessage = {
      id: `temp-user-${Date.now()}`,
      conversationId: targetConversationId,
      role: "user",
      contentText: text || "[Attached files]",
      contentJson: null,
      attachments: optimisticAttachments,
      source: "web",
      createdAt: new Date().toISOString(),
    };

    setMessageListState((prev) => ({
      ...prev,
      items: [...prev.items, optimisticMessage],
    }));
    setInputMessage("");
    setAttachedFiles((prev) => {
      prev.forEach((item) => {
        if (item.preview) {
          URL.revokeObjectURL(item.preview);
        }
      });
      return [];
    });
    setIsSending(true);
    setError(null);
    resetStreamingState();
    shouldAutoScrollRef.current = true;
    streamingViewRef.current = createEmptyStreamingViewState();
    streamingViewRef.current.phase = "thinking";
    streamingViewRef.current.processDescriptor = {
      phase: "thinking",
      kind: "thinking",
      detail: null,
      accent: null,
    };
    scheduleStreamingStateSync(true);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    let turnOutcome: "completed" | "cancelled" | "failed" | null = null;
    let hasFinalizedCompletedTurn = false;
    let hasCommittedFailedTurn = false;

    const removeOptimisticMessage = () => {
      setMessageListState((prev) => ({
        ...prev,
        items: prev.items.filter((message) => message.id !== optimisticMessage.id),
      }));
    };

    const commitFailedTurnToMessages = () => {
      if (hasCommittedFailedTurn) {
        return;
      }
      hasCommittedFailedTurn = true;

      const assistantContent = getPersistentFallbackAssistantText(
        {
          contentText: streamingViewRef.current.assistantText,
          contentJson: {
            scheduleEvents: streamingViewRef.current.scheduleEvents,
          },
        },
        t("agent.persistentResult.generatedOutput", "已生成结果"),
      );

      setMessageListState((prev) => ({
        ...prev,
        items: [
          ...prev.items,
          {
            id: `temp-assistant-failed-${Date.now()}`,
            conversationId: targetConversationId,
            role: "assistant",
            contentText: assistantContent,
            contentJson: {
              artifacts: [],
              scheduleEvents: streamingViewRef.current.scheduleEvents,
              inlineError: streamingViewRef.current.inlineError,
            },
            attachments: [],
            source: "web",
            createdAt: new Date().toISOString(),
          },
        ],
      }));
    };

    const finalizeCompletedTurn = async () => {
      if (hasFinalizedCompletedTurn) {
        return;
      }
      hasFinalizedCompletedTurn = true;
      turnOutcome = "completed";
      shouldAutoScrollRef.current = true;
      const assistantContent =
        streamingViewRef.current.assistantText.trim() ||
        t("agent.persistentResult.generatedOutput", "已生成结果");
      upsertConversationItem({
        id: targetConversationId,
        agentId,
        ownerUserId: "",
        title:
          pendingConversationTitle ||
          conversation?.title ||
          t("agent.draftConversation", "New conversation"),
        status: "active",
        source: "web",
        latestSnapshotId: null,
        latestSnapshotStatus: "ready",
        lastMessageAt: new Date().toISOString(),
        lastMessagePreview: assistantContent || text || "[Attached files]",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      });
      setConversation((prev) =>
        prev
          ? {
              ...prev,
              title:
                pendingConversationTitle ||
                prev.title ||
                t("agent.draftConversation", "New conversation"),
              latestSnapshotStatus: "ready",
            }
          : prev,
      );
      setIsCreatingConversation(false);
      setShowDraftPlaceholder(false);
      await syncConversationState(targetConversationId);
      resetStreamingState();
      setIsSending(false);
    };

    abortStreamingHandlerRef.current = () => {
      if (turnOutcome === "completed") {
        return;
      }
      turnOutcome = "cancelled";
      removeOptimisticMessage();
      shouldAutoScrollRef.current = true;
      resetStreamingState();
      setIsCreatingConversation(false);
      setShowDraftPlaceholder(false);
      setError(null);
    };

    try {
      await agentsApi.sendConversationMessage(
        agentId,
        targetConversationId,
        text || "[Attached files]",
        (chunk) => {
          if (chunk.type === "conversation_title") {
            const nextTitle = String(chunk.title || "").trim();
            if (nextTitle) {
              setPendingConversationTitle(nextTitle);
              setShowDraftPlaceholder(false);
              setConversation((prev) =>
                prev
                  ? { ...prev, title: nextTitle }
                  : ({
                      id: String(chunk.conversation_id || targetConversationId),
                      agentId,
                      ownerUserId: "",
                      title: nextTitle,
                      status: "active",
                      source: "web",
                      latestSnapshotId: null,
                      latestSnapshotStatus: null,
                      lastMessageAt: new Date().toISOString(),
                      lastMessagePreview: text || "[Attached files]",
                      createdAt: new Date().toISOString(),
                      updatedAt: new Date().toISOString(),
                      latestSnapshotGeneration: null,
                    } as AgentConversationDetail),
              );
              upsertConversationItem({
                id: String(chunk.conversation_id || targetConversationId),
                agentId,
                ownerUserId: "",
                title: nextTitle,
                status: "active",
                source: "web",
                latestSnapshotId: null,
                latestSnapshotStatus: "ready",
                lastMessageAt: new Date().toISOString(),
                lastMessagePreview: text || "[Attached files]",
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              });
            }
            return;
          }

          if (chunk.type === "content") {
            const chunkText = String(chunk.content || "");
            const currentContent = streamingViewRef.current.assistantText;
            const isLeadingWhitespaceOnly =
              chunkText.trim().length === 0 &&
              currentContent.trim().length === 0;

            if (isLeadingWhitespaceOnly) {
              return;
            }

            streamingViewRef.current.assistantText += chunkText;
            streamingViewRef.current.hasContentStarted = true;
            streamingViewRef.current.phase = null;
            streamingViewRef.current.processDescriptor = null;
          } else if (chunk.type === "schedule_created") {
            const nextScheduleEvents = mergePersistentScheduleEvents(
              streamingViewRef.current.scheduleEvents,
              chunk,
            );
            if (
              nextScheduleEvents.length !==
              streamingViewRef.current.scheduleEvents.length
            ) {
              streamingViewRef.current.scheduleEvents = nextScheduleEvents;
              const scheduleEvent =
                nextScheduleEvents[nextScheduleEvents.length - 1];
              addNotification({
                type: "success",
                title: t("schedules.page.createdTitle", "定时任务已创建"),
                message: `${scheduleEvent.name} ${t("schedules.page.createdSuffix", "已创建")}`,
                actionUrl: `/schedules/${scheduleEvent.schedule_id}`,
                actionLabel: t("schedules.page.viewSchedule", "查看定时任务"),
              });
            }
          } else if (chunk.type === "error") {
            turnOutcome = "failed";
            streamingViewRef.current.phase = null;
            streamingViewRef.current.processDescriptor = null;
            streamingViewRef.current.inlineError = String(chunk.content || "");
          } else if (chunk.type === "done") {
            streamingViewRef.current.phase = null;
            streamingViewRef.current.processDescriptor = null;
            scheduleStreamingStateSync(true);
            void finalizeCompletedTurn();
            const activeController = abortControllerRef.current;
            if (activeController) {
              activeController.abort();
            }
            return;
          } else {
            const nextPhase = mapChunkToPersistentPhase(chunk);
            const nextDescriptor = derivePersistentProcessDescriptor(chunk);
            const resolvedPhase = nextDescriptor?.phase || nextPhase;
            if (
              resolvedPhase &&
              !streamingViewRef.current.hasContentStarted
            ) {
              streamingViewRef.current.phase = resolvedPhase;
            }
            if (
              nextDescriptor &&
              !streamingViewRef.current.hasContentStarted
            ) {
              streamingViewRef.current.processDescriptor = nextDescriptor;
            }
          }

          scheduleStreamingStateSync();
        },
        (message) => {
          if (turnOutcome !== "completed") {
            turnOutcome = turnOutcome || "failed";
            streamingViewRef.current.phase = null;
            streamingViewRef.current.inlineError = message;
            scheduleStreamingStateSync(true);
          }
        },
        () => {
          if (turnOutcome === "failed" || turnOutcome === "cancelled") {
            return;
          }
          void finalizeCompletedTurn();
        },
        optimisticAttachments
          .map((item) => {
            const file = attachedFiles.find(
              (attached) => attached.id === item.id,
            );
            return file?.file;
          })
          .filter(Boolean) as File[],
        abortController.signal,
      );
    } catch (sendError) {
      console.error("Failed to send conversation message:", sendError);
      if (turnOutcome !== "completed") {
        turnOutcome = turnOutcome || "failed";
        streamingViewRef.current.phase = null;
        streamingViewRef.current.inlineError =
          sendError instanceof Error
            ? sendError.message
            : t("agent.sendMessageFailed", "Failed to send message");
        scheduleStreamingStateSync(true);
        setIsCreatingConversation(false);
        setShowDraftPlaceholder(false);
      }
    } finally {
      if (turnOutcome === "failed") {
        const syncedMessages = await syncConversationState(targetConversationId);
        const latestMessage = syncedMessages?.items?.[syncedMessages.items.length - 1];
        if (!latestMessage || latestMessage.role !== "assistant") {
          commitFailedTurnToMessages();
        }
        resetStreamingState();
        setIsSending(false);
      } else if (turnOutcome !== "completed") {
        shouldAutoScrollRef.current = true;
        await syncConversationState(targetConversationId);
        setIsSending(false);
      }
      abortControllerRef.current = null;
      abortStreamingHandlerRef.current = null;
    }
  }, [
    addNotification,
    agent?.externalRuntime?.availableForConversation,
    agentId,
    attachedFiles,
    conversationId,
    conversation?.title,
    draftConversationId,
    inputMessage,
    isRecordingVoice,
    isSending,
    isTranscribingVoice,
    pendingConversationTitle,
    replaceConversationUrl,
    resetStreamingState,
    scheduleStreamingStateSync,
    syncConversationState,
    t,
    upsertConversationItem,
  ]);

  const generatedOutputLabel = t(
    "agent.persistentResult.generatedOutput",
    "已生成结果",
  );
  const shouldVirtualizeHistory =
    messages.length >= HISTORY_VIRTUALIZATION_MIN_ITEMS;
  const shouldVirtualizeConversationList =
    conversations.length >= CONVERSATION_LIST_VIRTUALIZATION_MIN_ITEMS;

  const showPendingConversationCard = showDraftPlaceholder;
  const showStreamingProcessLine =
    isSending &&
    Boolean(streamingProcessDescriptor) &&
    !shouldHideProcessLine(hasStreamingContentStarted);
  const streamingAssistantDisplayContent = getPersistentFallbackAssistantText(
    {
      contentText: streamingAssistantText,
      contentJson: {
        scheduleEvents: streamingScheduleItems,
      },
    },
    generatedOutputLabel,
  );
  const showStreamingAssistantMessage =
    Boolean(streamingAssistantDisplayContent.trim()) ||
    Boolean(streamingInlineError) ||
    streamingScheduleItems.length > 0;
  const hasVisibleConversationContent =
    messages.length > 0 ||
    showStreamingProcessLine ||
    showStreamingAssistantMessage;
  const showBlockingLoading = isLoading && !hasVisibleConversationContent;
  const showCompactedHistorySummary =
    !messageListState.hasOlderLiveMessages &&
    Boolean(historySummary) &&
    Number(conversation?.compactedMessageCount || 0) > 0;
  const conversationTitle =
    pendingConversationTitle ||
    conversation?.title ||
    (showPendingConversationCard
      ? t("agent.generatingConversationTitle", "Generating title...")
      : !conversationId
        ? t("agent.draftConversation", "New conversation")
        : t("agent.loadingConversation", "Loading conversation..."));
  const conversationSubtitle = showPendingConversationCard
    ? t(
        "agent.generatingConversationTitleHint",
        "The title will appear after the first reply.",
      )
    : !conversationId
      ? t(
          "agent.draftConversationHint",
          "Send the first message to create this conversation.",
        )
      : conversation?.latestSnapshotStatus
        ? `${conversation.storageTier || "hot"} • ${t("agent.snapshotStatus", "Snapshot")}: ${conversation.latestSnapshotStatus}`
        : t("agent.snapshotPending", "No snapshot yet");

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate("/workforce")}
            className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            <ArrowLeft className="w-4 h-4" />
            {t("common.back", "Back")}
          </button>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {agent?.name ||
                t("agent.conversationTitle", "Agent Conversation")}
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {conversationTitle}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowWorkspacePanel((prev) => !prev)}
            disabled={!activeConversationId}
            className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            <FolderOpen className="w-4 h-4" />
            {t("agent.workspace", "Workspace")}
          </button>
          <button
            type="button"
            onClick={handleCreateConversation}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-600"
          >
            <MessageSquarePlus className="w-4 h-4" />
            {t("agent.newConversation", "New conversation")}
          </button>
        </div>
      </div>

      <div className="grid min-h-0 grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="flex h-[calc(100vh-11rem)] min-h-[620px] min-w-0 flex-col overflow-hidden rounded-3xl border border-zinc-200 bg-white/90 p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-400">
              {t("agent.conversations", "Conversations")}
            </h2>
            <span className="rounded-full bg-zinc-100 px-2 py-1 text-xs font-semibold text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
              {conversationListState.total + (showPendingConversationCard ? 1 : 0)}
            </span>
          </div>

          <div
            ref={conversationListContainerRef}
            onScroll={handleConversationListScroll}
            data-testid="conversation-list-scroll"
            className="min-h-0 flex-1 overflow-y-auto pr-1"
          >
            {showPendingConversationCard && (
              <div className="rounded-2xl border border-emerald-300/60 bg-emerald-50/70 px-3 py-3 dark:border-emerald-700/50 dark:bg-emerald-950/20">
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t(
                    "agent.generatingConversationTitle",
                    "Generating title...",
                  )}
                </div>
                <div className="mt-3 space-y-2">
                  <div className="h-3 w-2/3 animate-pulse rounded-full bg-emerald-200/80 dark:bg-emerald-800/70" />
                  <div className="h-3 w-full animate-pulse rounded-full bg-zinc-200/80 dark:bg-zinc-800/80" />
                  <div className="h-3 w-4/5 animate-pulse rounded-full bg-zinc-200/70 dark:bg-zinc-800/60" />
                </div>
              </div>
            )}
            <div>
              {shouldVirtualizeConversationList ? (
                <>
                  <div
                    style={{
                      height: `${conversationListVirtualization.topSpacerHeight}px`,
                    }}
                  />
                  {conversationListVirtualization.visibleIndexes.map((index) => {
                    const item = conversations[index];
                    if (!item) {
                      return null;
                    }
                    return (
                      <MeasuredVirtualItem
                        key={item.id}
                        gapPx={8}
                        index={index}
                        onHeightChange={
                          conversationListVirtualization.onItemHeightChange
                        }
                      >
                        <ConversationListItemCard
                          activeConversationId={activeConversationId}
                          deletingConversationIds={deletingConversationIds}
                          item={item}
                          noMessagesLabel={t(
                            "agent.noMessagesYet",
                            "No messages yet",
                          )}
                          onDeleteConversation={(conversationItem) => {
                            void handleDeleteConversation(conversationItem);
                          }}
                          onOpenConversation={(nextConversationId) => {
                            navigate(
                              `/workforce/${agentId}/conversations/${nextConversationId}`,
                            );
                          }}
                          onRenameConversation={(conversationItem) => {
                            void handleRenameConversation(conversationItem);
                          }}
                        />
                      </MeasuredVirtualItem>
                    );
                  })}
                  <div
                    style={{
                      height: `${conversationListVirtualization.bottomSpacerHeight}px`,
                    }}
                  />
                </>
              ) : (
                conversations.map((item, index) => (
                  <div
                    key={item.id}
                    style={{
                      paddingBottom:
                        index < conversations.length - 1
                          ? "8px"
                          : undefined,
                    }}
                  >
                    <ConversationListItemCard
                      activeConversationId={activeConversationId}
                      deletingConversationIds={deletingConversationIds}
                      item={item}
                      noMessagesLabel={t("agent.noMessagesYet", "No messages yet")}
                      onDeleteConversation={(conversationItem) => {
                        void handleDeleteConversation(conversationItem);
                      }}
                      onOpenConversation={(nextConversationId) => {
                        navigate(
                          `/workforce/${agentId}/conversations/${nextConversationId}`,
                        );
                      }}
                      onRenameConversation={(conversationItem) => {
                        void handleRenameConversation(conversationItem);
                      }}
                    />
                  </div>
                ))
              )}
              {conversationListState.isLoadingMore && (
                <div className="flex items-center justify-center py-3 text-zinc-500 dark:text-zinc-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              )}
            </div>
          </div>
        </aside>

        <section className="grid h-[calc(100vh-11rem)] min-h-[620px] grid-cols-1 gap-4">
          <div className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-zinc-200 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                      {conversationTitle}
                    </h2>
                    {conversation?.storageTier &&
                      conversation.storageTier !== "hot" && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                          {conversation.storageTier}
                        </span>
                      )}
                  </div>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {conversationSubtitle}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRefreshConversation()}
                  className="rounded-xl border border-zinc-200 px-3 py-2 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  {t("common.refresh", "Refresh")}
                </button>
              </div>
            </div>

            <div
              ref={messagesContainerRef}
              onScroll={handleMessagesScroll}
              data-testid="conversation-messages-scroll"
              className="min-h-0 flex-1 overflow-y-auto px-5 py-5"
            >
              {showBlockingLoading ? (
                <div className="flex h-full items-center justify-center gap-3 text-zinc-500 dark:text-zinc-400">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>{t("common.loading", "Loading...")}</span>
                </div>
              ) : error && !hasVisibleConversationContent ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300">
                  {error}
                </div>
              ) : !hasVisibleConversationContent ? (
                <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
                    <Bot className="w-7 h-7" />
                  </div>
                  <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    {t("agent.draftConversation", "New conversation")}
                  </h3>
                  <p className="mt-2 max-w-md text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
                    {t(
                      "agent.draftConversationHint",
                      "Send the first message to create and save this conversation.",
                    )}
                  </p>
                </div>
              ) : (
                <div className="flex flex-col">
                  <div ref={historyPrefixRef}>
                    {messageListState.isLoadingOlder && (
                      <div className="flex items-center justify-center pb-4 text-zinc-500 dark:text-zinc-400">
                        <Loader2 className="h-4 w-4 animate-spin" />
                      </div>
                    )}
                    {showCompactedHistorySummary && historySummary && (
                        <div
                          data-testid="compacted-history-summary"
                          className="rounded-[28px] border border-amber-200 bg-amber-50/80 px-5 py-4 dark:border-amber-900/40 dark:bg-amber-950/20"
                        >
                          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">
                            <Bot className="h-4 w-4" />
                            {t(
                              "agent.compactedHistory",
                              "Earlier messages were compacted",
                            )}
                          </div>
                          <p className="mt-2 text-xs leading-5 text-amber-800/90 dark:text-amber-200/90">
                            {t(
                              "agent.compactedHistoryHint",
                              "{{count}} earlier message(s) were summarized to keep this conversation lightweight.",
                              {
                                count: conversation?.compactedMessageCount || 0,
                              },
                            )}
                          </p>
                          <div className="mt-3 markdown-content text-sm text-zinc-700 dark:text-zinc-200">
                            <ReactMarkdown
                              remarkPlugins={remarkPlugins}
                              components={markdownComponents}
                            >
                              {historySummary.summaryText}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}
                  </div>

                  {shouldVirtualizeHistory ? (
                    <>
                      <div
                        style={{
                          height: `${historyVirtualization.topSpacerHeight}px`,
                        }}
                      />

                      {historyVirtualization.visibleIndexes.map((index) => {
                        const message = messages[index];
                        if (!message) {
                          return null;
                        }

                        return (
                          <MeasuredVirtualItem
                            key={message.id}
                            index={index}
                            onHeightChange={
                              historyVirtualization.onItemHeightChange
                            }
                          >
                            <ConversationMessageRow
                              message={message}
                              generatedOutputLabel={generatedOutputLabel}
                              onOpenArtifact={handleOpenArtifactInWorkspace}
                              onDownloadArtifact={handleDownloadArtifact}
                              downloadingArtifactPath={downloadingArtifactPath}
                            />
                          </MeasuredVirtualItem>
                        );
                      })}

                      <div
                        style={{
                          height: `${historyVirtualization.bottomSpacerHeight}px`,
                        }}
                      />
                    </>
                  ) : (
                    messages.map((message, index) => (
                      <div
                        key={message.id}
                        style={{
                          paddingBottom:
                            index < messages.length - 1
                              ? `${HISTORY_MESSAGE_GAP_PX}px`
                              : undefined,
                        }}
                      >
                        <ConversationMessageRow
                          message={message}
                          generatedOutputLabel={generatedOutputLabel}
                          onOpenArtifact={handleOpenArtifactInWorkspace}
                          onDownloadArtifact={handleDownloadArtifact}
                          downloadingArtifactPath={downloadingArtifactPath}
                        />
                      </div>
                    ))
                  )}

                  {(showStreamingProcessLine ||
                    showStreamingAssistantMessage) && (
                    <div
                      className="space-y-6"
                      style={{
                        paddingTop:
                          messages.length > 0
                            ? `${HISTORY_MESSAGE_GAP_PX}px`
                            : undefined,
                      }}
                    >
                      <PersistentConversationProcessLine
                        descriptor={streamingProcessDescriptor}
                        isVisible={showStreamingProcessLine}
                      />
                      {showStreamingAssistantMessage ? (
                        <PersistentConversationAssistantMessage
                          content={streamingAssistantDisplayContent}
                          artifactItems={[]}
                          scheduleItems={streamingScheduleItems}
                          errorText={streamingInlineError}
                          onOpenArtifact={handleOpenArtifactInWorkspace}
                          onDownloadArtifact={handleDownloadArtifact}
                          downloadingArtifactPath={downloadingArtifactPath}
                        />
                      ) : null}
                    </div>
                  )}

                  {error && (
                    <div
                      className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300"
                      style={{
                        marginTop:
                          messages.length > 0 ||
                          showStreamingProcessLine ||
                          showStreamingAssistantMessage
                            ? `${HISTORY_MESSAGE_GAP_PX}px`
                            : undefined,
                      }}
                    >
                      {error}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
              {isExternalRuntimeBlocked && (
                <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <span>{externalRuntimeBlockedMessage}</span>
                    <button
                      type="button"
                      onClick={() => navigate(externalRuntimeSetupHref)}
                      className="rounded-full border border-amber-300 px-3 py-1.5 text-xs font-semibold text-amber-800 transition hover:bg-amber-100 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900/40"
                    >
                      {t("agent.openRuntimeHost", "Open Runtime Host")}
                    </button>
                  </div>
                </div>
              )}
              {attachedFiles.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {attachedFiles.map((file) => (
                    <div
                      key={file.id}
                      className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs dark:border-zinc-800 dark:bg-zinc-950/50"
                    >
                      {file.type === "image" ? (
                        <ImageIcon className="w-3.5 h-3.5" />
                      ) : (
                        <Paperclip className="w-3.5 h-3.5" />
                      )}
                      <span className="max-w-[180px] truncate">
                        {file.file.name}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeAttachedFile(file.id)}
                        className="text-zinc-400 transition-colors hover:text-red-500"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-end gap-3 rounded-[28px] border border-zinc-200 bg-zinc-50/90 px-3 py-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-950/60">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isSending || isExternalRuntimeBlocked}
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white text-zinc-600 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={ATTACHMENT_ACCEPT_TYPES}
                  className="hidden"
                  onChange={handleFilesSelected}
                />
                <textarea
                  ref={textareaRef}
                  value={inputMessage}
                  onChange={(event) => setInputMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      if (
                        !isSending &&
                        !isRecordingVoice &&
                        !isTranscribingVoice &&
                        (inputMessage.trim() || attachedFiles.length > 0)
                      ) {
                        void handleSendMessage();
                      }
                    }
                  }}
                  placeholder={
                    isSending
                      ? t("agent.thinking", "Thinking...")
                      : isTranscribingVoice
                        ? t(
                            "agent.voiceInputProcessing",
                            "Transcribing voice input...",
                          )
                        : t(
                            "agent.messagePlaceholder",
                            "Send a message to this agent",
                          )
                  }
                  disabled={isSending || isExternalRuntimeBlocked}
                  rows={1}
                  className="max-h-[180px] min-h-[24px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-zinc-900 outline-none placeholder:text-zinc-400 dark:text-white"
                />
                <button
                  type="button"
                  onClick={() => {
                    void handleVoiceInput();
                  }}
                  disabled={isSending || isTranscribingVoice || isExternalRuntimeBlocked}
                  title={
                    isRecordingVoice
                      ? t("agent.voiceInputStop")
                      : t("agent.voiceInputStart")
                  }
                  className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    isRecordingVoice
                      ? "bg-rose-50 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400"
                      : "bg-white text-zinc-600 hover:bg-zinc-100 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  }`}
                >
                  {isTranscribingVoice ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : isRecordingVoice ? (
                    <Square className="w-4 h-4 fill-current" />
                  ) : (
                    <Mic className="w-4 h-4" />
                  )}
                </button>
                {isSending ? (
                  <button
                    type="button"
                    onClick={handleAbortStreaming}
                    className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-rose-500 text-white transition-colors hover:bg-rose-600"
                  >
                    <XIcon className="w-4 h-4" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void handleSendMessage()}
                    disabled={
                      isExternalRuntimeBlocked ||
                      (!inputMessage.trim() && attachedFiles.length === 0) ||
                      isRecordingVoice ||
                      isTranscribingVoice
                    }
                    className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-emerald-500 text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-zinc-300 dark:disabled:bg-zinc-700"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      <SessionWorkspacePanel
        agentId={agentId}
        conversationId={activeConversationId || undefined}
        isOpen={showWorkspacePanel}
        onClose={() => setShowWorkspacePanel(false)}
        focusPath={workspaceFocusPath}
      />
    </div>
  );
};
