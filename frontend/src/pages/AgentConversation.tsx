import React, {
  useCallback,
  useEffect,
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
import {
  mergeScheduleEvents,
  normalizeScheduleCreatedEvent,
} from "@/components/schedules/scheduleUtils";
import {
  ConversationRoundComponent,
  type ConversationRoundArtifact,
} from "@/components/workforce/ConversationRound";
import { createMarkdownComponents } from "@/components/workforce/CodeBlock";
import { SessionWorkspacePanel } from "@/components/workforce/SessionWorkspacePanel";
import { getRuntimeStatusMessage } from "@/pages/agentConversationRuntime";
import { useNotificationStore } from "@/stores";
import type {
  Agent,
  AgentConversationDetail,
  AgentConversationHistorySummary,
  AgentConversationSummary,
  ConversationMessage,
} from "@/types/agent";
import type {
  AttachedFile,
  ConversationRound,
  ErrorFeedback,
  RetryAttempt,
  StatusMessage,
} from "@/types/streaming";
import type { ScheduleCreatedEvent } from "@/types/schedule";

const WORKSPACE_PATH_PATTERN = /\/workspace\/[^\s,)\]}>"'`]+/gi;
const FILE_PATH_KV_PATTERN = /file_path=([^\s,)\]}>"'`]+)/gi;
const FILE_ACTION_PATH_PATTERN =
  /(?:wrote|appended to|edited)\s+([^\s,)\]}>"'`]+)/gi;
