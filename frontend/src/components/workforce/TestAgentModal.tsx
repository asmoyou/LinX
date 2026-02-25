import React, { useState, useRef, useEffect, useMemo } from 'react';
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
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Agent } from '@/types/agent';
import { agentsApi } from '@/api';
import type {
  ConversationRound,
  StatusMessage,
  RetryAttempt,
  ErrorFeedback,
  AttachedFile,
} from '@/types/streaming';
import { ConversationRoundComponent } from './ConversationRound';
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
}

export const TestAgentModal: React.FC<TestAgentModalProps> = ({ agent, isOpen, onClose }) => {
  const { t } = useTranslation();
  const createEmptyRoundData = () => ({
    thinking: '',
    content: '',
    statusMessages: [] as StatusMessage[],
    retryAttempts: [] as RetryAttempt[],
    errorFeedback: [] as ErrorFeedback[],
    stats: null as ConversationRound['stats'] | null,
  });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Current streaming state - tracks the current round being built
  const [currentRounds, setCurrentRounds] = useState<ConversationRound[]>([]);
  const [currentRoundData, setCurrentRoundData] = useState(createEmptyRoundData());

  const [currentRoundNumber, setCurrentRoundNumber] = useState(1);

  // Session state for persistent execution environment
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showWorkspacePanel, setShowWorkspacePanel] = useState(false);
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastStatusTimeRef = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

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

  const hasRoundActivity = (round: {
    thinking: string;
    content: string;
    statusMessages: StatusMessage[];
    retryAttempts: RetryAttempt[];
    errorFeedback: ErrorFeedback[];
  }): boolean =>
    Boolean(
      round.thinking ||
        round.content ||
        round.statusMessages.length > 0 ||
        round.retryAttempts.length > 0 ||
        round.errorFeedback.length > 0
    );

  const buildRoundSnapshot = (
    roundData: ReturnType<typeof createEmptyRoundData>,
    roundNumber: number
  ): ConversationRound => ({
    roundNumber,
    thinking: roundData.thinking,
    content: roundData.content,
    statusMessages: roundData.statusMessages,
    retryAttempts: roundData.retryAttempts.length > 0 ? roundData.retryAttempts : undefined,
    errorFeedback: roundData.errorFeedback.length > 0 ? roundData.errorFeedback : undefined,
    stats: roundData.stats || undefined,
  });

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

    const newMessage: Message = {
      role: 'assistant',
      content: assistantContent,
      timestamp: new Date(),
      rounds: finalizedRounds,
    };

    setMessages((prev) => [...prev, newMessage]);
  };

  const resetStreamingState = () => {
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

  const extractTargetItemCount = (prompt: string): number | null => {
    const strictMatches = [
      ...prompt.matchAll(
        /(\d{2,5})\s*(?:道|题|个|条|questions?|question|items?|item|problems?|problem)\b/gi
      ),
    ];
    let matches = strictMatches;
    if (!matches.length) {
      const hasActionIntent = /(出|生成|给我|制作|写|整理|generate|create|produce|write|list)/i.test(
        prompt
      );
      const hasQuestionIntent = /(题|题目|问题|question|questions|quiz|exercise|exercises|problem|problems)/i.test(
        prompt
      );
      if (hasActionIntent && hasQuestionIntent) {
        matches = [...prompt.matchAll(/\b(\d{2,5})\b/g)];
      }
    }
    if (!matches.length) return null;

    let maxCandidate = 0;
    for (const match of matches) {
      const value = Number(match[1]);
      if (Number.isFinite(value) && value > maxCandidate) {
        maxCandidate = value;
      }
    }

    if (maxCandidate < 120 || maxCandidate > 10000) {
      return null;
    }
    return maxCandidate;
  };

  const buildSegmentedOutputOptions = (
    prompt: string
  ): {
    enabled: boolean;
    targetItems?: number;
    segmentItemLimit?: number;
    maxOutputSegments?: number;
  } => {
    const targetItems = extractTargetItemCount(prompt);
    const hasQuestionIntent = /(题|题目|问题|question|questions|quiz|exercise|exercises)/i.test(
      prompt
    );

    if (!targetItems || !hasQuestionIntent) {
      return { enabled: false };
    }

    const segmentItemLimit = Math.min(80, targetItems);
    const maxOutputSegments = Math.max(1, Math.ceil(targetItems / segmentItemLimit));
    return {
      enabled: true,
      targetItems,
      segmentItemLimit,
      maxOutputSegments: Math.min(maxOutputSegments, 20),
    };
  };

  // Memoize markdown components to prevent re-creation on each render
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentRounds, currentRoundData]);

  // Focus input when modal opens
  /* eslint-disable react-hooks/set-state-in-effect */
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
      setMessages([]);
      setInputMessage('');
      setAttachedFiles([]);
      setCurrentRounds([]);
      setCurrentRoundData(createEmptyRoundData());
      setCurrentRoundNumber(1);
      setSessionId(null);
      setShowWorkspacePanel(false);
      sessionIdRef.current = null;
      agentIdRef.current = null;
      setError(null);
      setIsStreaming(false);
      setIsFullscreen(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!sessionId) {
      setShowWorkspacePanel(false);
    }
  }, [sessionId]);
  /* eslint-enable react-hooks/set-state-in-effect */

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

  const handleClearChat = () => {
    if (isStreaming) return;
    setMessages([
      {
        role: 'system',
        content: `${t('agent.testConversation')} - ${agent?.name}`,
        timestamp: new Date(),
      },
    ]);
    setError(null);
  };

  const handleSendMessage = async () => {
    if ((!inputMessage.trim() && attachedFiles.length === 0) || isStreaming) return;

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

    // Build conversation history (exclude system messages)
    const history = messages
      .filter(
        (m) => m.role !== 'system' && typeof m.content === 'string' && m.content.trim().length > 0
      )
      .map((m) => ({ role: m.role, content: m.content.trim() }));

    try {
      const filesToUpload = attachedFiles.map((af) => af.file);
      const segmentedOutput = buildSegmentedOutputOptions(userMessage.content);

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
                setCurrentRounds([...streamingDataRef.current.rounds]);
              }

              streamingDataRef.current.currentRoundNumber = newRoundNumber;
              streamingDataRef.current.currentRound = createEmptyRoundData();
              setCurrentRoundNumber(newRoundNumber);
              setCurrentRoundData({ ...streamingDataRef.current.currentRound });
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
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
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
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
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
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
          } else if (
            chunk.type === 'start' ||
            chunk.type === 'tool_call' ||
            chunk.type === 'tool_result' ||
            chunk.type === 'tool_error' ||
            chunk.type === 'done'
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
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
            lastStatusTimeRef.current = now;
          } else if (chunk.type === 'thinking') {
            streamingDataRef.current.currentRound.thinking += chunk.content;
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
          } else if (chunk.type === 'content') {
            streamingDataRef.current.currentRound.content += chunk.content;
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
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
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
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
              setCurrentRoundData({ ...streamingDataRef.current.currentRound });
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
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
            lastStatusTimeRef.current = now;
            setError(chunk.content);
          }
        },
        (error) => {
          setError(error);
          commitStreamingOutputToMessages();
          resetStreamingState();
        },
        () => {
          commitStreamingOutputToMessages();
          resetStreamingState();
        },
        history,
        filesToUpload.length > 0 ? filesToUpload : undefined,
        abortControllerRef.current?.signal,
        sessionId || undefined,
        segmentedOutput
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
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

      commitStreamingOutputToMessages();
      resetStreamingState();
      setError(null);
    }
  };

  return (
    <LayoutModal isOpen={isOpen} onClose={onClose} closeOnBackdropClick={false} closeOnEscape={true}>
      <div
        className={`w-full transition-all duration-500 ease-in-out my-auto flex flex-col modal-panel rounded-[32px] shadow-2xl overflow-hidden bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 ${
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

        <div className="flex-1 min-h-0 flex bg-white dark:bg-zinc-950">
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-6 py-8 space-y-8 custom-scrollbar">
            <AnimatePresence mode="popLayout">
              {messages.map((message, index) => (
                <motion.div
                  key={`${message.timestamp.getTime()}-${index}`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                >
                  {message.role === 'user' ? (
                    <div className="flex justify-end group">
                      <div className="max-w-[80%] space-y-2">
                        <div className="relative">
                          <div className="rounded-[24px] rounded-tr-none px-5 py-3.5 bg-indigo-600 dark:bg-indigo-500 text-white shadow-xl shadow-indigo-500/10">
                            <p className="text-sm font-medium whitespace-pre-wrap leading-relaxed">
                              {message.content}
                            </p>

                            {/* Attachments */}
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
                                      <p className="text-[11px] font-bold truncate">
                                        {attachment.file.name}
                                      </p>
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
                          {/* Triangle tail */}
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
                  ) : message.role === 'system' ? (
                    <div className="flex justify-center">
                      <div className="px-5 py-2 bg-zinc-100 dark:bg-zinc-900/50 rounded-full border border-zinc-200/50 dark:border-zinc-800/50">
                        <p className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-500">
                          {message.content}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="flex justify-start">
                      <div className="max-w-[90%] space-y-4">
                        {message.rounds && message.rounds.length > 0 ? (
                          <div className="space-y-6">
                            {message.rounds.map((round, roundIdx) => (
                              <ConversationRoundComponent
                                key={`${message.timestamp.getTime()}-${round.roundNumber}-${roundIdx}`}
                                round={round}
                                isLatest={roundIdx === message.rounds!.length - 1}
                                defaultCollapsed={
                                  roundIdx < message.rounds!.length - 1 ||
                                  Boolean(round.content && round.content.trim().length > 0)
                                }
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
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={markdownComponents}
                              >
                                {message.content}
                              </ReactMarkdown>
                            </div>
                            <div className="mt-4 pt-4 border-t border-zinc-200/60 dark:border-zinc-800 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Bot className="w-3.5 h-3.5 text-indigo-500" />
                                <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-600 uppercase tracking-widest">
                                  {agent.name}
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
                  )}
                </motion.div>
              ))}
            </AnimatePresence>

            {/* Current streaming rounds */}
            {isStreaming && (currentRounds.length > 0 || hasRoundActivity(currentRoundData)) && (
              <div className="flex justify-start">
                <div className="max-w-[90%] space-y-6">
                  {currentRounds.map((round, idx) => (
                    <ConversationRoundComponent
                      key={`stream-round-${round.roundNumber}-${idx}`}
                      round={round}
                      isLatest={false}
                      defaultCollapsed={true}
                    />
                  ))}

                  <ConversationRoundComponent
                    round={{
                      roundNumber: currentRoundNumber,
                      thinking: currentRoundData.thinking,
                      content: currentRoundData.content,
                      statusMessages: currentRoundData.statusMessages,
                      retryAttempts:
                        currentRoundData.retryAttempts.length > 0
                          ? currentRoundData.retryAttempts
                          : undefined,
                      errorFeedback:
                        currentRoundData.errorFeedback.length > 0
                          ? currentRoundData.errorFeedback
                          : undefined,
                      stats: currentRoundData.stats || undefined,
                    }}
                    isLatest={true}
                    isStreaming={true}
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

            <div ref={messagesEndRef} />
          </div>

          {/* Workspace Panel Container */}
          <AnimatePresence>
            {showWorkspacePanel && (
              <motion.div
                initial={{ opacity: 0, x: 300, width: 0 }}
                animate={{ opacity: 1, x: 0, width: 400 }}
                exit={{ opacity: 0, x: 300, width: 0 }}
                transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                className="border-l border-zinc-100 dark:border-zinc-800"
              >
                <SessionWorkspacePanel
                  agentId={agent.id}
                  sessionId={sessionId}
                  isOpen={showWorkspacePanel}
                  onClose={() => setShowWorkspacePanel(false)}
                />
              </motion.div>
            )}
          </AnimatePresence>
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
                  isStreaming ? t('agent.thinking') : t('agent.messagePlaceholder')
                }
                disabled={isStreaming}
                rows={1}
                className="flex-1 py-3 px-1 bg-transparent border-none focus:ring-0 text-sm font-medium text-zinc-900 dark:text-zinc-100 resize-none min-h-[44px] max-h-32 custom-scrollbar placeholder:text-zinc-400"
              />

              {/* Action Buttons */}
              <div className="flex items-center gap-2 pl-2 border-l border-zinc-100 dark:border-zinc-700">
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
                    disabled={!inputMessage.trim() && attachedFiles.length === 0}
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
