import React, { useState, useRef, useEffect, useMemo } from 'react';
import { X, Send, Loader2, AlertCircle, Bot, ChevronDown, ChevronUp, Brain, Paperclip, Image as ImageIcon, FileText, X as XIcon, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Agent } from '@/types/agent';
import { agentsApi } from '@/api';
import type {
  ConversationRound,
  StatusMessage,
  RetryAttempt,
  ErrorFeedback,
  AttachedFile
} from '@/types/streaming';
import { ConversationRoundComponent } from './ConversationRound';
import { RetryIndicator } from './RetryIndicator';
import { ErrorFeedbackDisplay } from './ErrorFeedbackDisplay';
import { createMarkdownComponents } from './CodeBlock';

interface TestAgentModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
}

interface StatusMessage {
  content: string;
  type: 'start' | 'info' | 'thinking' | 'done' | 'error' | 'tool_call' | 'tool_result' | 'tool_error';
  timestamp: Date;
  duration?: number;  // 处理耗时（秒）
}

interface AttachedFile {
  id: string;
  file: File;
  preview?: string;
  type: 'image' | 'document' | 'other';
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  rounds?: ConversationRound[];  // Multi-round execution
  attachments?: AttachedFile[];
}

export const TestAgentModal: React.FC<TestAgentModalProps> = ({
  agent,
  isOpen,
  onClose,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Current streaming state - tracks the current round being built
  const [currentRounds, setCurrentRounds] = useState<ConversationRound[]>([]);
  const [currentRoundData, setCurrentRoundData] = useState<{
    thinking: string;
    content: string;
    statusMessages: StatusMessage[];
    retryAttempts: RetryAttempt[];
    errorFeedback: ErrorFeedback[];
    stats: ConversationRound['stats'] | null;
  }>({
    thinking: '',
    content: '',
    statusMessages: [],
    retryAttempts: [],
    errorFeedback: [],
    stats: null,
  });
  
  const [currentRoundNumber, setCurrentRoundNumber] = useState(1);

  // Session state for persistent execution environment
  const [sessionId, setSessionId] = useState<string | null>(null);
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
  const lastStatusTimeRef = useRef<number>(Date.now());
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Use refs to track streaming data for onComplete callback
  const streamingDataRef = useRef<{
    rounds: ConversationRound[];
    currentRound: typeof currentRoundData;
    currentRoundNumber: number;
  }>({
    rounds: [],
    currentRound: {
      thinking: '',
      content: '',
      statusMessages: [],
      retryAttempts: [],
      errorFeedback: [],
      stats: null,
    },
    currentRoundNumber: 1,
  });

  // Memoize markdown components to prevent re-creation on each render
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentRounds]);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      if (messages.length === 0) {
        setMessages([
          {
            role: 'system',
            content: `Testing ${agent?.name}`,
            timestamp: new Date(),
          },
        ]);
      }
    }
  }, [isOpen]);

  // Reset state when modal closes and clean up session
  useEffect(() => {
    if (!isOpen) {
      // End the session to clean up resources (best-effort)
      // Use refs to get the current values (avoids stale closure - agent may be null when closing)
      const currentSessionId = sessionIdRef.current;
      const currentAgentId = agentIdRef.current;

      if (currentSessionId && currentAgentId) {
        console.log(`Ending session: ${currentSessionId} for agent: ${currentAgentId}`);
        agentsApi.endSession(currentAgentId, currentSessionId).then(() => {
          console.log(`Session ended successfully: ${currentSessionId}`);
        }).catch((err) => {
          // Log but don't throw - session cleanup is best-effort
          console.warn(`Failed to end session ${currentSessionId}:`, err);
        });
      }

      // Reset all state
      setMessages([]);
      setInputMessage('');
      setAttachedFiles([]);
      setCurrentRounds([]);
      setCurrentRoundData({
        thinking: '',
        content: '',
        statusMessages: [],
        retryAttempts: [],
        errorFeedback: [],
        stats: null,
      });
      setCurrentRoundNumber(1);
      setSessionId(null);  // Reset session ID
      sessionIdRef.current = null;  // Also reset ref
      agentIdRef.current = null;  // Also reset agent ID ref
      setError(null);
      setIsStreaming(false);
    }
  }, [isOpen]);  // Only depend on isOpen - use refs for other values

  if (!isOpen || !agent) return null;

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    
    files.forEach((file) => {
      const fileType = file.type.startsWith('image/') ? 'image' : 
                      file.type.includes('pdf') || file.type.includes('document') ? 'document' : 
                      'other';
      
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
    setCurrentRoundData({
      thinking: '',
      content: '',
      statusMessages: [],
      retryAttempts: [],
      errorFeedback: [],
      stats: null,
    });
    setCurrentRoundNumber(1);
    lastStatusTimeRef.current = Date.now();
    
    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();
    
    // Reset streaming data ref
    streamingDataRef.current = { 
      rounds: [], 
      currentRound: {
        thinking: '',
        content: '',
        statusMessages: [],
        retryAttempts: [],
        errorFeedback: [],
        stats: null,
      },
      currentRoundNumber: 1,
    };

    // Build conversation history (exclude system messages)
    const history = messages
      .filter(m => m.role !== 'system')
      .map(m => ({ role: m.role, content: m.content }));

    try {
      const filesToUpload = attachedFiles.map(af => af.file);
      
      await agentsApi.testAgent(
        agent.id,
        userMessage.content,
        (chunk) => {
          // Handle session event - track session ID for subsequent requests
          if (chunk.type === 'session') {
            const receivedSessionId = chunk.session_id;
            if (receivedSessionId) {
              setSessionId(receivedSessionId);
              const sandboxInfo = chunk.use_sandbox
                ? `[Docker sandbox: ${chunk.sandbox_id || 'pending'}]`
                : '[subprocess mode]';
              console.log(
                chunk.new_session
                  ? `New session created: ${receivedSessionId} ${sandboxInfo}`
                  : `Resumed session: ${receivedSessionId} ${sandboxInfo}`
              );
            }
            return;  // Don't process as other event types
          }

          // Handle different message types
          if (chunk.type === 'info') {
            // Round number info - start new round
            const roundMatch = chunk.content.match(/第\s*(\d+)\s*轮/);
            if (roundMatch) {
              const newRoundNumber = parseInt(roundMatch[1], 10);
              
              // Save previous round if it has content
              if (streamingDataRef.current.currentRound.content || 
                  streamingDataRef.current.currentRound.thinking) {
                const completedRound: ConversationRound = {
                  roundNumber: streamingDataRef.current.currentRoundNumber,
                  thinking: streamingDataRef.current.currentRound.thinking,
                  content: streamingDataRef.current.currentRound.content,
                  statusMessages: streamingDataRef.current.currentRound.statusMessages,
                  retryAttempts: streamingDataRef.current.currentRound.retryAttempts.length > 0 
                    ? streamingDataRef.current.currentRound.retryAttempts 
                    : undefined,
                  errorFeedback: streamingDataRef.current.currentRound.errorFeedback.length > 0 
                    ? streamingDataRef.current.currentRound.errorFeedback 
                    : undefined,
                  stats: streamingDataRef.current.currentRound.stats || undefined,
                };
                
                streamingDataRef.current.rounds.push(completedRound);
                setCurrentRounds([...streamingDataRef.current.rounds]);
              }
              
              // Start new round
              streamingDataRef.current.currentRoundNumber = newRoundNumber;
              streamingDataRef.current.currentRound = {
                thinking: '',
                content: '',
                statusMessages: [],
                retryAttempts: [],
                errorFeedback: [],
                stats: null,
              };
              setCurrentRoundNumber(newRoundNumber);
              setCurrentRoundData({ ...streamingDataRef.current.currentRound });
            }
            
            // Add to status messages
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
            // Retry attempt
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
            // Error feedback
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
            
          } else if (chunk.type === 'start' || chunk.type === 'tool_call' || 
                     chunk.type === 'tool_result' || chunk.type === 'tool_error' || 
                     chunk.type === 'done') {
            // Status messages
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
            // Thinking content
            streamingDataRef.current.currentRound.thinking += chunk.content;
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });
            
          } else if (chunk.type === 'content') {
            // Response content
            streamingDataRef.current.currentRound.content += chunk.content;
            setCurrentRoundData({ ...streamingDataRef.current.currentRound });

          } else if (chunk.type === 'round_stats') {
            // Per-round statistics - apply to current round
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
            // Final statistics (legacy - apply to current round if no round_stats received)
            const stats = {
              timeToFirstToken: chunk.timeToFirstToken,
              tokensPerSecond: chunk.tokensPerSecond,
              inputTokens: chunk.inputTokens,
              outputTokens: chunk.outputTokens,
              totalTokens: chunk.totalTokens,
              totalTime: chunk.totalTime,
            };
            // Only set if not already set by round_stats
            if (!streamingDataRef.current.currentRound.stats) {
              streamingDataRef.current.currentRound.stats = stats;
              setCurrentRoundData({ ...streamingDataRef.current.currentRound });
            }

          } else if (chunk.type === 'error') {
            setError(chunk.content);
            setIsStreaming(false);
          }
        },
        (error) => {
          setError(error);
          setIsStreaming(false);
          setCurrentRounds([]);
          setCurrentRoundData({
            thinking: '',
            content: '',
            statusMessages: [],
            retryAttempts: [],
            errorFeedback: [],
            stats: null,
          });
          streamingDataRef.current = { 
            rounds: [], 
            currentRound: {
              thinking: '',
              content: '',
              statusMessages: [],
              retryAttempts: [],
              errorFeedback: [],
              stats: null,
            },
            currentRoundNumber: 1,
          };
        },
        () => {
          // On complete - save final round and create message
          const { rounds, currentRound, currentRoundNumber } = streamingDataRef.current;
          
          // Save current round if it has content
          if (currentRound.content || currentRound.thinking) {
            const completedRound: ConversationRound = {
              roundNumber: currentRoundNumber,
              thinking: currentRound.thinking,
              content: currentRound.content,
              statusMessages: currentRound.statusMessages,
              retryAttempts: currentRound.retryAttempts.length > 0 ? currentRound.retryAttempts : undefined,
              errorFeedback: currentRound.errorFeedback.length > 0 ? currentRound.errorFeedback : undefined,
              stats: currentRound.stats || undefined,
            };
            
            rounds.push(completedRound);
          }
          
          // Create assistant message with all rounds
          if (rounds.length > 0) {
            // Use the last round's content as the main message content
            const lastRound = rounds[rounds.length - 1];
            
            const newMessage: Message = {
              role: 'assistant',
              content: lastRound.content || lastRound.thinking || '',
              timestamp: new Date(),
              rounds: rounds,
            };
            
            setMessages((prev) => [...prev, newMessage]);
          }
          
          // Reset streaming state
          setCurrentRounds([]);
          setCurrentRoundData({
            thinking: '',
            content: '',
            statusMessages: [],
            retryAttempts: [],
            errorFeedback: [],
            stats: null,
          });
          setCurrentRoundNumber(1);
          setIsStreaming(false);
          abortControllerRef.current = null;
          streamingDataRef.current = { 
            rounds: [], 
            currentRound: {
              thinking: '',
              content: '',
              statusMessages: [],
              retryAttempts: [],
              errorFeedback: [],
              stats: null,
            },
            currentRoundNumber: 1,
          };
        },
        history,
        filesToUpload.length > 0 ? filesToUpload : undefined,
        abortControllerRef.current?.signal,
        sessionId || undefined  // Pass existing session ID for subsequent requests
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      setIsStreaming(false);
      setCurrentRounds([]);
      setCurrentRoundData({
        thinking: '',
        content: '',
        statusMessages: [],
        retryAttempts: [],
        errorFeedback: [],
        stats: null,
      });
      streamingDataRef.current = { 
        rounds: [], 
        currentRound: {
          thinking: '',
          content: '',
          statusMessages: [],
          retryAttempts: [],
          errorFeedback: [],
          stats: null,
        },
        currentRoundNumber: 1,
      };
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
      abortControllerRef.current = null;
      setIsStreaming(false);
      setError('输出已终止');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md overflow-auto" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-5xl my-auto h-[85vh] flex flex-col modal-panel rounded-[24px] shadow-2xl overflow-hidden">
        {/* Header with gradient */}
        <div className="relative bg-gradient-to-r from-emerald-500 to-cyan-500 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-white/20 backdrop-blur-sm rounded-xl">
                <Bot className="w-6 h-6 text-white" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  {agent.name}
                  <Sparkles className="w-4 h-4" />
                </h2>
                <p className="text-xs text-white/80">AI Agent Testing Environment</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors text-white"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Messages Area with custom scrollbar */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 scrollbar-thin scrollbar-thumb-zinc-300 dark:scrollbar-thumb-zinc-700 scrollbar-track-transparent">
          {messages.map((message, index) => (
            <div key={index} className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              {message.role === 'user' ? (
                <div className="flex justify-end">
                  <div className="max-w-[75%] space-y-2">
                    {/* User message */}
                    <div className="rounded-[24px] px-4 py-3 bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-500/20">
                      <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">{message.content}</p>
                      
                      {/* Attachments */}
                      {message.attachments && message.attachments.length > 0 && (
                        <div className="mt-2 space-y-2">
                          {message.attachments.map((attachment) => (
                            <div key={attachment.id} className="flex items-center gap-2 p-2 bg-white/10 rounded-lg backdrop-blur-sm">
                              {attachment.type === 'image' ? (
                                <>
                                  <ImageIcon className="w-4 h-4" />
                                  {attachment.preview && (
                                    <img src={attachment.preview} alt={attachment.file.name} className="w-16 h-16 object-cover rounded" />
                                  )}
                                </>
                              ) : (
                                <FileText className="w-4 h-4" />
                              )}
                              <span className="text-xs truncate flex-1">{attachment.file.name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      
                      <p className="text-xs mt-2 text-emerald-100 opacity-80">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                </div>
              ) : message.role === 'system' ? (
                <div className="flex justify-center">
                  <div className="px-4 py-2 bg-zinc-100 dark:bg-zinc-800 rounded-full">
                    <p className="text-xs text-zinc-600 dark:text-zinc-400 font-medium">
                      {message.content}
                    </p>
                  </div>
                </div>
              ) : message.role === 'assistant' ? (
                <div className="flex justify-start">
                  <div className="max-w-[85%] space-y-3">
                    {/* Multi-round display */}
                    {message.rounds && message.rounds.length > 0 ? (
                      <>
                        {message.rounds.map((round, roundIdx) => (
                          <ConversationRoundComponent
                            key={roundIdx}
                            round={round}
                            isLatest={roundIdx === message.rounds!.length - 1}
                            defaultCollapsed={roundIdx < message.rounds!.length - 1}
                          />
                        ))}
                        
                        {/* Timestamp footer */}
                        <div className="flex justify-end">
                          <p className="text-xs text-zinc-500 dark:text-zinc-400">
                            {message.timestamp.toLocaleTimeString()}
                          </p>
                        </div>
                      </>
                    ) : (
                      /* Fallback for old single-round messages */
                      <div className="rounded-[24px] px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 shadow-lg">
                        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                            {message.content}
                          </ReactMarkdown>
                        </div>
                        
                        <div className="flex items-center justify-between mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
                          <p className="text-xs text-zinc-500 dark:text-zinc-400">
                            {message.timestamp.toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          ))}

          {/* Current streaming rounds */}
          {isStreaming && (currentRounds.length > 0 || currentRoundData.thinking || currentRoundData.content) && (
            <div className="flex justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="max-w-[85%] space-y-3">
                {/* Completed rounds */}
                {currentRounds.map((round, idx) => (
                  <ConversationRoundComponent
                    key={idx}
                    round={round}
                    isLatest={false}
                    defaultCollapsed={true}
                  />
                ))}
                
                {/* Current round being streamed */}
                {(currentRoundData.thinking || currentRoundData.content || 
                  currentRoundData.statusMessages.length > 0 ||
                  currentRoundData.retryAttempts.length > 0 ||
                  currentRoundData.errorFeedback.length > 0) && (
                  <div className="space-y-2">
                    {/* Round header */}
                    <div className="flex items-center gap-2 px-2">
                      <div className="h-px flex-1 bg-gradient-to-r from-transparent via-emerald-300 dark:via-emerald-700 to-transparent" />
                      <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/30 rounded-full animate-pulse">
                        第 {currentRoundNumber} 轮 (进行中)
                      </span>
                      <div className="h-px flex-1 bg-gradient-to-r from-transparent via-emerald-300 dark:via-emerald-700 to-transparent" />
                    </div>

                    {/* Retry attempts */}
                    {currentRoundData.retryAttempts.length > 0 && (
                      <div className="space-y-1.5">
                        {currentRoundData.retryAttempts.map((retry, idx) => (
                          <RetryIndicator 
                            key={idx} 
                            retry={retry} 
                            isActive={idx === currentRoundData.retryAttempts.length - 1}
                          />
                        ))}
                      </div>
                    )}

                    {/* Error feedback */}
                    {currentRoundData.errorFeedback.length > 0 && (
                      <div className="space-y-1.5">
                        {currentRoundData.errorFeedback.map((feedback, idx) => (
                          <ErrorFeedbackDisplay 
                            key={idx} 
                            feedback={feedback}
                            defaultCollapsed={idx < currentRoundData.errorFeedback.length - 1}
                          />
                        ))}
                      </div>
                    )}

                    {/* Status messages */}
                    {currentRoundData.statusMessages.length > 0 && (
                      <div className="rounded-xl overflow-hidden border-2 border-emerald-300 dark:border-emerald-700 bg-white dark:bg-zinc-800 shadow-lg">
                        <div className="px-4 py-2.5 bg-gradient-to-r from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20">
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-emerald-500 animate-pulse" />
                            <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                              Processing... ({currentRoundData.statusMessages.length} steps)
                            </span>
                          </div>
                        </div>
                        <div className="px-4 py-3 space-y-2 bg-emerald-50/30 dark:bg-emerald-900/10">
                          {currentRoundData.statusMessages.map((status, idx) => (
                            <div key={idx} className="flex items-start gap-2.5 text-xs">
                              <div
                                className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${
                                  status.type === 'start'
                                    ? 'bg-blue-500 animate-pulse'
                                    : status.type === 'info'
                                    ? 'bg-cyan-500'
                                    : status.type === 'tool_call'
                                    ? 'bg-orange-500 animate-pulse'
                                    : status.type === 'tool_result'
                                    ? 'bg-green-500'
                                    : status.type === 'tool_error'
                                    ? 'bg-red-500'
                                    : status.type === 'done'
                                    ? 'bg-green-500'
                                    : 'bg-zinc-500'
                                }`}
                              />
                              <span className={`flex-1 leading-relaxed ${
                                status.type === 'tool_call'
                                  ? 'text-orange-700 dark:text-orange-300 font-medium'
                                  : status.type === 'tool_result'
                                  ? 'text-green-700 dark:text-green-300'
                                  : status.type === 'tool_error'
                                  ? 'text-red-700 dark:text-red-300'
                                  : 'text-zinc-700 dark:text-zinc-300'
                              }`}>
                                {status.content}
                              </span>
                              {status.duration !== undefined && (
                                <span className="text-zinc-500 dark:text-zinc-400 text-[10px] font-mono ml-2">
                                  {status.duration.toFixed(2)}s
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Thinking content */}
                    {currentRoundData.thinking && (
                      <div className="rounded-xl overflow-hidden border-2 border-purple-300 dark:border-purple-700 bg-gradient-to-br from-purple-50 to-purple-100/50 dark:from-purple-900/20 dark:to-purple-800/10 shadow-lg">
                        <div className="px-4 py-2.5 bg-purple-100/80 dark:bg-purple-900/30 border-b border-purple-200 dark:border-purple-700">
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400 animate-pulse" />
                            <span className="text-xs font-semibold text-purple-700 dark:text-purple-300">
                              Thinking...
                            </span>
                          </div>
                        </div>
                        <div className="px-4 py-3">
                          <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 text-purple-900 dark:text-purple-100">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                              {currentRoundData.thinking}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Response content */}
                    {currentRoundData.content && (
                      <div className="rounded-[24px] px-4 py-3 bg-white dark:bg-zinc-800 border-2 border-emerald-300 dark:border-emerald-700 shadow-lg shadow-emerald-500/10">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                          <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                            Generating...
                          </span>
                        </div>
                        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                            {currentRoundData.content}
                          </ReactMarkdown>
                        </div>
                        {currentRoundData.stats && (
                          <div className="flex items-center gap-3 mt-3 pt-3 border-t border-emerald-200 dark:border-emerald-800 text-[10px] font-medium">
                            <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                              ⚡ {currentRoundData.stats.timeToFirstToken}s
                            </span>
                            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                              🚀 {currentRoundData.stats.tokensPerSecond} tok/s
                            </span>
                            <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                              📊 {currentRoundData.stats.inputTokens} / {currentRoundData.stats.outputTokens}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="flex justify-center animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="max-w-[85%] rounded-xl px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-start gap-3 shadow-lg">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                    Error
                  </p>
                  <p className="text-xs text-red-600 dark:text-red-500 mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area with modern design */}
        <div className="border-t border-zinc-200 dark:border-zinc-800 modal-panel px-6 py-4">
          {/* Attached Files Preview */}
          {attachedFiles.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {attachedFiles.map((file) => (
                <div
                  key={file.id}
                  className="relative group flex items-center gap-2 px-3 py-2 bg-zinc-100 dark:bg-zinc-800 rounded-lg border border-zinc-200 dark:border-zinc-700"
                >
                  {file.type === 'image' ? (
                    <>
                      <ImageIcon className="w-4 h-4 text-emerald-500" />
                      {file.preview && (
                        <img src={file.preview} alt={file.file.name} className="w-10 h-10 object-cover rounded" />
                      )}
                    </>
                  ) : (
                    <FileText className="w-4 h-4 text-blue-500" />
                  )}
                  <span className="text-xs text-zinc-700 dark:text-zinc-300 max-w-[150px] truncate">
                    {file.file.name}
                  </span>
                  <button
                    onClick={() => removeFile(file.id)}
                    className="ml-1 p-1 hover:bg-red-100 dark:hover:bg-red-900/20 rounded transition-colors"
                  >
                    <XIcon className="w-3 h-3 text-red-500" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            {/* File upload button */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,.pdf,.doc,.docx,.txt"
              onChange={handleFileSelect}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming}
              className="p-3 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-xl transition-colors text-zinc-600 dark:text-zinc-400 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Attach files"
            >
              <Paperclip className="w-5 h-5" />
            </button>

            {/* Text input */}
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isStreaming
                    ? 'Waiting for response...'
                    : 'Type your message or attach files...'
                }
                disabled={isStreaming}
                rows={1}
                className="w-full px-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl focus:outline-none focus:ring-0 focus:border-emerald-400 focus:shadow-[0_0_0_3px_rgba(16,185,129,0.15)] text-sm text-zinc-900 dark:text-zinc-100 resize-none disabled:opacity-50 disabled:cursor-not-allowed placeholder:text-zinc-400 dark:placeholder:text-zinc-500 transition-all"
                style={{ minHeight: '48px', maxHeight: '120px' }}
              />
            </div>

            {/* Send/Stop button */}
            {isStreaming ? (
              <button
                onClick={handleAbortStreaming}
                className="px-5 py-3 bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white rounded-xl font-semibold transition-all flex items-center gap-2 shadow-lg shadow-red-500/20"
                title="终止输出"
              >
                <XIcon className="w-5 h-5" />
                <span>终止</span>
              </button>
            ) : (
              <button
                onClick={handleSendMessage}
                disabled={!inputMessage.trim() && attachedFiles.length === 0}
                className="px-5 py-3 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white rounded-xl font-semibold transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-500/20 disabled:shadow-none"
              >
                <Send className="w-5 h-5" />
              </button>
            )}
          </div>
          
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2 text-center">
            Press Enter to send • Shift+Enter for new line • Attach images and documents
          </p>
        </div>
      </div>
    </div>
  );
};