const RELATIVE_FILE_PATH_PATTERN =
  /(?:^|[\s"'`(（【])((?:\.\/)?[^\s"'`<>(){}[\]]+\.(?:md|markdown|txt|json|csv|ya?ml|pdf|docx?|xlsx?|pptx?|html?))(?=$|[\s"'`)\]}>，。；;!?])/gi;
const ATTACHMENT_ACCEPT_TYPES =
  "image/*,.pdf,.doc,.docx,.pptx,.xls,.xlsx,.txt,.md,.markdown,.html,.htm,.csv";
const STREAM_RENDER_THROTTLE_MS = 60;
const AUTO_SCROLL_THRESHOLD_PX = 120;
const HISTORY_MESSAGE_GAP_PX = 32;
const HISTORY_MESSAGE_ESTIMATED_HEIGHT_PX = 320;
const HISTORY_OVERSCAN_PX = 900;
const HISTORY_VIRTUALIZATION_MIN_ITEMS = 24;

interface StreamingRoundState {
  thinking: string;
  content: string;
  statusMessages: StatusMessage[];
  retryAttempts: RetryAttempt[];
  errorFeedback: ErrorFeedback[];
  stats: ConversationRound["stats"] | null;
  scheduleEvents: ScheduleCreatedEvent[];
}

function createEmptyRoundData(): StreamingRoundState {
  return {
    thinking: "",
    content: "",
    statusMessages: [],
    retryAttempts: [],
    errorFeedback: [],
    stats: null,
    scheduleEvents: [],
  };
}

function buildRoundSnapshot(
  roundData: StreamingRoundState,
  roundNumber: number,
): ConversationRound {
  return {
    roundNumber,
    thinking: roundData.thinking,
    content: roundData.content,
    statusMessages: [...roundData.statusMessages],
    retryAttempts:
      roundData.retryAttempts.length > 0
        ? [...roundData.retryAttempts]
        : undefined,
    errorFeedback:
      roundData.errorFeedback.length > 0
        ? [...roundData.errorFeedback]
        : undefined,
    stats: roundData.stats ? { ...roundData.stats } : undefined,
    scheduleEvents:
      roundData.scheduleEvents.length > 0
        ? [...roundData.scheduleEvents]
        : undefined,
  };
}

function buildCurrentRoundDataState(
  roundData: StreamingRoundState,
): StreamingRoundState {
  return {
    thinking: roundData.thinking,
    content: roundData.content,
    statusMessages: [...roundData.statusMessages],
    retryAttempts: [...roundData.retryAttempts],
    errorFeedback: [...roundData.errorFeedback],
    stats: roundData.stats ? { ...roundData.stats } : null,
    scheduleEvents: [...roundData.scheduleEvents],
  };
}

function hasRoundActivity(round: StreamingRoundState): boolean {
  return Boolean(
    round.thinking ||
    round.content.trim() ||
    round.statusMessages.length > 0 ||
    round.retryAttempts.length > 0 ||
    round.errorFeedback.length > 0 ||
    round.scheduleEvents.length > 0,
  );
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

function normalizeWorkspaceFilePath(rawPath: string): string {
  let normalized = String(rawPath || "")
    .trim()
    .replace(/\\/g, "/");
  normalized = normalized.replace(/^[\s("'`[{（【]+/, "");
  normalized = normalized.replace(/[\s)"'`.,:;!?}\]）】]+$/, "");
  if (!normalized) return "";
  if (/^(?:https?:|data:|file:)/i.test(normalized)) return "";

  const workspaceIndex = normalized.indexOf("/workspace/");
  if (workspaceIndex >= 0) {
    normalized = normalized.slice(workspaceIndex);
  }

  if (normalized.startsWith("workspace/")) {
    normalized = `/${normalized}`;
  }

  if (!normalized.startsWith("/workspace/")) {
    if (normalized.startsWith("./")) {
      normalized = normalized.slice(2);
    }
    if (normalized.startsWith("/")) return "";
    normalized = `/workspace/${normalized}`;
  }

  if (normalized.includes("..")) return "";
  return normalized.startsWith("/workspace/") ? normalized : "";
}

function extractWorkspacePathsFromText(text: string): string[] {
  const source = String(text || "");
  const unique = new Set<string>();
  const candidatePaths: string[] = [];

  const absoluteMatches = source.match(WORKSPACE_PATH_PATTERN) || [];
  candidatePaths.push(...absoluteMatches);

  for (const match of source.matchAll(FILE_PATH_KV_PATTERN)) {
    if (match[1]) {
      candidatePaths.push(match[1]);
    }
  }

  for (const match of source.matchAll(FILE_ACTION_PATH_PATTERN)) {
    if (match[1]) {
      candidatePaths.push(match[1]);
    }
  }

  for (const match of source.matchAll(RELATIVE_FILE_PATH_PATTERN)) {
    if (match[1]) {
      candidatePaths.push(match[1]);
    }
  }

  candidatePaths.forEach((rawPath) => {
    const normalized = normalizeWorkspaceFilePath(rawPath);
    if (!normalized || normalized.startsWith("/workspace/input/")) {
      return;
    }
    unique.add(normalized);
  });

  return [...unique];
}

function extractRoundArtifacts(
  round: ConversationRound,
): ConversationRoundArtifact[] {
  const explicitArtifacts = Array.isArray((round as any).artifacts)
    ? (round as any).artifacts
    : [];
  const explicitPaths = explicitArtifacts
    .map((item: any) => normalizeWorkspaceFilePath(item?.path || ""))
    .filter(Boolean);
  const inferredPaths = extractWorkspacePathsFromText(round.content || "");
  return [...new Set([...explicitPaths, ...inferredPaths])]
    .sort((a, b) => a.localeCompare(b))
    .map((path) => ({ path, confirmed: true }));
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

interface VirtualizedHistoryItemProps {
  index: number;
  onHeightChange: (index: number, height: number) => void;
  children: React.ReactNode;
}

const VirtualizedHistoryItem: React.FC<VirtualizedHistoryItemProps> = ({
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
    <div ref={itemRef} style={{ paddingBottom: `${HISTORY_MESSAGE_GAP_PX}px` }}>
      {children}
    </div>
  );
};

function normalizeStoredRound(rawRound: any, index: number): ConversationRound {
  const statusMessages = Array.isArray(rawRound?.statusMessages)
    ? rawRound.statusMessages.map((item: any) => ({
        content: String(item?.content || ""),
        type: (item?.type || "info") as StatusMessage["type"],
        timestamp: new Date(item?.timestamp || Date.now()),
        duration:
          typeof item?.duration === "number" ? item.duration : undefined,
      }))
    : [];

  const retryAttempts = Array.isArray(rawRound?.retryAttempts)
    ? rawRound.retryAttempts.map((item: any, retryIndex: number) => ({
        retryCount: Number(
          item?.retryCount || item?.retry_count || retryIndex + 1 || 1,
        ),
        maxRetries: Number(item?.maxRetries || item?.max_retries || 1),
        errorType: (item?.errorType ||
          item?.error_type ||
          "parse_error") as RetryAttempt["errorType"],
        message: String(item?.message || ""),
        timestamp: new Date(item?.timestamp || Date.now()),
      }))
    : undefined;

  const errorFeedback = Array.isArray(rawRound?.errorFeedback)
    ? rawRound.errorFeedback.map((item: any) => ({
        errorType: String(item?.errorType || item?.error_type || "unknown"),
        retryCount: Number(item?.retryCount || item?.retry_count || 1),
        maxRetries: Number(item?.maxRetries || item?.max_retries || 1),
        message: String(item?.message || ""),
        suggestions: Array.isArray(item?.suggestions)
          ? item.suggestions.map(String)
          : undefined,
        timestamp: new Date(item?.timestamp || Date.now()),
      }))
    : undefined;
  const scheduleEvents = mergeScheduleEvents(
    undefined,
    rawRound?.scheduleEvents,
  );

  return {
    roundNumber: Number(rawRound?.roundNumber || index + 1),
    thinking: String(rawRound?.thinking || ""),
    content: String(rawRound?.content || ""),
    statusMessages,
    retryAttempts,
    errorFeedback,
    scheduleEvents,
    stats: rawRound?.stats
      ? {
          timeToFirstToken: Number(rawRound.stats.timeToFirstToken || 0),
          tokensPerSecond: Number(rawRound.stats.tokensPerSecond || 0),
          inputTokens: Number(rawRound.stats.inputTokens || 0),
          outputTokens: Number(rawRound.stats.outputTokens || 0),
          totalTokens: Number(rawRound.stats.totalTokens || 0),
          totalTime: Number(rawRound.stats.totalTime || 0),
        }
      : undefined,
  };
}

type RenderedConversationMessage = ConversationMessage & {
  parsedRounds: ConversationRound[];
  artifactPaths: string[];
};

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
  const historyPrefixRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
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
  const lastScrollTopRef = useRef(0);
  const streamingDataRef = useRef<{
    rounds: ConversationRound[];
    currentRound: StreamingRoundState;
    currentRoundNumber: number;
  }>({
    rounds: [],
    currentRound: createEmptyRoundData(),
    currentRoundNumber: 1,
  });

  const [agent, setAgent] = useState<Agent | null>(null);
  const [conversations, setConversations] = useState<
    AgentConversationSummary[]
  >([]);
  const [conversation, setConversation] =
    useState<AgentConversationDetail | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
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
  const [currentRounds, setCurrentRounds] = useState<ConversationRound[]>([]);
  const [currentRoundData, setCurrentRoundData] = useState<StreamingRoundState>(
    createEmptyRoundData(),
  );
  const [currentRoundNumber, setCurrentRoundNumber] = useState(1);
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
  const [historyItemHeights, setHistoryItemHeights] = useState<
    Record<number, number>
  >({});
  const [historyPrefixHeight, setHistoryPrefixHeight] = useState(0);

  const activeConversationId = conversationId || draftConversationId || "";

  const loadConversationData = useCallback(async () => {
    if (!agentId) {
      return;
    }

    setIsLoading(true);
    try {
      const [agentData, listData, detailData, messagesData] = await Promise.all(
        [
          agentsApi.getById(agentId),
          agentsApi.getConversations(agentId),
          conversationId
            ? agentsApi.getConversation(agentId, conversationId)
            : Promise.resolve(null),
          conversationId
            ? agentsApi.getConversationMessages(agentId, conversationId)
            : Promise.resolve(null),
        ],
      );
      setAgent(agentData);
      setConversations(listData.items);
      setConversation(detailData);
      setMessages(messagesData?.items || []);
      setHistoryItemHeights({});
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

  useEffect(() => {
    attachedFilesRef.current = attachedFiles;
  }, [attachedFiles]);

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
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        releaseRuntime();
      }
    };

    window.addEventListener("pagehide", handlePageHide);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
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
    const { rounds, currentRound, currentRoundNumber } =
      streamingDataRef.current;
    setCurrentRounds([...rounds]);
    setCurrentRoundData(buildCurrentRoundDataState(currentRound));
    setCurrentRoundNumber(currentRoundNumber);
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

  const handleHistoryItemHeightChange = useCallback(
    (index: number, height: number) => {
      const normalizedHeight = Math.max(0, Math.round(height));
      setHistoryItemHeights((prev) => {
        if (prev[index] === normalizedHeight) {
          return prev;
        }
        return {
          ...prev,
          [index]: normalizedHeight,
        };
      });
    },
    [],
  );

  const getHistoryItemHeight = useCallback(
    (index: number): number =>
      historyItemHeights[index] ?? HISTORY_MESSAGE_ESTIMATED_HEIGHT_PX,
    [historyItemHeights],
  );

  const handleMessagesScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const currentScrollTop = container.scrollTop;
    const previousScrollTop = lastScrollTopRef.current;
    lastScrollTopRef.current = currentScrollTop;

    setMessagesScrollTop(currentScrollTop);
    setMessagesViewportHeight(container.clientHeight);

    const distanceFromBottom =
      container.scrollHeight - currentScrollTop - container.clientHeight;

    if (currentScrollTop < previousScrollTop - 4) {
      shouldAutoScrollRef.current = false;
      return;
    }

    if (distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX) {
      shouldAutoScrollRef.current = true;
    }
  }, []);

  const historyVirtualization = useMemo(() => {
    const itemCount = messages.length;
    if (itemCount === 0) {
      return {
        startIndex: 0,
        endIndex: -1,
        topSpacerHeight: 0,
        bottomSpacerHeight: 0,
      };
    }

    const offsets: number[] = new Array(itemCount);
    const heights: number[] = new Array(itemCount);
    let totalHeight = 0;

    for (let index = 0; index < itemCount; index += 1) {
      offsets[index] = totalHeight;
      const height = getHistoryItemHeight(index);
      heights[index] = height;
      totalHeight += height;
    }

    const adjustedScrollTop = Math.max(
      0,
      messagesScrollTop - historyPrefixHeight,
    );
    const viewportStart = Math.max(0, adjustedScrollTop - HISTORY_OVERSCAN_PX);
    const viewportEnd =
      adjustedScrollTop +
      Math.max(messagesViewportHeight, 1) +
      HISTORY_OVERSCAN_PX;

    let startIndex = 0;
    while (
      startIndex < itemCount &&
      offsets[startIndex] + heights[startIndex] < viewportStart
    ) {
      startIndex += 1;
    }
    startIndex = Math.min(startIndex, itemCount - 1);

    let endIndex = startIndex;
    while (endIndex < itemCount && offsets[endIndex] < viewportEnd) {
      endIndex += 1;
    }
    endIndex = Math.max(startIndex, Math.min(itemCount - 1, endIndex));

    const topSpacerHeight = offsets[startIndex] ?? 0;
    const renderedEndOffset = offsets[endIndex] + heights[endIndex];
    const bottomSpacerHeight = Math.max(0, totalHeight - renderedEndOffset);

    return {
      startIndex,
      endIndex,
      topSpacerHeight,
      bottomSpacerHeight,
    };
  }, [
    getHistoryItemHeight,
    historyPrefixHeight,
    messages.length,
    messagesScrollTop,
    messagesViewportHeight,
  ]);

  const visibleHistoryIndexes = useMemo(() => {
    if (historyVirtualization.endIndex < historyVirtualization.startIndex) {
      return [] as number[];
    }

    return Array.from(
      {
        length:
          historyVirtualization.endIndex - historyVirtualization.startIndex + 1,
      },
      (_, index) => historyVirtualization.startIndex + index,
    );
  }, [historyVirtualization.endIndex, historyVirtualization.startIndex]);

  const resetStreamingState = useCallback(() => {
    if (streamFlushTimerRef.current !== null) {
      window.clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }
    setCurrentRounds([]);
    setCurrentRoundData(createEmptyRoundData());
    setCurrentRoundNumber(1);
    abortControllerRef.current = null;
    abortStreamingHandlerRef.current = null;
    streamingDataRef.current = {
      rounds: [],
      currentRound: createEmptyRoundData(),
      currentRoundNumber: 1,
    };
  }, []);

  useEffect(
    () => () => {
      if (streamFlushTimerRef.current !== null) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const syncMetrics = () => {
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
  }, [historySummary, conversation?.compactedMessageCount]);

  useEffect(() => {
    shouldAutoScrollRef.current = true;
    lastScrollTopRef.current = 0;
    setHistoryItemHeights({});
    setMessagesScrollTop(0);
    const frameId = window.requestAnimationFrame(() => {
      scrollMessagesToBottom("auto");
    });
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [activeConversationId, scrollMessagesToBottom]);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }

    const behavior: ScrollBehavior = isSending ? "auto" : "smooth";
    const frameId = window.requestAnimationFrame(() => {
      scrollMessagesToBottom(behavior);
    });
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [
    currentRoundData,
    currentRounds,
    historyItemHeights,
    historyPrefixHeight,
    isSending,
    messages,
    scrollMessagesToBottom,
    showWorkspacePanel,
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
      setConversations((prev) => {
        const deduped = prev.filter((item) => item.id !== nextItem.id);
        return [nextItem, ...deduped];
      });
    },
    [],
  );

  const syncConversationState = useCallback(
    async (targetConversationId: string, includeMessages = true) => {
      if (!agentId || !targetConversationId) return;
      try {
        const [listData, detailData, messagesData] = await Promise.all([
          agentsApi.getConversations(agentId),
          agentsApi.getConversation(agentId, targetConversationId),
          includeMessages
            ? agentsApi.getConversationMessages(agentId, targetConversationId)
            : Promise.resolve(null),
        ]);
        setConversations(listData.items);
        setConversation(detailData);
        setPendingConversationTitle(detailData.title || null);
        if (messagesData) {
          setHistoryItemHeights({});
          setMessages(messagesData.items);
          setHistorySummary(messagesData.historySummary || null);
        }
      } catch (syncError) {
        console.error("Failed to sync conversation state:", syncError);
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
    setMessages([]);
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
        setConversations(remainingConversations);

        if (item.id === activeConversationId) {
          setConversation(null);
          setMessages([]);
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

    setMessages((prev) => [...prev, optimisticMessage]);
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
    streamingDataRef.current = {
      rounds: [],
      currentRound: createEmptyRoundData(),
      currentRoundNumber: 1,
    };
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    let turnOutcome: "completed" | "cancelled" | "failed" | null = null;
    let hasFinalizedCompletedTurn = false;

    const finalizeStreamingOutput = () => {
      const completedRounds = [...streamingDataRef.current.rounds];
      if (hasRoundActivity(streamingDataRef.current.currentRound)) {
        completedRounds.push(
          buildRoundSnapshot(
            streamingDataRef.current.currentRound,
            streamingDataRef.current.currentRoundNumber,
          ),
        );
      }

      const assistantContent = completedRounds
        .map((round) => round.content.trim())
        .filter(Boolean)
        .join("\n\n")
        .trim();
      const latestStats =
        completedRounds.length > 0
          ? completedRounds[completedRounds.length - 1].stats
          : undefined;
      const scheduleEvents = completedRounds.reduce<ScheduleCreatedEvent[]>(
        (acc, round) => {
          return mergeScheduleEvents(acc, round.scheduleEvents) || acc;
        },
        [],
      );

      return {
        completedRounds,
        assistantContent,
        latestStats: latestStats || null,
        scheduleEvents,
      };
    };

    const removeOptimisticMessage = () => {
      setMessages((prev) =>
        prev.filter((message) => message.id !== optimisticMessage.id),
      );
    };

    const finalizeCompletedTurn = async () => {
      if (hasFinalizedCompletedTurn) {
        return;
      }
      hasFinalizedCompletedTurn = true;
      turnOutcome = "completed";
      shouldAutoScrollRef.current = true;
      const { assistantContent } = finalizeStreamingOutput();
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
      resetStreamingState();
      setIsCreatingConversation(false);
      setShowDraftPlaceholder(false);
      await syncConversationState(targetConversationId);
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
          if (chunk.type === "runtime") {
            const statusContent = getRuntimeStatusMessage(chunk, t);
            if (statusContent) {
              streamingDataRef.current.currentRound.statusMessages.push({
                content: statusContent,
                type: "start",
                timestamp: new Date(),
              });
            }
            scheduleStreamingStateSync(true);
            return;
          }
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

          if (chunk.type === "info") {
            const roundMatch = String(chunk.content || "").match(
              /第\s*(\d+)\s*轮/,
            );
            if (roundMatch) {
              const nextRoundNumber = parseInt(roundMatch[1], 10);
              if (hasRoundActivity(streamingDataRef.current.currentRound)) {
                streamingDataRef.current.rounds.push(
                  buildRoundSnapshot(
                    streamingDataRef.current.currentRound,
                    streamingDataRef.current.currentRoundNumber,
                  ),
                );
              }
              streamingDataRef.current.currentRoundNumber = nextRoundNumber;
              streamingDataRef.current.currentRound = createEmptyRoundData();
            }
            streamingDataRef.current.currentRound.statusMessages.push({
              content: String(chunk.content || ""),
              type: "info",
              timestamp: new Date(),
            });
          } else if (
            chunk.type === "start" ||
            chunk.type === "tool_call" ||
            chunk.type === "tool_result" ||
            chunk.type === "tool_error" ||
            chunk.type === "done" ||
            chunk.type === "error"
          ) {
            streamingDataRef.current.currentRound.statusMessages.push({
              content: String(chunk.content || ""),
              type: chunk.type as StatusMessage["type"],
              timestamp: new Date(),
            });
            if (chunk.type === "done") {
              scheduleStreamingStateSync(true);
              void finalizeCompletedTurn();
              const activeController = abortControllerRef.current;
              if (activeController) {
                activeController.abort();
              }
              return;
            }
            if (chunk.type === "error") {
              turnOutcome = "failed";
              setError(String(chunk.content || ""));
            }
          } else if (chunk.type === "thinking") {
            streamingDataRef.current.currentRound.thinking += String(
              chunk.content || "",
            );
          } else if (chunk.type === "content") {
            const chunkText = String(chunk.content || "");
            const currentContent =
              streamingDataRef.current.currentRound.content;
            const isLeadingWhitespaceOnly =
              chunkText.trim().length === 0 &&
              currentContent.trim().length === 0;

            if (isLeadingWhitespaceOnly) {
              return;
            }

            streamingDataRef.current.currentRound.content += chunkText;
          } else if (chunk.type === "schedule_created") {
            const scheduleEvent = normalizeScheduleCreatedEvent(chunk);
            if (scheduleEvent) {
              streamingDataRef.current.currentRound.scheduleEvents =
                mergeScheduleEvents(
                  streamingDataRef.current.currentRound.scheduleEvents,
                  [scheduleEvent],
                ) || [];
              addNotification({
                type: "success",
                title: t("schedules.page.createdTitle", "定时任务已创建"),
                message: `${scheduleEvent.name} ${t("schedules.page.createdSuffix", "已创建")}`,
                actionUrl: `/schedules/${scheduleEvent.schedule_id}`,
                actionLabel: t("schedules.page.viewSchedule", "查看定时任务"),
              });
              scheduleStreamingStateSync(true);
              return;
            }
          } else if (chunk.type === "retry_attempt") {
            streamingDataRef.current.currentRound.retryAttempts.push({
              retryCount: Number(chunk.retry_count || 1),
              maxRetries: Number(chunk.max_retries || 1),
              errorType: (chunk.error_type ||
                "parse_error") as RetryAttempt["errorType"],
              message: String(chunk.content || ""),
              timestamp: new Date(),
            });
          } else if (chunk.type === "error_feedback") {
            streamingDataRef.current.currentRound.errorFeedback.push({
              errorType: String(chunk.error_type || "unknown"),
              retryCount: Number(chunk.retry_count || 1),
              maxRetries: Number(chunk.max_retries || 1),
              message: String(chunk.content || ""),
              suggestions: Array.isArray(chunk.suggestions)
                ? chunk.suggestions.map(String)
                : undefined,
              timestamp: new Date(),
            });
          } else if (chunk.type === "round_stats") {
            streamingDataRef.current.currentRound.stats = {
              timeToFirstToken: Number(chunk.timeToFirstToken || 0),
              tokensPerSecond: Number(chunk.tokensPerSecond || 0),
              inputTokens: Number(chunk.inputTokens || 0),
              outputTokens: Number(chunk.outputTokens || 0),
              totalTokens:
                Number(chunk.inputTokens || 0) +
                Number(chunk.outputTokens || 0),
              totalTime: Number(chunk.totalTime || 0),
            };
          } else if (
            chunk.type === "stats" &&
            !streamingDataRef.current.currentRound.stats
          ) {
            streamingDataRef.current.currentRound.stats = {
              timeToFirstToken: Number(chunk.timeToFirstToken || 0),
              tokensPerSecond: Number(chunk.tokensPerSecond || 0),
              inputTokens: Number(chunk.inputTokens || 0),
              outputTokens: Number(chunk.outputTokens || 0),
              totalTokens: Number(chunk.totalTokens || 0),
              totalTime: Number(chunk.totalTime || 0),
            };
          }

          scheduleStreamingStateSync();
        },
        (message) => {
          if (turnOutcome !== "completed") {
            turnOutcome = turnOutcome || "failed";
            removeOptimisticMessage();
            shouldAutoScrollRef.current = true;
            resetStreamingState();
            setIsCreatingConversation(false);
            setShowDraftPlaceholder(false);
          }
          setError(message);
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
        removeOptimisticMessage();
        setIsCreatingConversation(false);
        setShowDraftPlaceholder(false);
        setError(
          sendError instanceof Error
            ? sendError.message
            : t("agent.sendMessageFailed", "Failed to send message"),
        );
      }
    } finally {
      if (turnOutcome !== "completed") {
        shouldAutoScrollRef.current = true;
        await syncConversationState(targetConversationId);
        setIsSending(false);
      }
      abortControllerRef.current = null;
      abortStreamingHandlerRef.current = null;
    }
  }, [
    addNotification,
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

  const renderedMessages = useMemo<RenderedConversationMessage[]>(() => {
    return messages.map((message) => {
      const rawRounds = Array.isArray(message.contentJson?.rounds)
        ? message.contentJson.rounds
        : [];
      const storedRounds = rawRounds.map((rawRound: any, index: number) =>
        normalizeStoredRound(rawRound, index),
      );
      const topLevelScheduleEvents = Array.isArray(
        message.contentJson?.scheduleEvents,
      )
        ? message.contentJson.scheduleEvents
        : [];
      if (topLevelScheduleEvents.length > 0) {
        if (storedRounds.length > 0) {
          const lastRoundIndex = storedRounds.length - 1;
          storedRounds[lastRoundIndex] = {
            ...storedRounds[lastRoundIndex],
            scheduleEvents: mergeScheduleEvents(
              storedRounds[lastRoundIndex].scheduleEvents,
              topLevelScheduleEvents,
            ),
          };
        } else {
          storedRounds.push(
            normalizeStoredRound(
              {
                roundNumber: 1,
                scheduleEvents: topLevelScheduleEvents,
              },
              0,
            ),
          );
        }
      }
      const artifactPaths = Array.isArray(message.contentJson?.artifacts)
        ? message.contentJson.artifacts
            .map((item: any) => normalizeWorkspaceFilePath(item?.path || ""))
            .filter(Boolean)
        : [];
      return {
        ...message,
        parsedRounds: storedRounds,
        artifactPaths,
      };
    });
  }, [messages]);

  const renderHistoryMessage = useCallback(
    (message: RenderedConversationMessage) => {
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
                          attachment.name ||
                            attachment.file_name ||
                            "Attachment",
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

      return (
        <div className="space-y-4">
          {message.parsedRounds.length > 0 ? (
            message.parsedRounds.map((round, index) => (
              <ConversationRoundComponent
                key={`${message.id}-round-${round.roundNumber}-${index}`}
                round={round}
                isLatest={index === message.parsedRounds.length - 1}
                artifacts={[
                  ...extractRoundArtifacts(round),
                  ...(
                    (index === message.parsedRounds.length - 1
                      ? message.artifactPaths
                      : []) as string[]
                  ).map((path) => ({ path, confirmed: true })),
                ].filter(
                  (artifact, artifactIndex, allArtifacts) =>
                    allArtifacts.findIndex(
                      (candidate) => candidate.path === artifact.path,
                    ) === artifactIndex,
                )}
                onOpenArtifact={handleOpenArtifactInWorkspace}
                onDownloadArtifact={handleDownloadArtifact}
                downloadingArtifactPath={downloadingArtifactPath}
                defaultCollapsed={index < message.parsedRounds.length - 1}
              />
            ))
          ) : (
            <div className="rounded-[32px] rounded-tl-none border border-zinc-200 bg-zinc-50 px-6 py-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950/40">
              <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
                <Bot className="w-4 h-4 text-emerald-500" />
                {agent?.name || "Agent"}
              </div>
              <div className="markdown-content">
                <ReactMarkdown
                  remarkPlugins={remarkPlugins}
                  components={markdownComponents}
                >
                  {message.contentText}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      );
    },
    [
      agent?.name,
      downloadingArtifactPath,
      handleDownloadArtifact,
      handleOpenArtifactInWorkspace,
      markdownComponents,
      remarkPlugins,
    ],
  );

  const currentStreamingRound = useMemo(() => {
    if (!hasRoundActivity(currentRoundData)) {
      return null;
    }
    return buildRoundSnapshot(currentRoundData, currentRoundNumber);
  }, [currentRoundData, currentRoundNumber]);

  const shouldVirtualizeHistory =
    renderedMessages.length >= HISTORY_VIRTUALIZATION_MIN_ITEMS;

  const showPendingConversationCard = showDraftPlaceholder;
  const hasVisibleConversationContent =
    renderedMessages.length > 0 ||
    currentRounds.length > 0 ||
    Boolean(currentStreamingRound);
  const showBlockingLoading = isLoading && !hasVisibleConversationContent;
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
              {conversations.length + (showPendingConversationCard ? 1 : 0)}
            </span>
          </div>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
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
            {conversations.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() =>
                  navigate(`/workforce/${agentId}/conversations/${item.id}`)
                }
                className={`w-full rounded-2xl border px-3 py-3 text-left transition-colors ${
                  item.id === activeConversationId
                    ? "border-emerald-500 bg-emerald-500/10"
                    : "border-zinc-200 bg-zinc-50 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950/60 dark:hover:bg-zinc-800/80"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      {item.title}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs text-zinc-500 dark:text-zinc-400">
                      {item.lastMessagePreview ||
                        t("agent.noMessagesYet", "No messages yet")}
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
                  </div>
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleRenameConversation(item);
                      }}
                      className="rounded-lg p-1 text-zinc-400 transition-colors hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleDeleteConversation(item);
                      }}
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
              </button>
            ))}
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
                    {historySummary &&
                      Number(conversation?.compactedMessageCount || 0) > 0 && (
                        <div className="rounded-[28px] border border-amber-200 bg-amber-50/80 px-5 py-4 dark:border-amber-900/40 dark:bg-amber-950/20">
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

                      {visibleHistoryIndexes.map((index) => {
                        const message = renderedMessages[index];
                        if (!message) {
                          return null;
                        }

                        return (
                          <VirtualizedHistoryItem
                            key={message.id}
                            index={index}
                            onHeightChange={handleHistoryItemHeightChange}
                          >
                            {renderHistoryMessage(message)}
                          </VirtualizedHistoryItem>
                        );
                      })}

                      <div
                        style={{
                          height: `${historyVirtualization.bottomSpacerHeight}px`,
                        }}
                      />
                    </>
                  ) : (
                    renderedMessages.map((message, index) => (
                      <div
                        key={message.id}
                        style={{
                          paddingBottom:
                            index < renderedMessages.length - 1
                              ? `${HISTORY_MESSAGE_GAP_PX}px`
                              : undefined,
                        }}
                      >
                        {renderHistoryMessage(message)}
                      </div>
                    ))
                  )}

                  {(currentRounds.length > 0 || currentStreamingRound) && (
                    <div
                      className="space-y-6"
                      style={{
                        paddingTop:
                          renderedMessages.length > 0
                            ? `${HISTORY_MESSAGE_GAP_PX}px`
                            : undefined,
                      }}
                    >
                      {currentRounds.map((round, index) => (
                        <ConversationRoundComponent
                          key={`stream-round-${round.roundNumber}-${index}`}
                          round={round}
                          defaultCollapsed={index < currentRounds.length - 1}
                          artifacts={extractRoundArtifacts(round)}
                          onOpenArtifact={handleOpenArtifactInWorkspace}
                          onDownloadArtifact={handleDownloadArtifact}
                          downloadingArtifactPath={downloadingArtifactPath}
                        />
                      ))}
                      {currentStreamingRound && (
                        <ConversationRoundComponent
                          round={currentStreamingRound}
                          isLatest
                          isStreaming={isSending}
                          artifacts={extractRoundArtifacts(
                            currentStreamingRound,
                          )}
                          onOpenArtifact={handleOpenArtifactInWorkspace}
                          onDownloadArtifact={handleDownloadArtifact}
                          downloadingArtifactPath={downloadingArtifactPath}
                        />
                      )}
                    </div>
                  )}

                  {error && (
                    <div
                      className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300"
                      style={{
                        marginTop:
                          renderedMessages.length > 0 ||
                          currentRounds.length > 0 ||
                          Boolean(currentStreamingRound)
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
                  disabled={isSending}
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
                  disabled={isSending}
                  rows={1}
                  className="max-h-[180px] min-h-[24px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-zinc-900 outline-none placeholder:text-zinc-400 dark:text-white"
                />
                <button
                  type="button"
                  onClick={() => {
                    void handleVoiceInput();
                  }}
                  disabled={isSending || isTranscribingVoice}
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
