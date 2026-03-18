import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Bot,
  FolderOpen,
  Image as ImageIcon,
  Loader2,
  MessageSquarePlus,
  Paperclip,
  Pencil,
  Send,
  Trash2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';

import { agentsApi } from '@/api';
import { ConversationRoundComponent, type ConversationRoundArtifact } from '@/components/workforce/ConversationRound';
import { createMarkdownComponents } from '@/components/workforce/CodeBlock';
import { SessionWorkspacePanel } from '@/components/workforce/SessionWorkspacePanel';
import type {
  Agent,
  AgentConversationDetail,
  AgentConversationHistorySummary,
  AgentConversationSummary,
  ConversationMessage,
} from '@/types/agent';
import type {
  AttachedFile,
  ConversationRound,
  ErrorFeedback,
  RetryAttempt,
  StatusMessage,
} from '@/types/streaming';

const WORKSPACE_PATH_PATTERN = /\/workspace\/[^\s,)\]}>"'`]+/gi;
const FILE_PATH_KV_PATTERN = /file_path=([^\s,)\]}>"'`]+)/gi;
const FILE_ACTION_PATH_PATTERN = /(?:wrote|appended to|edited)\s+([^\s,)\]}>"'`]+)/gi;
const RELATIVE_FILE_PATH_PATTERN =
  /(?:^|[\s"'`(（【])((?:\.\/)?[^\s"'`<>(){}[\]]+\.(?:md|markdown|txt|json|csv|ya?ml|pdf|docx?|xlsx?|pptx?|html?))(?=$|[\s"'`)\]}>，。；;!?])/gi;

interface StreamingRoundState {
  thinking: string;
  content: string;
  statusMessages: StatusMessage[];
  retryAttempts: RetryAttempt[];
  errorFeedback: ErrorFeedback[];
  stats: ConversationRound['stats'] | null;
}

function createEmptyRoundData(): StreamingRoundState {
  return {
    thinking: '',
    content: '',
    statusMessages: [],
    retryAttempts: [],
    errorFeedback: [],
    stats: null,
  };
}

function buildRoundSnapshot(roundData: StreamingRoundState, roundNumber: number): ConversationRound {
  return {
    roundNumber,
    thinking: roundData.thinking,
    content: roundData.content,
    statusMessages: [...roundData.statusMessages],
    retryAttempts: roundData.retryAttempts.length > 0 ? [...roundData.retryAttempts] : undefined,
    errorFeedback: roundData.errorFeedback.length > 0 ? [...roundData.errorFeedback] : undefined,
    stats: roundData.stats ? { ...roundData.stats } : undefined,
  };
}

function hasRoundActivity(round: StreamingRoundState): boolean {
  return Boolean(
    round.thinking ||
      round.content.trim() ||
      round.statusMessages.length > 0 ||
      round.retryAttempts.length > 0 ||
      round.errorFeedback.length > 0
  );
}

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
    if (!normalized || normalized.startsWith('/workspace/input/')) {
      return;
    }
    unique.add(normalized);
  });

  return [...unique];
}

function extractRoundArtifacts(round: ConversationRound): ConversationRoundArtifact[] {
  const explicitArtifacts = Array.isArray((round as any).artifacts) ? (round as any).artifacts : [];
  const explicitPaths = explicitArtifacts
    .map((item: any) => normalizeWorkspaceFilePath(item?.path || ''))
    .filter(Boolean);
  const inferredPaths = extractWorkspacePathsFromText(round.content || '');
  return [...new Set([...explicitPaths, ...inferredPaths])]
    .sort((a, b) => a.localeCompare(b))
    .map((path) => ({ path, confirmed: true }));
}

function buildAttachmentPreview(file: File): AttachedFile {
  const type: AttachedFile['type'] = file.type.startsWith('image/')
    ? 'image'
    : file.type.includes('pdf') || file.type.includes('text') || file.type.includes('json')
      ? 'document'
      : 'other';
  return {
    id: `${file.name}-${file.size}-${file.lastModified}`,
    file,
    preview: type === 'image' ? URL.createObjectURL(file) : undefined,
    type,
  };
}

function normalizeStoredRound(rawRound: any, index: number): ConversationRound {
  const statusMessages = Array.isArray(rawRound?.statusMessages)
    ? rawRound.statusMessages.map((item: any) => ({
        content: String(item?.content || ''),
        type: (item?.type || 'info') as StatusMessage['type'],
        timestamp: new Date(item?.timestamp || Date.now()),
        duration: typeof item?.duration === 'number' ? item.duration : undefined,
      }))
    : [];

  const retryAttempts = Array.isArray(rawRound?.retryAttempts)
    ? rawRound.retryAttempts.map((item: any, retryIndex: number) => ({
        retryCount: Number(item?.retryCount || item?.retry_count || retryIndex + 1 || 1),
        maxRetries: Number(item?.maxRetries || item?.max_retries || 1),
        errorType: (item?.errorType || item?.error_type || 'parse_error') as RetryAttempt['errorType'],
        message: String(item?.message || ''),
        timestamp: new Date(item?.timestamp || Date.now()),
      }))
    : undefined;

  const errorFeedback = Array.isArray(rawRound?.errorFeedback)
    ? rawRound.errorFeedback.map((item: any) => ({
        errorType: String(item?.errorType || item?.error_type || 'unknown'),
        retryCount: Number(item?.retryCount || item?.retry_count || 1),
        maxRetries: Number(item?.maxRetries || item?.max_retries || 1),
        message: String(item?.message || ''),
        suggestions: Array.isArray(item?.suggestions) ? item.suggestions.map(String) : undefined,
        timestamp: new Date(item?.timestamp || Date.now()),
      }))
    : undefined;

  return {
    roundNumber: Number(rawRound?.roundNumber || index + 1),
    thinking: String(rawRound?.thinking || ''),
    content: String(rawRound?.content || ''),
    statusMessages,
    retryAttempts,
    errorFeedback,
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

export const AgentConversation: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { agentId = '', conversationId = '' } = useParams();
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);
  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const attachedFilesRef = useRef<AttachedFile[]>([]);
  const activeConversationRef = useRef<{ agentId?: string; conversationId?: string }>({});

  const [agent, setAgent] = useState<Agent | null>(null);
  const [conversations, setConversations] = useState<AgentConversationSummary[]>([]);
  const [conversation, setConversation] = useState<AgentConversationDetail | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [historySummary, setHistorySummary] = useState<AgentConversationHistorySummary | null>(null);
  const [inputMessage, setInputMessage] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWorkspacePanel, setShowWorkspacePanel] = useState(false);
  const [workspaceFocusPath, setWorkspaceFocusPath] = useState<string | null>(null);
  const [downloadingArtifactPath, setDownloadingArtifactPath] = useState<string | null>(null);
  const [currentRounds, setCurrentRounds] = useState<ConversationRound[]>([]);
  const [currentRoundData, setCurrentRoundData] = useState<StreamingRoundState>(createEmptyRoundData());
  const [currentRoundNumber, setCurrentRoundNumber] = useState(1);
  const [draftConversationId, setDraftConversationId] = useState<string | null>(null);
  const [, setIsCreatingConversation] = useState(false);
  const [pendingConversationTitle, setPendingConversationTitle] = useState<string | null>(null);
  const [showDraftPlaceholder, setShowDraftPlaceholder] = useState(false);
  const [deletingConversationIds, setDeletingConversationIds] = useState<Set<string>>(new Set());

  const activeConversationId = conversationId || draftConversationId || '';

  const loadConversationData = useCallback(async () => {
    if (!agentId) {
      return;
    }

    setIsLoading(true);
    try {
      const [agentData, listData, detailData, messagesData] = await Promise.all([
        agentsApi.getById(agentId),
        agentsApi.getConversations(agentId),
        conversationId ? agentsApi.getConversation(agentId, conversationId) : Promise.resolve(null),
        conversationId
          ? agentsApi.getConversationMessages(agentId, conversationId)
          : Promise.resolve(null),
      ]);
      setAgent(agentData);
      setConversations(listData.items);
      setConversation(detailData);
      setMessages(messagesData?.items || []);
      setHistorySummary(messagesData?.historySummary || null);
      setPendingConversationTitle(detailData?.title || null);
      setError(null);
    } catch (loadError) {
      console.error('Failed to load conversation data:', loadError);
      const message = loadError instanceof Error ? loadError.message : 'Failed to load conversation';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [agentId, conversationId]);

  useEffect(() => {
    void loadConversationData();
  }, [loadConversationData]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentRounds, currentRoundData, showWorkspacePanel]);

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
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [inputMessage]);

  useEffect(() => {
    const releaseRuntime = () => {
      const currentAgentId = activeConversationRef.current.agentId;
      const currentConversationId = activeConversationRef.current.conversationId;
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
      if (document.visibilityState === 'hidden') {
        releaseRuntime();
      }
    };

    window.addEventListener('pagehide', handlePageHide);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('pagehide', handlePageHide);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
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

  const resetStreamingState = useCallback(() => {
    setCurrentRounds([]);
    setCurrentRoundData(createEmptyRoundData());
    setCurrentRoundNumber(1);
    abortControllerRef.current = null;
  }, []);

  const handleRefreshConversation = useCallback(async () => {
    await loadConversationData();
  }, [loadConversationData]);

  const replaceConversationUrl = useCallback(
    (nextConversationId: string) => {
      if (!agentId || !nextConversationId) return;
      window.history.replaceState(
        window.history.state,
        '',
        `/workforce/${agentId}/conversations/${nextConversationId}`
      );
    },
    [agentId]
  );

  const upsertConversationItem = useCallback((nextItem: AgentConversationSummary) => {
    setConversations((prev) => {
      const deduped = prev.filter((item) => item.id !== nextItem.id);
      return [nextItem, ...deduped];
    });
  }, []);

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
          setMessages(messagesData.items);
          setHistorySummary(messagesData.historySummary || null);
        }
      } catch (syncError) {
        console.error('Failed to sync conversation state:', syncError);
      }
    },
    [agentId]
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
    setInputMessage('');
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
      const nextTitle = window.prompt(t('agent.renameConversation', 'Rename conversation'), item.title);
      if (!nextTitle || nextTitle.trim() === item.title) {
        return;
      }
      try {
        await agentsApi.updateConversation(agentId, item.id, nextTitle.trim());
        await loadConversationData();
      } catch (renameError) {
        console.error('Failed to rename conversation:', renameError);
        toast.error(t('agent.renameConversationFailed', 'Failed to rename conversation'));
      }
    },
    [agentId, loadConversationData, t]
  );

  const handleDeleteConversation = useCallback(
    async (item: AgentConversationSummary) => {
      if (deletingConversationIds.has(item.id)) {
        return;
      }
      if (!window.confirm(t('agent.deleteConversationConfirm', 'Delete this conversation?'))) {
        return;
      }
      setDeletingConversationIds((prev) => {
        const next = new Set(prev);
        next.add(item.id);
        return next;
      });
      try {
        await agentsApi.deleteConversation(agentId, item.id);
        const remainingConversations = conversations.filter((conversationItem) => conversationItem.id !== item.id);
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
            navigate(`/workforce/${agentId}/conversations/${remainingConversations[0].id}`);
          } else {
            navigate(`/workforce/${agentId}/conversations`);
          }
        }
      } catch (deleteError) {
        console.error('Failed to delete conversation:', deleteError);
        toast.error(t('agent.deleteConversationFailed', 'Failed to delete conversation'));
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
    ]
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
          normalizedPath
        );
        const fileName = normalizedPath.split('/').filter(Boolean).pop() || 'artifact';
        downloadBlob(blob, fileName);
      } catch (downloadError) {
        const message = downloadError instanceof Error ? downloadError.message : 'Failed to download file';
        toast.error(message);
      } finally {
        setDownloadingArtifactPath(null);
      }
    },
    [activeConversationId, agentId]
  );

  const handleOpenArtifactInWorkspace = useCallback((path: string) => {
    const normalizedPath = normalizeWorkspaceFilePath(path);
    if (!normalizedPath) return;
    setWorkspaceFocusPath(normalizedPath);
    setShowWorkspacePanel(true);
  }, []);

  const handleFilesSelected = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files || []);
    if (nextFiles.length === 0) return;

    setAttachedFiles((prev) => [...prev, ...nextFiles.map(buildAttachmentPreview)]);
    event.target.value = '';
  }, []);

  const removeAttachedFile = useCallback((fileId: string) => {
    setAttachedFiles((prev) => {
      const target = prev.find((item) => item.id === fileId);
      if (target?.preview) {
        URL.revokeObjectURL(target.preview);
      }
      return prev.filter((item) => item.id !== fileId);
    });
  }, []);

  const handleSendMessage = useCallback(async () => {
    if (!agentId || isSending) {
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
        console.error('Failed to create conversation:', createError);
        setIsCreatingConversation(false);
        setShowDraftPlaceholder(false);
        toast.error(t('agent.startConversationFailed', 'Failed to start conversation'));
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
      role: 'user',
      contentText: text || '[Attached files]',
      contentJson: null,
      attachments: optimisticAttachments,
      source: 'web',
      createdAt: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimisticMessage]);
    setInputMessage('');
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

    const roundStateRef = {
      current: {
        rounds: [] as ConversationRound[],
        currentRound: createEmptyRoundData(),
        currentRoundNumber: 1,
      },
    };
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    let hasCommittedStreamingOutput = false;

    const finalizeStreamingOutput = () => {
      const completedRounds = [...roundStateRef.current.rounds];
      if (hasRoundActivity(roundStateRef.current.currentRound)) {
        completedRounds.push(
          buildRoundSnapshot(
            roundStateRef.current.currentRound,
            roundStateRef.current.currentRoundNumber
          )
        );
      }

      const assistantContent = completedRounds
        .map((round) => round.content.trim())
        .filter(Boolean)
        .join('\n\n')
        .trim();
      const latestStats =
        completedRounds.length > 0
          ? completedRounds[completedRounds.length - 1].stats
          : undefined;

      return {
        completedRounds,
        assistantContent,
        latestStats: latestStats || null,
      };
    };

    const commitStreamingOutputToMessages = () => {
      if (hasCommittedStreamingOutput) {
        return finalizeStreamingOutput();
      }
      hasCommittedStreamingOutput = true;
      const { completedRounds, assistantContent, latestStats } = finalizeStreamingOutput();

      if (!assistantContent && completedRounds.length === 0) {
        return { completedRounds, assistantContent, latestStats };
      }

      const assistantMessage: ConversationMessage = {
        id: `temp-assistant-${Date.now()}`,
        conversationId: targetConversationId,
        role: 'assistant',
        contentText: assistantContent,
        contentJson: {
          rounds: completedRounds,
          stats: latestStats,
          artifacts: [],
        },
        attachments: [],
        source: 'web',
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
      return { completedRounds, assistantContent, latestStats };
    };

    try {
      await agentsApi.sendConversationMessage(
        agentId,
        targetConversationId,
        text || '[Attached files]',
        (chunk) => {
          if (chunk.type === 'runtime') {
            const statusContent = chunk.restored_from_snapshot
              ? t('agent.runtimeRestored', 'Runtime restored from the latest snapshot.')
              : t('agent.runtimeFresh', 'Runtime started for this conversation.');
            roundStateRef.current.currentRound.statusMessages.push({
              content: statusContent,
              type: 'start',
              timestamp: new Date(),
            });
            setCurrentRoundData({ ...roundStateRef.current.currentRound });
            return;
          }
          if (chunk.type === 'conversation_title') {
            const nextTitle = String(chunk.title || '').trim();
            if (nextTitle) {
              setPendingConversationTitle(nextTitle);
              setShowDraftPlaceholder(false);
              setConversation((prev) =>
                prev
                  ? { ...prev, title: nextTitle }
                  : ({
                      id: String(chunk.conversation_id || targetConversationId),
                      agentId,
                      ownerUserId: '',
                      title: nextTitle,
                      status: 'active',
                      source: 'web',
                      latestSnapshotId: null,
                      latestSnapshotStatus: null,
                      lastMessageAt: new Date().toISOString(),
                      lastMessagePreview: text || '[Attached files]',
                      createdAt: new Date().toISOString(),
                      updatedAt: new Date().toISOString(),
                      latestSnapshotGeneration: null,
                    } as AgentConversationDetail)
              );
              upsertConversationItem({
                id: String(chunk.conversation_id || targetConversationId),
                agentId,
                ownerUserId: '',
                title: nextTitle,
                status: 'active',
                source: 'web',
                latestSnapshotId: null,
                latestSnapshotStatus: 'ready',
                lastMessageAt: new Date().toISOString(),
                lastMessagePreview: text || '[Attached files]',
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              });
            }
            return;
          }

          if (chunk.type === 'info') {
            const roundMatch = String(chunk.content || '').match(/第\s*(\d+)\s*轮/);
            if (roundMatch) {
              const nextRoundNumber = parseInt(roundMatch[1], 10);
              if (hasRoundActivity(roundStateRef.current.currentRound)) {
                roundStateRef.current.rounds.push(
                  buildRoundSnapshot(
                    roundStateRef.current.currentRound,
                    roundStateRef.current.currentRoundNumber
                  )
                );
              }
              roundStateRef.current.currentRoundNumber = nextRoundNumber;
              roundStateRef.current.currentRound = createEmptyRoundData();
            }
            roundStateRef.current.currentRound.statusMessages.push({
              content: String(chunk.content || ''),
              type: 'info',
              timestamp: new Date(),
            });
          } else if (
            chunk.type === 'start' ||
            chunk.type === 'tool_call' ||
            chunk.type === 'tool_result' ||
            chunk.type === 'tool_error' ||
            chunk.type === 'done' ||
            chunk.type === 'error'
          ) {
            roundStateRef.current.currentRound.statusMessages.push({
              content: String(chunk.content || ''),
              type: chunk.type as StatusMessage['type'],
              timestamp: new Date(),
            });
            if (chunk.type === 'done') {
              commitStreamingOutputToMessages();
              resetStreamingState();
              setIsCreatingConversation(false);
              setShowDraftPlaceholder(false);
              return;
            }
          } else if (chunk.type === 'thinking') {
            roundStateRef.current.currentRound.thinking += String(chunk.content || '');
          } else if (chunk.type === 'content') {
            roundStateRef.current.currentRound.content += String(chunk.content || '');
          } else if (chunk.type === 'retry_attempt') {
            roundStateRef.current.currentRound.retryAttempts.push({
              retryCount: Number(chunk.retry_count || 1),
              maxRetries: Number(chunk.max_retries || 1),
              errorType: (chunk.error_type || 'parse_error') as RetryAttempt['errorType'],
              message: String(chunk.content || ''),
              timestamp: new Date(),
            });
          } else if (chunk.type === 'error_feedback') {
            roundStateRef.current.currentRound.errorFeedback.push({
              errorType: String(chunk.error_type || 'unknown'),
              retryCount: Number(chunk.retry_count || 1),
              maxRetries: Number(chunk.max_retries || 1),
              message: String(chunk.content || ''),
              suggestions: Array.isArray(chunk.suggestions) ? chunk.suggestions.map(String) : undefined,
              timestamp: new Date(),
            });
          } else if (chunk.type === 'round_stats') {
            roundStateRef.current.currentRound.stats = {
              timeToFirstToken: Number(chunk.timeToFirstToken || 0),
              tokensPerSecond: Number(chunk.tokensPerSecond || 0),
              inputTokens: Number(chunk.inputTokens || 0),
              outputTokens: Number(chunk.outputTokens || 0),
              totalTokens: Number(chunk.inputTokens || 0) + Number(chunk.outputTokens || 0),
              totalTime: Number(chunk.totalTime || 0),
            };
          } else if (chunk.type === 'stats' && !roundStateRef.current.currentRound.stats) {
            roundStateRef.current.currentRound.stats = {
              timeToFirstToken: Number(chunk.timeToFirstToken || 0),
              tokensPerSecond: Number(chunk.tokensPerSecond || 0),
              inputTokens: Number(chunk.inputTokens || 0),
              outputTokens: Number(chunk.outputTokens || 0),
              totalTokens: Number(chunk.totalTokens || 0),
              totalTime: Number(chunk.totalTime || 0),
            };
          }

          setCurrentRounds([...roundStateRef.current.rounds]);
          setCurrentRoundData({ ...roundStateRef.current.currentRound });
          setCurrentRoundNumber(roundStateRef.current.currentRoundNumber);
        },
        (message) => {
          setError(message);
        },
        async () => {
          const { assistantContent } = commitStreamingOutputToMessages();
          upsertConversationItem({
            id: targetConversationId,
            agentId,
            ownerUserId: '',
            title:
              pendingConversationTitle ||
              conversation?.title ||
              t('agent.draftConversation', 'New conversation'),
            status: 'active',
            source: 'web',
            latestSnapshotId: null,
            latestSnapshotStatus: 'ready',
            lastMessageAt: new Date().toISOString(),
            lastMessagePreview: assistantContent || text || '[Attached files]',
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
                    t('agent.draftConversation', 'New conversation'),
                  latestSnapshotStatus: 'ready',
                }
              : prev
          );
          resetStreamingState();
          setIsCreatingConversation(false);
          setShowDraftPlaceholder(false);
          await syncConversationState(targetConversationId, false);
        },
        optimisticAttachments.map((item) => {
          const file = attachedFiles.find((attached) => attached.id === item.id);
          return file?.file;
        }).filter(Boolean) as File[],
        abortController.signal
      );
    } catch (sendError) {
      console.error('Failed to send conversation message:', sendError);
      setIsCreatingConversation(false);
      setShowDraftPlaceholder(false);
      await syncConversationState(targetConversationId);
    } finally {
      setIsSending(false);
      abortControllerRef.current = null;
    }
  }, [
    agentId,
    attachedFiles,
    conversationId,
    draftConversationId,
    inputMessage,
    isSending,
    pendingConversationTitle,
    replaceConversationUrl,
    resetStreamingState,
    syncConversationState,
    t,
    upsertConversationItem,
    conversation?.title,
  ]);

  const renderedMessages = useMemo(() => {
    return messages.map((message) => {
      const rawRounds = Array.isArray(message.contentJson?.rounds) ? message.contentJson.rounds : [];
      const storedRounds = rawRounds.map((rawRound: any, index: number) =>
        normalizeStoredRound(rawRound, index)
      );
      const artifactPaths = Array.isArray(message.contentJson?.artifacts)
        ? message.contentJson.artifacts
            .map((item: any) => normalizeWorkspaceFilePath(item?.path || ''))
            .filter(Boolean)
        : [];
      return {
        ...message,
        parsedRounds: storedRounds,
        artifactPaths,
      };
    });
  }, [messages]);

  const currentStreamingRound = useMemo(() => {
    if (!hasRoundActivity(currentRoundData)) {
      return null;
    }
    return buildRoundSnapshot(currentRoundData, currentRoundNumber);
  }, [currentRoundData, currentRoundNumber]);

  const showPendingConversationCard = showDraftPlaceholder;
  const hasVisibleConversationContent =
    renderedMessages.length > 0 || currentRounds.length > 0 || Boolean(currentStreamingRound);
  const showBlockingLoading = isLoading && !hasVisibleConversationContent;
  const conversationTitle =
    pendingConversationTitle ||
    conversation?.title ||
    (showPendingConversationCard
      ? t('agent.generatingConversationTitle', 'Generating title...')
      : !conversationId
        ? t('agent.draftConversation', 'New conversation')
        : t('agent.loadingConversation', 'Loading conversation...'));
  const conversationSubtitle = showPendingConversationCard
    ? t('agent.generatingConversationTitleHint', 'The title will appear after the first reply.')
    : !conversationId
      ? t('agent.draftConversationHint', 'Send the first message to create this conversation.')
      : conversation?.latestSnapshotStatus
        ? `${conversation.storageTier || 'hot'} • ${t('agent.snapshotStatus', 'Snapshot')}: ${conversation.latestSnapshotStatus}`
        : t('agent.snapshotPending', 'No snapshot yet');

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/workforce')}
            className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            <ArrowLeft className="w-4 h-4" />
            {t('common.back', 'Back')}
          </button>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {agent?.name || t('agent.conversationTitle', 'Agent Conversation')}
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
            {t('agent.workspace', 'Workspace')}
          </button>
          <button
            type="button"
            onClick={handleCreateConversation}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-600"
          >
            <MessageSquarePlus className="w-4 h-4" />
            {t('agent.newConversation', 'New conversation')}
          </button>
        </div>
      </div>

      <div className="grid min-h-0 grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="flex h-[calc(100vh-11rem)] min-h-[620px] min-w-0 flex-col overflow-hidden rounded-3xl border border-zinc-200 bg-white/90 p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-400">
              {t('agent.conversations', 'Conversations')}
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
                  {t('agent.generatingConversationTitle', 'Generating title...')}
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
                onClick={() => navigate(`/workforce/${agentId}/conversations/${item.id}`)}
                className={`w-full rounded-2xl border px-3 py-3 text-left transition-colors ${
                  item.id === activeConversationId
                    ? 'border-emerald-500 bg-emerald-500/10'
                    : 'border-zinc-200 bg-zinc-50 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950/60 dark:hover:bg-zinc-800/80'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      {item.title}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs text-zinc-500 dark:text-zinc-400">
                      {item.lastMessagePreview || t('agent.noMessagesYet', 'No messages yet')}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
                        {item.source}
                      </span>
                      {item.storageTier && item.storageTier !== 'hot' && (
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
                    {conversation?.storageTier && conversation.storageTier !== 'hot' && (
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
                  {t('common.refresh', 'Refresh')}
                </button>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
              {showBlockingLoading ? (
                <div className="flex h-full items-center justify-center gap-3 text-zinc-500 dark:text-zinc-400">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>{t('common.loading', 'Loading...')}</span>
                </div>
              ) : error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300">
                  {error}
                </div>
              ) : !hasVisibleConversationContent ? (
                <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
                    <Bot className="w-7 h-7" />
                  </div>
                  <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    {t('agent.draftConversation', 'New conversation')}
                  </h3>
                  <p className="mt-2 max-w-md text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
                    {t(
                      'agent.draftConversationHint',
                      'Send the first message to create and save this conversation.'
                    )}
                  </p>
                </div>
              ) : (
                <div className="space-y-6">
                  {historySummary &&
                    Number(conversation?.compactedMessageCount || 0) > 0 && (
                      <div className="rounded-[28px] border border-amber-200 bg-amber-50/80 px-5 py-4 dark:border-amber-900/40 dark:bg-amber-950/20">
                        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">
                          <Bot className="h-4 w-4" />
                          {t('agent.compactedHistory', 'Earlier messages were compacted')}
                        </div>
                        <p className="mt-2 text-xs leading-5 text-amber-800/90 dark:text-amber-200/90">
                          {t(
                            'agent.compactedHistoryHint',
                            '{{count}} earlier message(s) were summarized to keep this conversation lightweight.',
                            { count: conversation?.compactedMessageCount || 0 }
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
                  {renderedMessages.map((message) =>
                    message.role === 'user' ? (
                      <div key={message.id} className="flex justify-end">
                        <div className="max-w-[80%] rounded-[28px] rounded-tr-none bg-emerald-600 px-5 py-4 text-white shadow-lg shadow-emerald-500/10">
                          <p className="whitespace-pre-wrap text-sm leading-relaxed">
                            {message.contentText}
                          </p>
                          {message.attachments.length > 0 && (
                            <div className="mt-3 grid gap-2">
                              {message.attachments.map((attachment, index) => (
                                <div key={`${message.id}-attachment-${index}`} className="rounded-xl border border-white/15 bg-white/10 px-3 py-2">
                                  <p className="text-xs font-semibold">
                                    {String(attachment.name || attachment.file_name || 'Attachment')}
                                  </p>
                                  <p className="text-[11px] opacity-80">
                                    {String(attachment.type || attachment.content_type || '')}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div key={message.id} className="space-y-4">
                        {message.parsedRounds.length > 0 ? (
                          message.parsedRounds.map((round, index) => (
                            <ConversationRoundComponent
                              key={`${message.id}-round-${round.roundNumber}-${index}`}
                              round={round}
                              isLatest={index === message.parsedRounds.length - 1}
                              artifacts={[
                                ...extractRoundArtifacts(round),
                                ...((index === message.parsedRounds.length - 1
                                  ? message.artifactPaths
                                  : []) as string[]).map((path) => ({ path, confirmed: true })),
                              ].filter(
                                (artifact, artifactIndex, allArtifacts) =>
                                  allArtifacts.findIndex((candidate) => candidate.path === artifact.path) === artifactIndex
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
                              {agent?.name || 'Agent'}
                            </div>
                            <div className="markdown-content">
                              <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
                                {message.contentText}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  )}

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
                      artifacts={extractRoundArtifacts(currentStreamingRound)}
                      onOpenArtifact={handleOpenArtifactInWorkspace}
                      onDownloadArtifact={handleDownloadArtifact}
                      downloadingArtifactPath={downloadingArtifactPath}
                    />
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>

            <div className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
              {attachedFiles.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {attachedFiles.map((file) => (
                    <div key={file.id} className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs dark:border-zinc-800 dark:bg-zinc-950/50">
                      {file.type === 'image' ? <ImageIcon className="w-3.5 h-3.5" /> : <Paperclip className="w-3.5 h-3.5" />}
                      <span className="max-w-[180px] truncate">{file.file.name}</span>
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
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white text-zinc-600 transition-colors hover:bg-zinc-100 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={handleFilesSelected}
                />
                <textarea
                  ref={textareaRef}
                  value={inputMessage}
                  onChange={(event) => setInputMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      if (!isSending && (inputMessage.trim() || attachedFiles.length > 0)) {
                        void handleSendMessage();
                      }
                    }
                  }}
                  placeholder={t('agent.messagePlaceholder', 'Send a message to this agent')}
                  rows={1}
                  className="max-h-[180px] min-h-[24px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-zinc-900 outline-none placeholder:text-zinc-400 dark:text-white"
                />
                <button
                  type="button"
                  onClick={() => void handleSendMessage()}
                  disabled={isSending || (!inputMessage.trim() && attachedFiles.length === 0)}
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-emerald-500 text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-zinc-300 dark:disabled:bg-zinc-700"
                >
                  {isSending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
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
