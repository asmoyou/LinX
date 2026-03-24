import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import {
  X,
  Send,
  AlertCircle,
  Bot,
  Paperclip,
  Image as ImageIcon,
  FileText,
  X as XIcon,
  FolderOpen,
  Trash2,
  Maximize2,
  Minimize2,
  Cpu,
  History,
  Zap,
  Mic,
  Square,
  Loader2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Agent } from '@/types/agent';
import { agentsApi } from '@/api';
import {
  mergeScheduleEvents,
  normalizeScheduleCreatedEvent,
} from '@/components/schedules/scheduleUtils';
import { useNotificationStore } from '@/stores';
import type {
  ConversationRound,
  StatusMessage,
  RetryAttempt,
  ErrorFeedback,
  AttachedFile,
} from '@/types/streaming';
import type { ScheduleCreatedEvent } from '@/types/schedule';
import {
  ConversationRoundComponent,
  type ConversationRoundArtifact,
} from './ConversationRound';
import { SessionWorkspacePanel } from './SessionWorkspacePanel';
import { createMarkdownComponents } from './CodeBlock';
import { LayoutModal } from '@/components/LayoutModal';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';

interface TestAgentModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  rounds?: ConversationRound[]; // Multi-round execution
  attachments?: AttachedFile[];
  scheduleEvents?: ScheduleCreatedEvent[];
}

type HistoryContentItem =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } };

type HistoryPayloadMessage = {
  role: 'user' | 'assistant';
  content: string | HistoryContentItem[];
};

const STREAM_RENDER_THROTTLE_MS = 60;
const AUTO_SCROLL_THRESHOLD_PX = 120;
const HISTORY_MESSAGE_GAP_PX = 32;
const HISTORY_MESSAGE_ESTIMATED_HEIGHT_PX = 320;
const HISTORY_OVERSCAN_PX = 900;
const WORKSPACE_PATH_PATTERN = /\/workspace\/[^\s,)\]}>"'`]+/gi;
const FILE_PATH_KV_PATTERN = /file_path=([^\s,)\]}>"'`]+)/gi;
const FILE_ACTION_PATH_PATTERN = /(?:wrote|appended to|edited)\s+([^\s,)\]}>"'`]+)/gi;
const RELATIVE_FILE_PATH_PATTERN =
  /(?:^|[\s"'`(（【])((?:\.\/)?[^\s"'`<>(){}\[\]]+\.(?:md|markdown|txt|json|csv|ya?ml|pdf|docx?|xlsx?|pptx?|html?))(?=$|[\s"'`)\]}>，。；;!?])/gi;

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
  const itemRef = useRef<HTMLDivElement>(null);

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

function downloadBlob(blob: Blob, fileName: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

function normalizeWorkspaceFilePath(rawPath: string): string {
  let normalized = String(rawPath || '').trim().replace(/\\/g, '/');
  normalized = normalized.replace(/^[\s("'`[{（【]+/, '');
  normalized = normalized.replace(/[\s)"'`.,:;!?}\]）】]+$/, '');
  if (!normalized) return '';
  if (/^(?:https?:|data:|file:)/i.test(normalized)) return '';

  const workspaceIndex = normalized.indexOf('/workspace/');
  if (workspaceIndex >= 0) {
    normalized = normalized.slice(workspaceIndex);
  }

  if (normalized.startsWith('workspace/')) {
    normalized = `/${normalized}`;
  }

  if (!normalized.startsWith('/workspace/')) {
    if (normalized.startsWith('./')) {
      normalized = normalized.slice(2);
    }
    if (normalized.startsWith('/')) return '';
    normalized = `/workspace/${normalized}`;
  }

  if (normalized.includes('..')) return '';
  return normalized.startsWith('/workspace/') ? normalized : '';
}

function extractWorkspacePathsFromText(text: string): string[] {
  const source = String(text || '');
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
    if (!normalized) return;
    if (normalized.startsWith('/workspace/input/')) return;
    unique.add(normalized);
  });

  return [...unique];
}

function extractRoundArtifacts(round: ConversationRound): ConversationRoundArtifact[] {
  const paths = extractWorkspacePathsFromText(round.content || '');
  return paths.sort((a, b) => a.localeCompare(b)).map((path) => ({ path, confirmed: true }));
}

export const TestAgentModal: React.FC<TestAgentModalProps> = ({ agent, isOpen, onClose }) => {
  const { t } = useTranslation();
  const addNotification = useNotificationStore((state) => state.addNotification);
  const createEmptyRoundData = () => ({
    thinking: '',
    content: '',
    statusMessages: [] as StatusMessage[],
    retryAttempts: [] as RetryAttempt[],
    errorFeedback: [] as ErrorFeedback[],
    stats: null as ConversationRound['stats'] | null,
    scheduleEvents: [] as ScheduleCreatedEvent[],
  });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [isTranscribingVoice, setIsTranscribingVoice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [messagesScrollTop, setMessagesScrollTop] = useState(0);
  const [messagesViewportHeight, setMessagesViewportHeight] = useState(0);
  const [historyItemHeights, setHistoryItemHeights] = useState<Record<number, number>>({});

  // Current streaming state - tracks the current round being built
  const [currentRounds, setCurrentRounds] = useState<ConversationRound[]>([]);
  const [currentRoundData, setCurrentRoundData] = useState(createEmptyRoundData());

  const [currentRoundNumber, setCurrentRoundNumber] = useState(1);

  // Session state for persistent execution environment
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showWorkspacePanel, setShowWorkspacePanel] = useState(false);
  const [workspaceFocusPath, setWorkspaceFocusPath] = useState<string | null>(null);
  const [downloadingArtifactPath, setDownloadingArtifactPath] = useState<string | null>(null);
  // Use ref to track sessionId for cleanup (avoids stale closure issues)
  const sessionIdRef = useRef<string | null>(null);
  // Use ref to track agentId for cleanup (agent may be null when modal closes)
  const agentIdRef = useRef<string | null>(null);

  // Keep refs in sync with state
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    // Only update ref with valid agent IDs - keep last valid ID for cleanup
    if (agent?.id) {
      agentIdRef.current = agent.id;
    }
  }, [agent?.id]);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingStreamRef = useRef<MediaStream | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const lastStatusTimeRef = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamFlushTimerRef = useRef<number | null>(null);
  const shouldAutoScrollRef = useRef(true);

  // Use refs to track streaming data for onComplete callback
  const streamingDataRef = useRef<{
    rounds: ConversationRound[];
    currentRound: ReturnType<typeof createEmptyRoundData>;
    currentRoundNumber: number;
  }>({
    rounds: [],
    currentRound: createEmptyRoundData(),
    currentRoundNumber: 1,
  });

  const resetHistoryVirtualizationMetrics = useCallback(() => {
    setHistoryItemHeights({});
    setMessagesScrollTop(0);
  }, []);

  const hasRoundActivity = (round: {
    thinking: string;
    content: string;
    statusMessages: StatusMessage[];
    retryAttempts: RetryAttempt[];
    errorFeedback: ErrorFeedback[];
    scheduleEvents: ScheduleCreatedEvent[];
  }): boolean =>
    Boolean(
      round.thinking ||
        (round.content && round.content.trim().length > 0) ||
        round.statusMessages.length > 0 ||
        round.retryAttempts.length > 0 ||
        round.errorFeedback.length > 0 ||
        round.scheduleEvents.length > 0
    );

  const buildRoundSnapshot = (
    roundData: ReturnType<typeof createEmptyRoundData>,
    roundNumber: number
  ): ConversationRound => ({
    roundNumber,
    thinking: roundData.thinking,
    content: roundData.content,
    statusMessages: [...roundData.statusMessages],
    retryAttempts: roundData.retryAttempts.length > 0 ? [...roundData.retryAttempts] : undefined,
    errorFeedback: roundData.errorFeedback.length > 0 ? [...roundData.errorFeedback] : undefined,
    stats: roundData.stats ? { ...roundData.stats } : undefined,
    scheduleEvents:
      roundData.scheduleEvents.length > 0 ? [...roundData.scheduleEvents] : undefined,
  });

  const buildCurrentRoundDataState = (roundData: ReturnType<typeof createEmptyRoundData>) => ({
    thinking: roundData.thinking,
    content: roundData.content,
    statusMessages: [...roundData.statusMessages],
    retryAttempts: [...roundData.retryAttempts],
    errorFeedback: [...roundData.errorFeedback],
    stats: roundData.stats ? { ...roundData.stats } : null,
    scheduleEvents: [...roundData.scheduleEvents],
  });

  const syncStreamingStateToView = useCallback(() => {
    const { rounds, currentRound, currentRoundNumber } = streamingDataRef.current;
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
    [syncStreamingStateToView]
  );

  const commitStreamingOutputToMessages = () => {
    const { rounds, currentRound, currentRoundNumber } = streamingDataRef.current;
    const finalizedRounds = [...rounds];

    if (hasRoundActivity(currentRound)) {
      finalizedRounds.push(buildRoundSnapshot(currentRound, currentRoundNumber));
    }

    if (finalizedRounds.length === 0) {
      return;
    }

    const finalContentRound = [...finalizedRounds]
      .reverse()
      .find((round) => Boolean(round.content && round.content.trim()));
    const assistantContent = finalContentRound?.content?.trim() || '';
    const scheduleEvents = finalizedRounds.reduce<ScheduleCreatedEvent[]>((acc, round) => {
      return mergeScheduleEvents(acc, round.scheduleEvents) || acc;
    }, []);

    const newMessage: Message = {
      role: 'assistant',
      content: assistantContent,
      timestamp: new Date(),
      rounds: finalizedRounds,
      scheduleEvents,
    };

    setMessages((prev) => [...prev, newMessage]);
  };

  const resetStreamingState = () => {
    if (streamFlushTimerRef.current !== null) {
      window.clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }
    setCurrentRounds([]);
    setCurrentRoundData(createEmptyRoundData());
    setCurrentRoundNumber(1);
    setIsStreaming(false);
    abortControllerRef.current = null;
    streamingDataRef.current = {
      rounds: [],
      currentRound: createEmptyRoundData(),
      currentRoundNumber: 1,
    };
  };

  // Memoize markdown components to prevent re-creation on each render
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);
  const remarkPlugins = useMemo(() => [remarkGfm], []);

  const scrollMessagesToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
  }, []);

  const handleHistoryItemHeightChange = useCallback((index: number, height: number) => {
    const normalized = Math.max(0, Math.round(height));
    setHistoryItemHeights((prev) => {
      if (prev[index] === normalized) {
        return prev;
      }
      return {
        ...prev,
        [index]: normalized,
      };
    });
  }, []);

  const getHistoryItemHeight = useCallback(
    (index: number): number => historyItemHeights[index] ?? HISTORY_MESSAGE_ESTIMATED_HEIGHT_PX,
    [historyItemHeights]
  );

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

    for (let i = 0; i < itemCount; i += 1) {
      offsets[i] = totalHeight;
      const height = getHistoryItemHeight(i);
      heights[i] = height;
      totalHeight += height;
    }

    const viewportStart = Math.max(0, messagesScrollTop - HISTORY_OVERSCAN_PX);
    const viewportEnd =
      messagesScrollTop + Math.max(messagesViewportHeight, 1) + HISTORY_OVERSCAN_PX;

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
  }, [getHistoryItemHeight, messages.length, messagesScrollTop, messagesViewportHeight]);

  const visibleHistoryIndexes = useMemo(() => {
    if (historyVirtualization.endIndex < historyVirtualization.startIndex) {
      return [] as number[];
    }

    return Array.from(
      { length: historyVirtualization.endIndex - historyVirtualization.startIndex + 1 },
      (_, idx) => historyVirtualization.startIndex + idx
    );
  }, [historyVirtualization.endIndex, historyVirtualization.startIndex]);

  const handleMessagesScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    setMessagesScrollTop(container.scrollTop);
    setMessagesViewportHeight(container.clientHeight);

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX;
  }, []);

  useEffect(
    () => () => {
      if (streamFlushTimerRef.current !== null) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    },
    []
  );

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const syncMetrics = () => {
      setMessagesScrollTop(container.scrollTop);
      setMessagesViewportHeight(container.clientHeight);
    };

    syncMetrics();
    const observer = new ResizeObserver(syncMetrics);
    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, [isOpen, showWorkspacePanel, isFullscreen]);

  useEffect(() => {
    if (!isOpen) return;
    shouldAutoScrollRef.current = true;
    const rafId = window.requestAnimationFrame(() => {
      scrollMessagesToBottom('auto');
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [isOpen, scrollMessagesToBottom]);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }

    const behavior: ScrollBehavior = isStreaming ? 'auto' : 'smooth';
    const rafId = window.requestAnimationFrame(() => {
      scrollMessagesToBottom(behavior);
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [
    messages,
    currentRounds,
    currentRoundData,
    historyItemHeights,
    isStreaming,
    showWorkspacePanel,
    scrollMessagesToBottom,
  ]);

  const handleOpenArtifactInWorkspace = useCallback((path: string) => {
    const normalizedPath = normalizeWorkspaceFilePath(path);
    if (!normalizedPath) return;
    setWorkspaceFocusPath(normalizedPath);
    setShowWorkspacePanel(true);
  }, []);

  const handleDownloadArtifact = useCallback(
    async (path: string) => {
      const normalizedPath = normalizeWorkspaceFilePath(path);
      if (!normalizedPath) return;

      if (!sessionId || !agent?.id) {
        setError('No active session for downloading this file.');
        return;
      }

      setDownloadingArtifactPath(normalizedPath);
      try {
        const blob = await agentsApi.downloadSessionWorkspaceFile(
          agent.id,
          sessionId,
          normalizedPath
        );
        const filename = normalizedPath.split('/').filter(Boolean).pop() || 'artifact';
        downloadBlob(blob, filename);
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Failed to download output file';
        setError(message);
      } finally {
        setDownloadingArtifactPath(null);
      }
    },
    [agent?.id, sessionId]
  );

  const renderHistoryMessage = useCallback(
    (message: Message) => {
      if (message.role === 'user') {
        return (
          <div className="flex justify-end group">
            <div className="max-w-[80%] space-y-2">
              <div className="relative">
                <div className="rounded-[24px] rounded-tr-none px-5 py-3.5 bg-indigo-600 dark:bg-indigo-500 text-white shadow-xl shadow-indigo-500/10">
                  <p className="text-sm font-medium whitespace-pre-wrap leading-relaxed">
                    {message.content}
                  </p>

                  {message.attachments && message.attachments.length > 0 && (
                    <div className="mt-3 grid grid-cols-1 gap-2">
                      {message.attachments.map((attachment) => (
                        <div
                          key={attachment.id}
                          className="flex items-center gap-3 p-2.5 bg-white/10 rounded-xl backdrop-blur-sm border border-white/10"
                        >
                          <div className="p-2 bg-white/20 rounded-lg">
                            {attachment.type === 'image' ? (
                              <ImageIcon className="w-4 h-4" />
                            ) : (
                              <FileText className="w-4 h-4" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] font-bold truncate">{attachment.file.name}</p>
                            <p className="text-[10px] opacity-70">
                              {(attachment.file.size / 1024).toFixed(1)} KB
                            </p>
                          </div>
                          {attachment.preview && (
                            <img
                              src={attachment.preview}
                              alt=""
                              className="w-10 h-10 object-cover rounded-lg border border-white/20"
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="absolute top-0 -right-2 w-4 h-4 text-indigo-600 dark:text-indigo-500 overflow-hidden">
                  <div className="absolute top-0 right-0 w-4 h-4 bg-current rotate-45 transform origin-top-right rounded-sm" />
                </div>
              </div>
              <p className="text-[10px] font-bold text-zinc-400 dark:text-zinc-600 uppercase tracking-widest text-right px-1">
                {message.timestamp.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
            </div>
          </div>
        );
      }

      if (message.role === 'system') {
        return (
          <div className="flex justify-center">
            <div className="px-5 py-2 bg-zinc-100 dark:bg-zinc-900/50 rounded-full border border-zinc-200/50 dark:border-zinc-800/50">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-500">
                {message.content}
              </p>
            </div>
          </div>
        );
      }

      return (
        <div className="flex justify-start">
          <div className="max-w-[90%] space-y-4">
            {message.rounds && message.rounds.length > 0 ? (
              <div className="space-y-6">
                {message.rounds.map((round, roundIdx) => (
                  <ConversationRoundComponent
                    key={`${message.timestamp.getTime()}-${round.roundNumber}-${roundIdx}`}
                    round={round}
                    isLatest={roundIdx === message.rounds!.length - 1}
                    artifacts={extractRoundArtifacts(round)}
                    onOpenArtifact={handleOpenArtifactInWorkspace}
                    onDownloadArtifact={handleDownloadArtifact}
                    downloadingArtifactPath={downloadingArtifactPath}
                    defaultCollapsed={roundIdx < message.rounds!.length - 1}
                  />
                ))}
                <p className="text-[10px] font-bold text-zinc-400 dark:text-zinc-600 uppercase tracking-widest px-1">
                  {message.timestamp.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
            ) : (
              <div className="rounded-[32px] rounded-tl-none px-6 py-5 bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800 shadow-sm relative">
                <div className="absolute top-0 -left-2 w-4 h-4 text-zinc-50 dark:text-zinc-900 overflow-hidden">
                  <div className="absolute top-0 left-0 w-4 h-4 bg-current -rotate-45 transform origin-top-left rounded-sm" />
                </div>
                <div className="markdown-content">
                  <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
                    {message.content}
                  </ReactMarkdown>
                </div>
                <div className="mt-4 pt-4 border-t border-zinc-200/60 dark:border-zinc-800 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Bot className="w-3.5 h-3.5 text-indigo-500" />
                    <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-600 uppercase tracking-widest">
                      {agent?.name}
                    </span>
                  </div>
                  <p className="text-[10px] font-bold text-zinc-400 dark:text-zinc-600 uppercase tracking-widest">
                    {message.timestamp.toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
              </div>
            )}
          </div>
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
    ]
  );

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
      if (recorder.state !== 'inactive') {
        recorder.stop();
      }
    }
    releaseVoiceRecordingResources();
  }, [releaseVoiceRecordingResources]);

  const resolveVoiceFileExtension = useCallback((mimeType: string): string => {
    const normalized = String(mimeType || '').toLowerCase();
    if (normalized.includes('wav')) return 'wav';
    if (normalized.includes('mp4') || normalized.includes('m4a')) return 'm4a';
    if (normalized.includes('flac')) return 'flac';
    if (normalized.includes('ogg')) return 'ogg';
    if (normalized.includes('aac')) return 'aac';
    if (normalized.includes('mpeg') || normalized.includes('mp3')) return 'mp3';
    return 'webm';
  }, []);

  const transcribeVoiceBlob = useCallback(
    async (audioBlob: Blob, mimeType: string) => {
      if (!audioBlob.size) {
        setError(t('agent.voiceInputEmpty'));
        return;
      }

      setIsTranscribingVoice(true);
      setError(null);
      try {
        const extension = resolveVoiceFileExtension(mimeType);
        const timestamp = Date.now();
        const audioFile = new File([audioBlob], `voice-input-${timestamp}.${extension}`, {
          type: mimeType || `audio/${extension}`,
        });

        const response = await agentsApi.transcribeVoiceInput(audioFile);
        const transcript = String(response.text || '').trim();

        if (!transcript) {
          setError(t('agent.voiceInputEmpty'));
          return;
        }

        setInputMessage((prev) => {
          if (!prev.trim()) {
            return transcript;
          }
          return `${prev}${/\s$/.test(prev) ? '' : ' '}${transcript}`;
        });
        inputRef.current?.focus();
      } catch (err) {
        setError(err instanceof Error ? err.message : t('agent.voiceInputFailed'));
      } finally {
        setIsTranscribingVoice(false);
      }
    },
    [resolveVoiceFileExtension, t]
  );

  const startVoiceRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError(t('agent.voiceInputUnsupported'));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordingStreamRef.current = stream;

      const preferredMimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
        'audio/ogg;codecs=opus',
        'audio/ogg',
      ];

      const selectedMimeType = preferredMimeTypes.find((type) =>
        MediaRecorder.isTypeSupported(type)
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
        setError(t('agent.voiceInputFailed'));
        cancelVoiceRecording();
      };

      recorder.onstop = () => {
        const finalMimeType = recorder.mimeType || selectedMimeType || 'audio/webm';
        const chunks = [...recordingChunksRef.current];
        releaseVoiceRecordingResources();
        void transcribeVoiceBlob(new Blob(chunks, { type: finalMimeType }), finalMimeType);
      };

      recorder.start();
      setError(null);
      setIsRecordingVoice(true);
    } catch (err) {
      const isPermissionDenied =
        err instanceof DOMException &&
        (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError');

      setError(
        isPermissionDenied
          ? t('agent.voiceInputPermissionDenied')
          : err instanceof Error
            ? err.message
            : t('agent.voiceInputFailed')
      );
      cancelVoiceRecording();
    }
  }, [cancelVoiceRecording, releaseVoiceRecordingResources, t, transcribeVoiceBlob]);

  const handleVoiceInput = useCallback(async () => {
    if (isStreaming || isTranscribingVoice) return;

    const recorder = mediaRecorderRef.current;
    if (isRecordingVoice && recorder && recorder.state !== 'inactive') {
      recorder.stop();
      return;
    }

    await startVoiceRecording();
  }, [isRecordingVoice, isStreaming, isTranscribingVoice, startVoiceRecording]);

  useEffect(
    () => () => {
      const recorder = mediaRecorderRef.current;
      if (recorder) {
        recorder.ondataavailable = null;
        recorder.onerror = null;
        recorder.onstop = null;
        if (recorder.state !== 'inactive') {
          recorder.stop();
        }
      }
      if (recordingStreamRef.current) {
        recordingStreamRef.current.getTracks().forEach((track) => track.stop());
        recordingStreamRef.current = null;
      }
    },
    []
  );

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      if (messages.length === 0) {
        setMessages([
          {
            role: 'system',
            content: `${t('agent.testConversation')} - ${agent?.name}`,
            timestamp: new Date(),
          },
        ]);
      }
    }
  }, [isOpen, agent?.name, t, messages.length]);

  // Reset state when modal closes and clean up session
  useEffect(() => {
    if (!isOpen) {
      // Abort any in-flight streaming connection FIRST
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }

      cancelVoiceRecording();
      setIsTranscribingVoice(false);

      // End the session to clean up resources (best-effort)
      const currentSessionId = sessionIdRef.current;
      const currentAgentId = agentIdRef.current;

      if (currentSessionId && currentAgentId) {
        void agentsApi.endSession(currentAgentId, currentSessionId).then((result) => {
          if (!result.success) {
            console.warn(
              `[TestAgentModal] Session cleanup failed for ${currentSessionId}: ` +
                `${result.error || 'unknown error'}`
            );
          }
        });
      }

      // Reset all state
      if (streamFlushTimerRef.current !== null) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
      resetHistoryVirtualizationMetrics();
      setMessages([]);
      setInputMessage('');
      setAttachedFiles([]);
      setCurrentRounds([]);
      setCurrentRoundData(createEmptyRoundData());
      setCurrentRoundNumber(1);
      setSessionId(null);
      setShowWorkspacePanel(false);
      setWorkspaceFocusPath(null);
      setDownloadingArtifactPath(null);
      sessionIdRef.current = null;
      agentIdRef.current = null;
      setError(null);
      setIsStreaming(false);
      setIsFullscreen(false);
    }
  }, [cancelVoiceRecording, isOpen, resetHistoryVirtualizationMetrics]);

  useEffect(() => {
    if (!sessionId) {
      setShowWorkspacePanel(false);
      setWorkspaceFocusPath(null);
    }
  }, [sessionId]);

  if (!isOpen || !agent) return null;

  const inferAttachmentType = (file: File): AttachedFile['type'] => {
    const mime = (file.type || '').toLowerCase();
    const filename = (file.name || '').toLowerCase();
    const ext = filename.includes('.') ? filename.slice(filename.lastIndexOf('.')) : '';

    if (mime.startsWith('image/')) {
      return 'image';
    }

    const documentExts = new Set([
      '.pdf',
      '.doc',
      '.docx',
      '.pptx',
      '.xls',
      '.xlsx',
      '.txt',
      '.md',
      '.markdown',
      '.html',
      '.htm',
      '.csv',
    ]);

    if (
      documentExts.has(ext) ||
      mime.includes('pdf') ||
      mime.includes('document') ||
      mime.includes('text/') ||
      mime.includes('markdown') ||
      mime.includes('spreadsheet') ||
      mime.includes('excel') ||
      mime.includes('presentation')
    ) {
      return 'document';
    }

    return 'other';
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);

    files.forEach((file) => {
      const fileType = inferAttachmentType(file);

      const newFile: AttachedFile = {
        id: Math.random().toString(36).substring(2, 11),
        file,
        type: fileType,
      };

      // Create preview for images
      if (fileType === 'image') {
        const reader = new FileReader();
        reader.onload = (e) => {
          setAttachedFiles((prev) =>
            prev.map((f) =>
              f.id === newFile.id ? { ...f, preview: e.target?.result as string } : f
            )
          );
        };
        reader.readAsDataURL(file);
      }

      setAttachedFiles((prev) => [...prev, newFile]);
    });

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const removeFile = (fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const readImageAsDataUrl = (file: File): Promise<string | null> =>
    new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const raw = typeof reader.result === 'string' ? reader.result : '';
        if (raw.startsWith('data:image/')) {
          resolve(raw);
          return;
        }
        resolve(null);
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });

  const buildHistoryContent = async (
    message: Message
  ): Promise<string | HistoryContentItem[] | null> => {
    const normalizedText = typeof message.content === 'string' ? message.content.trim() : '';
    const imageAttachments = (message.attachments ?? []).filter((item) => item.type === 'image');

    if (imageAttachments.length === 0) {
      return normalizedText || null;
    }

    const multimodalItems: HistoryContentItem[] = [];
    if (normalizedText) {
      multimodalItems.push({ type: 'text', text: normalizedText });
    }

    for (const attachment of imageAttachments) {
      let imageUrl =
        typeof attachment.preview === 'string' && attachment.preview.startsWith('data:image/')
          ? attachment.preview
          : null;

      if (!imageUrl) {
        imageUrl = await readImageAsDataUrl(attachment.file);
      }

      if (!imageUrl) {
        continue;
      }

      multimodalItems.push({
        type: 'image_url',
        image_url: { url: imageUrl },
      });
    }

    if (multimodalItems.length === 0) {
      return normalizedText || null;
    }

    return multimodalItems;
  };

  const buildConversationHistory = async (): Promise<HistoryPayloadMessage[]> => {
    const history: HistoryPayloadMessage[] = [];

    for (const message of messages) {
      if (message.role === 'system') {
        continue;
      }

      const content = await buildHistoryContent(message);
      if (!content) {
        continue;
      }

      history.push({
        role: message.role,
        content,
      });
    }

    return history;
  };

  const handleClearChat = () => {
    if (isStreaming) return;
    resetHistoryVirtualizationMetrics();
    setMessages([
      {
        role: 'system',
        content: `${t('agent.testConversation')} - ${agent?.name}`,
        timestamp: new Date(),
      },
    ]);
    setError(null);
    setWorkspaceFocusPath(null);
    setDownloadingArtifactPath(null);
  };

  const handleSendMessage = async () => {
    if ((!inputMessage.trim() && attachedFiles.length === 0) || isStreaming || isRecordingVoice) {
      return;
    }

    const userMessage: Message = {
      role: 'user',
      content: inputMessage.trim() || '[Attached files]',
      timestamp: new Date(),
      attachments: attachedFiles.length > 0 ? [...attachedFiles] : undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');
    setAttachedFiles([]);
    setError(null);
    setIsStreaming(true);
    shouldAutoScrollRef.current = true;
    if (streamFlushTimerRef.current !== null) {
      window.clearTimeout(streamFlushTimerRef.current);
      streamFlushTimerRef.current = null;
    }

    // Reset streaming state
    setCurrentRounds([]);
    setCurrentRoundData(createEmptyRoundData());
    setCurrentRoundNumber(1);
    lastStatusTimeRef.current = Date.now();

    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();

    // Reset streaming data ref
    streamingDataRef.current = {
      rounds: [],
      currentRound: createEmptyRoundData(),
      currentRoundNumber: 1,
    };

    // Build conversation history (exclude system messages).
    // Preserve image attachments in history as multimodal image_url items.
    const history = await buildConversationHistory();

    try {
      const filesToUpload = attachedFiles.map((af) => af.file);

      await agentsApi.testAgent(
        agent.id,
        userMessage.content,
        (chunk) => {
          // Handle session event
          if (chunk.type === 'session') {
            const receivedSessionId = chunk.session_id;
            if (receivedSessionId) {
              setSessionId(receivedSessionId);
            }
            return;
          }

          // Handle different message types
          if (chunk.type === 'info') {
            const roundMatch = chunk.content.match(/第\s*(\d+)\s*轮/);
            if (roundMatch) {
              const newRoundNumber = parseInt(roundMatch[1], 10);

              if (hasRoundActivity(streamingDataRef.current.currentRound)) {
                const completedRound = buildRoundSnapshot(
                  streamingDataRef.current.currentRound,
                  streamingDataRef.current.currentRoundNumber
                );

                streamingDataRef.current.rounds.push(completedRound);
              }

              streamingDataRef.current.currentRoundNumber = newRoundNumber;
              streamingDataRef.current.currentRound = createEmptyRoundData();
              scheduleStreamingStateSync(true);
            }

            const now = Date.now();
            const duration = (now - lastStatusTimeRef.current) / 1000;

            if (streamingDataRef.current.currentRound.statusMessages.length > 0) {
              const lastIndex = streamingDataRef.current.currentRound.statusMessages.length - 1;
              streamingDataRef.current.currentRound.statusMessages[lastIndex].duration = duration;
            }

            const newStatus: StatusMessage = {
              content: chunk.content,
              type: 'info',
              timestamp: new Date(),
              duration: undefined,
            };

            streamingDataRef.current.currentRound.statusMessages.push(newStatus);
            scheduleStreamingStateSync();
            lastStatusTimeRef.current = now;
          } else if (chunk.type === 'retry_attempt') {
            const retry: RetryAttempt = {
              retryCount: chunk.retry_count,
              maxRetries: chunk.max_retries,
              errorType: chunk.error_type,
              message: chunk.content,
              timestamp: new Date(),
            };

            streamingDataRef.current.currentRound.retryAttempts.push(retry);
            scheduleStreamingStateSync();
          } else if (chunk.type === 'error_feedback') {
            const feedback: ErrorFeedback = {
              errorType: chunk.error_type,
              retryCount: chunk.retry_count,
              maxRetries: chunk.max_retries,
              message: chunk.content,
              suggestions: chunk.suggestions,
              timestamp: new Date(),
            };

            streamingDataRef.current.currentRound.errorFeedback.push(feedback);
            scheduleStreamingStateSync();
          } else if (
            chunk.type === 'start' ||
            chunk.type === 'tool_call' ||
            chunk.type === 'tool_result' ||
            chunk.type === 'tool_error'
          ) {
            const now = Date.now();
            const duration = (now - lastStatusTimeRef.current) / 1000;

            if (streamingDataRef.current.currentRound.statusMessages.length > 0) {
              const lastIndex = streamingDataRef.current.currentRound.statusMessages.length - 1;
              streamingDataRef.current.currentRound.statusMessages[lastIndex].duration = duration;
            }

            const newStatus: StatusMessage = {
              content: chunk.content,
              type: chunk.type as StatusMessage['type'],
              timestamp: new Date(),
              duration: undefined,
            };

            streamingDataRef.current.currentRound.statusMessages.push(newStatus);
            scheduleStreamingStateSync();
            lastStatusTimeRef.current = now;
          } else if (chunk.type === 'done') {
            const now = Date.now();
            const duration = (now - lastStatusTimeRef.current) / 1000;

            if (streamingDataRef.current.currentRound.statusMessages.length > 0) {
              const lastIndex = streamingDataRef.current.currentRound.statusMessages.length - 1;
              streamingDataRef.current.currentRound.statusMessages[lastIndex].duration = duration;
            }

            streamingDataRef.current.currentRound.statusMessages.push({
              content: chunk.content,
              type: 'done',
              timestamp: new Date(),
              duration: undefined,
            });

            // Backend may keep SSE open briefly after sending done; stop UI waiting immediately.
            const activeController = abortControllerRef.current;
            if (activeController) {
              activeController.abort();
            }

            commitStreamingOutputToMessages();
            resetStreamingState();
            return;
          } else if (chunk.type === 'thinking') {
            streamingDataRef.current.currentRound.thinking += chunk.content;
            scheduleStreamingStateSync();
          } else if (chunk.type === 'content') {
            const chunkText = String(chunk.content ?? '');
            const currentContent = streamingDataRef.current.currentRound.content;
            const isLeadingWhitespaceOnly =
              chunkText.trim().length === 0 && currentContent.trim().length === 0;

            if (isLeadingWhitespaceOnly) {
              return;
            }

            streamingDataRef.current.currentRound.content += chunkText;
            scheduleStreamingStateSync();
          } else if (chunk.type === 'schedule_created') {
            const scheduleEvent = normalizeScheduleCreatedEvent(chunk);
            if (scheduleEvent) {
              streamingDataRef.current.currentRound.scheduleEvents =
                mergeScheduleEvents(
                  streamingDataRef.current.currentRound.scheduleEvents,
                  [scheduleEvent]
                ) || [];
              addNotification({
                type: 'success',
                title: t('schedules.page.createdTitle', '定时任务已创建'),
                message: `${scheduleEvent.name} ${t('schedules.page.createdSuffix', '已创建')}`,
                actionUrl: `/schedules/${scheduleEvent.schedule_id}`,
                actionLabel: t('schedules.page.viewSchedule', '查看定时任务'),
              });
              scheduleStreamingStateSync(true);
            }
          } else if (chunk.type === 'round_stats') {
            const roundStats = {
              timeToFirstToken: chunk.timeToFirstToken,
              tokensPerSecond: chunk.tokensPerSecond,
              inputTokens: chunk.inputTokens,
              outputTokens: chunk.outputTokens,
              totalTokens: (chunk.inputTokens || 0) + (chunk.outputTokens || 0),
              totalTime: chunk.totalTime,
            };
            streamingDataRef.current.currentRound.stats = roundStats;
            scheduleStreamingStateSync();
          } else if (chunk.type === 'stats') {
            const stats = {
              timeToFirstToken: chunk.timeToFirstToken,
              tokensPerSecond: chunk.tokensPerSecond,
              inputTokens: chunk.inputTokens,
              outputTokens: chunk.outputTokens,
              totalTokens: chunk.totalTokens,
              totalTime: chunk.totalTime,
            };
            if (!streamingDataRef.current.currentRound.stats) {
              streamingDataRef.current.currentRound.stats = stats;
              scheduleStreamingStateSync();
            }
          } else if (chunk.type === 'error') {
            const now = Date.now();
            const duration = (now - lastStatusTimeRef.current) / 1000;

            if (streamingDataRef.current.currentRound.statusMessages.length > 0) {
              const lastIndex = streamingDataRef.current.currentRound.statusMessages.length - 1;
              streamingDataRef.current.currentRound.statusMessages[lastIndex].duration = duration;
            }

            const errorStatus: StatusMessage = {
              content: chunk.content,
              type: 'error',
              timestamp: new Date(),
              duration: undefined,
            };
            streamingDataRef.current.currentRound.statusMessages.push(errorStatus);
            scheduleStreamingStateSync();
            lastStatusTimeRef.current = now;
            setError(chunk.content);
          }
        },
        (error) => {
          setError(error);
          scheduleStreamingStateSync(true);
          commitStreamingOutputToMessages();
          resetStreamingState();
        },
        () => {
          scheduleStreamingStateSync(true);
          commitStreamingOutputToMessages();
          resetStreamingState();
        },
        history,
        filesToUpload.length > 0 ? filesToUpload : undefined,
        abortControllerRef.current?.signal,
        sessionId || undefined
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      scheduleStreamingStateSync(true);
      commitStreamingOutputToMessages();
      resetStreamingState();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleAbortStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();

      const now = Date.now();
      const duration = (now - lastStatusTimeRef.current) / 1000;
      if (streamingDataRef.current.currentRound.statusMessages.length > 0) {
        const lastIndex = streamingDataRef.current.currentRound.statusMessages.length - 1;
        streamingDataRef.current.currentRound.statusMessages[lastIndex].duration = duration;
      }
      streamingDataRef.current.currentRound.statusMessages.push({
        content: t('agent.details.statusValue.offline'), // Reusing "offline" as a proxy for "cancelled/stopped" or use a literal
        type: 'info',
        timestamp: new Date(),
        duration: undefined,
      });

      scheduleStreamingStateSync(true);
      commitStreamingOutputToMessages();
      resetStreamingState();
      setError(null);
    }
  };

  const currentStreamingRound: ConversationRound = {
    roundNumber: currentRoundNumber,
    thinking: currentRoundData.thinking,
    content: currentRoundData.content,
    statusMessages: currentRoundData.statusMessages,
    retryAttempts:
      currentRoundData.retryAttempts.length > 0 ? currentRoundData.retryAttempts : undefined,
    errorFeedback:
      currentRoundData.errorFeedback.length > 0 ? currentRoundData.errorFeedback : undefined,
    stats: currentRoundData.stats || undefined,
    scheduleEvents:
      currentRoundData.scheduleEvents.length > 0 ? currentRoundData.scheduleEvents : undefined,
  };

  return (
    <LayoutModal isOpen={isOpen} onClose={onClose} closeOnBackdropClick={false} closeOnEscape={true}>
      <div
        className={`w-full transition-[max-width,height] duration-500 ease-in-out flex flex-col modal-panel rounded-[32px] shadow-2xl overflow-hidden bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 ${
          isFullscreen ? 'max-w-[98vw] h-[95vh]' : 'max-w-5xl h-[85vh]'
        }`}
      >
        {/* Header - Unified with Agent Style */}
        <div className="bg-zinc-50 dark:bg-zinc-900 px-6 py-5 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center text-white shadow-lg shrink-0">
              {agent.avatar ? (
                <img src={agent.avatar} alt="" className="w-full h-full object-cover rounded-2xl" />
              ) : (
                <Bot className="w-6 h-6" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-black text-zinc-900 dark:text-zinc-100 tracking-tight">
                  {agent.name}
                </h2>
                <div className="px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold uppercase tracking-widest border border-emerald-100 dark:border-emerald-800/50">
                  {t('agent.testAgent')}
                </div>
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 font-medium">
                {agent.model} • {agent.provider}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleClearChat}
              disabled={isStreaming || messages.length <= 1}
              className="p-2.5 rounded-xl transition-all bg-white hover:bg-zinc-100 text-zinc-500 border border-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:text-zinc-400 dark:border-zinc-700 disabled:opacity-30"
              title={t('common.delete')}
            >
              <Trash2 className="w-5 h-5" />
            </button>
            <button
              onClick={() => setShowWorkspacePanel((prev) => !prev)}
              disabled={!sessionId}
              className={`p-2.5 rounded-xl transition-all border ${
                showWorkspacePanel
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-600 dark:bg-indigo-900/30 dark:border-indigo-800 dark:text-indigo-400'
                  : 'bg-white border-zinc-200 text-zinc-500 dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-400'
              } hover:bg-zinc-100 dark:hover:bg-zinc-700 disabled:opacity-30`}
              title="Workspace"
            >
              <FolderOpen className="w-5 h-5" />
            </button>
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2.5 rounded-xl transition-all bg-white hover:bg-zinc-100 text-zinc-500 border border-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:text-zinc-400 dark:border-zinc-700"
            >
              {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            </button>
            <div className="w-px h-6 bg-zinc-200 dark:bg-zinc-800 mx-1" />
            <button
              onClick={onClose}
              className="p-2.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-xl transition-colors"
            >
              <X className="w-6 h-6 text-zinc-400 dark:text-zinc-500" />
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex overflow-hidden bg-white dark:bg-zinc-950">
          {/* Messages Area */}
          <div
            ref={messagesContainerRef}
            onScroll={handleMessagesScroll}
            className="flex-1 min-w-0 overflow-y-auto px-6 py-8 custom-scrollbar"
          >
            <div className="flex flex-col">
              <div style={{ height: `${historyVirtualization.topSpacerHeight}px` }} />

              {visibleHistoryIndexes.map((index) => {
                const message = messages[index];
                if (!message) return null;

                return (
                  <VirtualizedHistoryItem
                    key={`${message.timestamp.getTime()}-${index}`}
                    index={index}
                    onHeightChange={handleHistoryItemHeightChange}
                  >
                    {renderHistoryMessage(message)}
                  </VirtualizedHistoryItem>
                );
              })}

              <div style={{ height: `${historyVirtualization.bottomSpacerHeight}px` }} />

              {(isStreaming || error) && (
                <div
                  className="space-y-8"
                  style={{
                    paddingTop: messages.length > 0 ? `${HISTORY_MESSAGE_GAP_PX}px` : undefined,
                  }}
                >
                  {/* Current streaming rounds */}
                  {isStreaming && (currentRounds.length > 0 || hasRoundActivity(currentRoundData)) && (
                    <div className="flex justify-start">
                      <div className="max-w-[90%] space-y-6">
                        {currentRounds.map((round, idx) => (
                          <ConversationRoundComponent
                            key={`stream-round-${round.roundNumber}-${idx}`}
                            round={round}
                            isLatest={false}
                            artifacts={extractRoundArtifacts(round)}
                            onOpenArtifact={handleOpenArtifactInWorkspace}
                            onDownloadArtifact={handleDownloadArtifact}
                            downloadingArtifactPath={downloadingArtifactPath}
                            defaultCollapsed={true}
                          />
                        ))}

                        <ConversationRoundComponent
                          round={currentStreamingRound}
                          isLatest={true}
                          isStreaming={true}
                          artifacts={extractRoundArtifacts(currentStreamingRound)}
                          onOpenArtifact={handleOpenArtifactInWorkspace}
                          onDownloadArtifact={handleDownloadArtifact}
                          downloadingArtifactPath={downloadingArtifactPath}
                        />
                      </div>
                    </div>
                  )}

                  {/* Typing Indicator */}
                  {isStreaming && !hasRoundActivity(currentRoundData) && (
                    <div className="flex justify-start">
                      <div className="px-5 py-3 rounded-2xl rounded-tl-none bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800">
                        <div className="flex gap-1.5">
                          {[0, 1, 2].map((i) => (
                            <motion.div
                              key={i}
                              className="w-1.5 h-1.5 rounded-full bg-indigo-400 dark:bg-indigo-600"
                              animate={{ opacity: [0.3, 1, 0.3], y: [0, -4, 0] }}
                              transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }}
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Error Message */}
                  {error && (
                    <div className="flex justify-center">
                      <div className="max-w-[80%] rounded-2xl p-4 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex items-start gap-3 shadow-xl shadow-rose-500/5">
                        <div className="p-2 rounded-xl bg-rose-100 dark:bg-rose-900/50 text-rose-600 dark:text-rose-400">
                          <AlertCircle className="w-5 h-5" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm font-black text-rose-900 dark:text-rose-200 uppercase tracking-tight">
                            System Error
                          </p>
                          <p className="text-xs text-rose-700 dark:text-rose-400 mt-1 font-medium leading-relaxed">
                            {error}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Workspace Panel Container */}
          {showWorkspacePanel && (
            <div className="w-[400px] shrink-0 border-l border-zinc-100 dark:border-zinc-800">
              <SessionWorkspacePanel
                agentId={agent.id}
                sessionId={sessionId}
                isOpen={showWorkspacePanel}
                focusPath={workspaceFocusPath}
                onClose={() => setShowWorkspacePanel(false)}
              />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-6 border-t border-zinc-100 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50">
          <div className="max-w-4xl mx-auto space-y-4">
            {/* Attached Files Preview */}
            <AnimatePresence>
              {attachedFiles.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 10, scale: 0.95 }}
                  className="flex flex-wrap gap-2 pb-2"
                >
                  {attachedFiles.map((file) => (
                    <div
                      key={file.id}
                      className="group flex items-center gap-2.5 pl-2 pr-1.5 py-1.5 bg-white dark:bg-zinc-800 rounded-xl border border-zinc-200 dark:border-zinc-700 shadow-sm"
                    >
                      <div className="p-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                        {file.type === 'image' ? (
                          <ImageIcon className="w-3.5 h-3.5 text-indigo-500" />
                        ) : (
                          <FileText className="w-3.5 h-3.5 text-blue-500" />
                        )}
                      </div>
                      <span className="text-[11px] font-bold text-zinc-700 dark:text-zinc-300 max-w-[120px] truncate">
                        {file.file.name}
                      </span>
                      <button
                        onClick={() => removeFile(file.id)}
                        className="p-1 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded-lg transition-colors group"
                      >
                        <XIcon className="w-3.5 h-3.5 text-zinc-400 group-hover:text-rose-500" />
                      </button>
                    </div>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex items-end gap-3 bg-white dark:bg-zinc-800 p-2 rounded-[24px] shadow-sm border border-zinc-200 dark:border-zinc-700 focus-within:border-indigo-400 dark:focus-within:border-indigo-500 transition-all focus-within:shadow-lg focus-within:shadow-indigo-500/5">
              {/* File upload button */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.pdf,.doc,.docx,.pptx,.xls,.xlsx,.txt,.md,.markdown,.html,.htm,.csv"
                onChange={handleFileSelect}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isStreaming}
                className="p-3 hover:bg-zinc-100 dark:hover:bg-zinc-700 rounded-2xl transition-all text-zinc-500 dark:text-zinc-400 disabled:opacity-30 active:scale-90"
              >
                <Paperclip className="w-5 h-5" />
              </button>

              {/* Text input */}
              <textarea
                ref={inputRef}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isStreaming
                    ? t('agent.thinking')
                    : isTranscribingVoice
                      ? t('agent.voiceInputProcessing')
                      : t('agent.messagePlaceholder')
                }
                disabled={isStreaming}
                rows={1}
                className="flex-1 py-3 px-1 bg-transparent border-none focus:ring-0 text-sm font-medium text-zinc-900 dark:text-zinc-100 resize-none min-h-[44px] max-h-32 custom-scrollbar placeholder:text-zinc-400"
              />

              {/* Action Buttons */}
              <div className="flex items-center gap-2 pl-2 border-l border-zinc-100 dark:border-zinc-700">
                <button
                  onClick={() => {
                    void handleVoiceInput();
                  }}
                  disabled={isStreaming || isTranscribingVoice}
                  title={isRecordingVoice ? t('agent.voiceInputStop') : t('agent.voiceInputStart')}
                  className={`p-3 rounded-2xl transition-all disabled:opacity-30 active:scale-90 ${
                    isRecordingVoice
                      ? 'bg-rose-50 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400'
                      : 'hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-500 dark:text-zinc-400'
                  }`}
                >
                  {isTranscribingVoice ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : isRecordingVoice ? (
                    <Square className="w-5 h-5 fill-current" />
                  ) : (
                    <Mic className="w-5 h-5" />
                  )}
                </button>

                {isStreaming ? (
                  <button
                    onClick={handleAbortStreaming}
                    className="p-3 bg-rose-500 hover:bg-rose-600 text-white rounded-2xl transition-all shadow-lg shadow-rose-500/20 active:scale-90"
                  >
                    <XIcon className="w-5 h-5" />
                  </button>
                ) : (
                  <button
                    onClick={handleSendMessage}
                    disabled={
                      (!inputMessage.trim() && attachedFiles.length === 0) ||
                      isRecordingVoice ||
                      isTranscribingVoice
                    }
                    className="p-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-30 disabled:shadow-none active:scale-90"
                  >
                    <Send className="w-5 h-5" />
                  </button>
                )}
              </div>
            </div>

            <div className="flex items-center justify-center gap-6 text-[10px] font-bold text-zinc-400 dark:text-zinc-500 uppercase tracking-widest">
              <div className="flex items-center gap-1.5">
                <Zap className="w-3 h-3 text-amber-500" />
                <span>Enter to Send</span>
              </div>
              <div className="flex items-center gap-1.5">
                <History className="w-3 h-3 text-indigo-500" />
                <span>Multi-turn History</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Cpu className="w-3 h-3 text-emerald-500" />
                <span>Live Workspace</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </LayoutModal>
  );
};
