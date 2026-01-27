import React, { useState, useRef, useEffect } from 'react';
import { X, Send, Loader2, AlertCircle, Bot, ChevronDown, ChevronUp, Brain, Paperclip, Image as ImageIcon, FileText, X as XIcon, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Agent } from '@/types/agent';
import { agentsApi } from '@/api';

interface TestAgentModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
}

interface StatusMessage {
  content: string;
  type: 'start' | 'info' | 'thinking' | 'done' | 'error';
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
  thinkingContent?: string;  // 添加thinking内容字段
  timestamp: Date;
  statusMessages?: StatusMessage[];
  attachments?: AttachedFile[];
  stats?: {
    timeToFirstToken: number;
    tokensPerSecond: number;
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    totalTime: number;
  };
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
  const [currentResponse, setCurrentResponse] = useState('');
  const [currentThinking, setCurrentThinking] = useState('');  // 添加当前thinking内容
  const [currentStatusMessages, setCurrentStatusMessages] = useState<StatusMessage[]>([]);
  const [collapsedStatus, setCollapsedStatus] = useState<{ [key: number]: boolean }>({});
  const [collapsedThinking, setCollapsedThinking] = useState<{ [key: number]: boolean }>({});  // thinking 折叠状态
  const [streamingStatusCollapsed, setStreamingStatusCollapsed] = useState(false);  // 流式输出时的状态折叠
  const [streamingThinkingCollapsed, setStreamingThinkingCollapsed] = useState(false);  // 流式输出时的thinking折叠
  const [currentStats, setCurrentStats] = useState<Message['stats'] | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasReceivedThinkingRef = useRef<boolean>(false);  // 跟踪是否已收到thinking
  const hasReceivedContentRef = useRef<boolean>(false);  // 跟踪是否已收到content
  const lastStatusTimeRef = useRef<number>(Date.now());  // 记录上一条状态消息的时间
  const abortControllerRef = useRef<AbortController | null>(null);  // 用于终止流式输出
  const messagesLengthRef = useRef<number>(0);  // 追踪messages数组长度
  
  // Use refs to track streaming data for onComplete callback
  const streamingDataRef = useRef<{
    content: string;
    thinkingContent: string;  // 添加thinking内容追踪
    statusMessages: StatusMessage[];
    stats: Message['stats'] | null;
  }>({ content: '', thinkingContent: '', statusMessages: [], stats: null });

  // Update messagesLengthRef whenever messages change
  useEffect(() => {
    messagesLengthRef.current = messages.length;
  }, [messages]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentResponse]);

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

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setMessages([]);
      setInputMessage('');
      setAttachedFiles([]);
      setCurrentResponse('');
      setCurrentThinking('');
      setCurrentStatusMessages([]);
      setCurrentStats(null);
      setCollapsedStatus({});
      setCollapsedThinking({});  // 重置 thinking 折叠状态
      setStreamingStatusCollapsed(false);  // 重置流式状态折叠
      setStreamingThinkingCollapsed(false);  // 重置流式thinking折叠
      setError(null);
      setIsStreaming(false);
    }
  }, [isOpen]);

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
    setCurrentResponse('');
    setCurrentThinking('');  // 重置thinking内容
    setCurrentStatusMessages([]);
    setCurrentStats(null);
    hasReceivedThinkingRef.current = false;  // 重置thinking标志
    hasReceivedContentRef.current = false;  // 重置content标志
    lastStatusTimeRef.current = Date.now();  // 重置时间追踪
    setStreamingStatusCollapsed(false);  // 重置流式状态折叠
    setStreamingThinkingCollapsed(false);  // 重置流式thinking折叠
    
    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();
    
    // Reset streaming data ref
    streamingDataRef.current = { content: '', thinkingContent: '', statusMessages: [], stats: null };

    // Build conversation history (exclude system messages)
    const history = messages
      .filter(m => m.role !== 'system')
      .map(m => ({ role: m.role, content: m.content }));

    try {
      // Note: File processing is handled by agent skills
      // If agent has image_processing or document_processing skills, files will be processed
      // Otherwise, files are skipped and only text is sent to the agent
      
      // Extract File objects from attachments
      const filesToUpload = attachedFiles.map(af => af.file);
      
      await agentsApi.testAgent(
        agent.id,
        userMessage.content,
        (chunk) => {
          // 临时调试：只在类型变化时输出
          if (chunk.type === 'thinking' || chunk.type === 'content') {
            if (!window._lastChunkType || window._lastChunkType !== chunk.type) {
              console.log(`[TYPE CHANGE] ${window._lastChunkType || 'START'} -> ${chunk.type}`);
              window._lastChunkType = chunk.type;
            }
          }
          
          if (chunk.type === 'start' || chunk.type === 'info' || chunk.type === 'done') {
            const now = Date.now();
            const duration = (now - lastStatusTimeRef.current) / 1000;  // 转换为秒
            
            // 更新上一条消息的 duration
            if (streamingDataRef.current.statusMessages.length > 0) {
              const lastIndex = streamingDataRef.current.statusMessages.length - 1;
              streamingDataRef.current.statusMessages[lastIndex].duration = duration;
              
              // 更新显示
              setCurrentStatusMessages((prev) => {
                const updated = [...prev];
                if (updated.length > 0) {
                  updated[updated.length - 1].duration = duration;
                }
                return updated;
              });
            }
            
            // 添加新的状态消息
            const newStatus: StatusMessage = {
              content: chunk.content,
              type: chunk.type as 'start' | 'info' | 'thinking' | 'done' | 'error',
              timestamp: new Date(),
              duration: undefined,  // 将在下一条消息时计算
            };
            
            streamingDataRef.current.statusMessages.push(newStatus);
            setCurrentStatusMessages((prev) => [...prev, newStatus]);
            lastStatusTimeRef.current = now;  // 更新时间
          } else if (chunk.type === 'thinking') {
            // Thinking content (reasoning process)
            // 第一次收到thinking内容时，自动折叠当前正在显示的 Agent Process
            if (!hasReceivedThinkingRef.current) {
              hasReceivedThinkingRef.current = true;
              
              // 计算最后一条状态消息的耗时
              if (streamingDataRef.current.statusMessages.length > 0) {
                const now = Date.now();
                const duration = (now - lastStatusTimeRef.current) / 1000;
                const lastIndex = streamingDataRef.current.statusMessages.length - 1;
                streamingDataRef.current.statusMessages[lastIndex].duration = duration;
                
                setCurrentStatusMessages((prev) => {
                  const updated = [...prev];
                  if (updated.length > 0) {
                    updated[updated.length - 1].duration = duration;
                  }
                  return updated;
                });
              }
              
              // 立即折叠流式输出的 Agent Process
              setStreamingStatusCollapsed(true);
            }
            
            streamingDataRef.current.thinkingContent += chunk.content;
            setCurrentThinking(streamingDataRef.current.thinkingContent);
          } else if (chunk.type === 'content') {
            // 第一次收到content内容时，自动折叠当前正在显示的 Agent Process 和 Thinking
            if (!hasReceivedContentRef.current) {
              hasReceivedContentRef.current = true;
              
              // 计算最后一条状态消息的耗时
              if (streamingDataRef.current.statusMessages.length > 0) {
                const now = Date.now();
                const duration = (now - lastStatusTimeRef.current) / 1000;
                const lastIndex = streamingDataRef.current.statusMessages.length - 1;
                streamingDataRef.current.statusMessages[lastIndex].duration = duration;
                
                setCurrentStatusMessages((prev) => {
                  const updated = [...prev];
                  if (updated.length > 0) {
                    updated[updated.length - 1].duration = duration;
                  }
                  return updated;
                });
              }
              
              // 立即折叠流式输出的 Agent Process 和 Thinking Process
              setStreamingStatusCollapsed(true);
              setStreamingThinkingCollapsed(true);
            }
            
            streamingDataRef.current.content += chunk.content;
            setCurrentResponse(streamingDataRef.current.content);
          } else if (chunk.type === 'stats') {
            const stats = {
              timeToFirstToken: chunk.timeToFirstToken,
              tokensPerSecond: chunk.tokensPerSecond,
              inputTokens: chunk.inputTokens,
              outputTokens: chunk.outputTokens,
              totalTokens: chunk.totalTokens,
              totalTime: chunk.totalTime,
            };
            streamingDataRef.current.stats = stats;
            setCurrentStats(stats);
          } else if (chunk.type === 'error') {
            setError(chunk.content);
            setIsStreaming(false);
            setCurrentResponse('');
          }
        },
        (error) => {
          setError(error);
          setIsStreaming(false);
          setCurrentResponse('');
          setCurrentThinking('');
          streamingDataRef.current = { content: '', thinkingContent: '', statusMessages: [], stats: null };
        },
        () => {
          const { content, thinkingContent, statusMessages, stats } = streamingDataRef.current;
          
          if (content || thinkingContent) {
            const newMessage: Message = {
              role: 'assistant',
              content: content,
              thinkingContent: thinkingContent || undefined,
              timestamp: new Date(),
              statusMessages: statusMessages.length > 0 ? statusMessages : undefined,
              stats: stats || undefined,
            };
            
            // 只添加消息，不做任何其他操作
            setMessages((prev) => [...prev, newMessage]);
          }
          
          setCurrentResponse('');
          setCurrentThinking('');
          setCurrentStatusMessages([]);
          setCurrentStats(null);
          setIsStreaming(false);
          hasReceivedThinkingRef.current = false;
          hasReceivedContentRef.current = false;
          abortControllerRef.current = null;
          streamingDataRef.current = { content: '', thinkingContent: '', statusMessages: [], stats: null };
        },
        history,
        filesToUpload.length > 0 ? filesToUpload : undefined,
        abortControllerRef.current?.signal  // 传递 AbortSignal
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      setIsStreaming(false);
      setCurrentResponse('');
      setCurrentStatusMessages([]);
      setCurrentStats(null);
      streamingDataRef.current = { content: '', statusMessages: [], stats: null };
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const toggleStatusCollapse = (index: number) => {
    setCollapsedStatus((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const toggleThinkingCollapse = (index: number) => {
    setCollapsedThinking((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
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
      <div className="w-full max-w-5xl my-auto h-[85vh] flex flex-col bg-gradient-to-br from-white to-zinc-50 dark:from-zinc-900 dark:to-zinc-950 rounded-2xl shadow-2xl overflow-hidden">
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
                    <div className="rounded-2xl px-4 py-3 bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-500/20">
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
                  <div className="max-w-[85%] space-y-2">
                    {/* Agent Process (Status Messages) */}
                    {message.statusMessages && message.statusMessages.length > 0 && (
                      <div className="rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-sm">
                        <button
                          onClick={() => toggleStatusCollapse(index)}
                          className="w-full flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-zinc-50 to-zinc-100 dark:from-zinc-800 dark:to-zinc-800/50 hover:from-zinc-100 hover:to-zinc-100 dark:hover:from-zinc-700 dark:hover:to-zinc-700/50 transition-all text-left"
                        >
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-purple-500" />
                            <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                              Agent Process ({message.statusMessages.length} steps)
                            </span>
                          </div>
                          {(collapsedStatus[index] ?? streamingStatusCollapsed) ? (
                            <ChevronDown className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
                          ) : (
                            <ChevronUp className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
                          )}
                        </button>
                        {!(collapsedStatus[index] ?? streamingStatusCollapsed) && (
                          <div className="px-4 py-3 space-y-2 bg-zinc-50/50 dark:bg-zinc-900/50">
                            {message.statusMessages.map((status, idx) => (
                              <div key={idx} className="flex items-start gap-2.5 text-xs">
                                <div
                                  className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${
                                    status.type === 'start'
                                      ? 'bg-blue-500 animate-pulse'
                                      : status.type === 'info'
                                      ? 'bg-cyan-500'
                                      : status.type === 'thinking'
                                      ? 'bg-purple-500 animate-pulse'
                                      : status.type === 'done'
                                      ? 'bg-green-500'
                                      : 'bg-zinc-500'
                                  }`}
                                />
                                <span className="text-zinc-700 dark:text-zinc-300 flex-1 leading-relaxed">
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
                        )}
                      </div>
                    )}
                    
                    {/* Thinking Content (if exists) */}
                    {message.thinkingContent && (
                      <div className="rounded-xl overflow-hidden border border-purple-200 dark:border-purple-700 bg-gradient-to-br from-purple-50 to-purple-100/50 dark:from-purple-900/20 dark:to-purple-800/10 shadow-sm mb-2">
                        <button
                          onClick={() => toggleThinkingCollapse(index)}
                          className="w-full flex items-center justify-between gap-2 px-4 py-2.5 bg-purple-100/80 dark:bg-purple-900/30 border-b border-purple-200 dark:border-purple-700 hover:bg-purple-200/60 dark:hover:bg-purple-900/50 transition-colors"
                        >
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                            <span className="text-xs font-semibold text-purple-700 dark:text-purple-300">
                              Thinking Process
                            </span>
                          </div>
                          {(collapsedThinking[index] ?? streamingThinkingCollapsed) ? (
                            <ChevronDown className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                          ) : (
                            <ChevronUp className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                          )}
                        </button>
                        {!(collapsedThinking[index] ?? streamingThinkingCollapsed) && (
                          <div className="px-4 py-3">
                            <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2 text-purple-900 dark:text-purple-100">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {message.thinkingContent}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    
                    {/* Assistant Response */}
                    <div className="rounded-2xl px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 shadow-lg">
                      <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-zinc-900 prose-pre:text-zinc-100">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content}
                        </ReactMarkdown>
                      </div>
                      
                      {/* Stats footer */}
                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">
                          {message.timestamp.toLocaleTimeString()}
                        </p>
                        {message.stats && (
                          <div className="flex items-center gap-3 text-[10px] font-medium">
                            <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400" title="Time to first token">
                              ⚡ {message.stats.timeToFirstToken}s
                            </span>
                            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400" title="Tokens per second">
                              🚀 {message.stats.tokensPerSecond} tok/s
                            </span>
                            <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400" title="Input / Output tokens">
                              📊 {message.stats.inputTokens} / {message.stats.outputTokens}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          ))}

          {/* Current Status Messages (while streaming) */}
          {isStreaming && currentStatusMessages.length > 0 && (
            <div className="flex justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="max-w-[85%] rounded-xl overflow-hidden border border-purple-200 dark:border-purple-800 bg-white dark:bg-zinc-800 shadow-lg">
                <button
                  onClick={() => setStreamingStatusCollapsed(!streamingStatusCollapsed)}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 hover:from-purple-100 hover:to-purple-100 dark:hover:from-purple-900/30 dark:hover:to-purple-800/30 transition-all"
                >
                  <div className="flex items-center gap-2">
                    <Brain className="w-4 h-4 text-purple-500 animate-pulse" />
                    <span className="text-xs font-semibold text-purple-700 dark:text-purple-300">
                      Processing... ({currentStatusMessages.length} steps)
                    </span>
                  </div>
                  {streamingStatusCollapsed ? (
                    <ChevronDown className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                  ) : (
                    <ChevronUp className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                  )}
                </button>
                {!streamingStatusCollapsed && (
                  <div className="px-4 py-3 space-y-2 bg-purple-50/30 dark:bg-purple-900/10">
                    {currentStatusMessages.map((status, idx) => (
                      <div key={idx} className="flex items-start gap-2.5 text-xs">
                        <div
                          className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${
                            status.type === 'start'
                              ? 'bg-blue-500 animate-pulse'
                              : status.type === 'info'
                              ? 'bg-cyan-500'
                              : status.type === 'thinking'
                              ? 'bg-purple-500 animate-pulse'
                              : status.type === 'done'
                              ? 'bg-green-500'
                              : 'bg-zinc-500'
                          }`}
                        />
                        <span className="text-zinc-700 dark:text-zinc-300 flex-1 leading-relaxed">
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
                )}
              </div>
            </div>
          )}

          {/* Streaming Response */}
          {(currentThinking || currentResponse) && (
            <div className="flex justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="max-w-[85%] space-y-2">
                {/* Streaming Thinking Content */}
                {currentThinking && (
                  <div className="rounded-xl overflow-hidden border-2 border-purple-300 dark:border-purple-700 bg-gradient-to-br from-purple-50 to-purple-100/50 dark:from-purple-900/20 dark:to-purple-800/10 shadow-lg shadow-purple-500/10">
                    <button
                      onClick={() => setStreamingThinkingCollapsed(!streamingThinkingCollapsed)}
                      className="w-full flex items-center justify-between gap-2 px-4 py-2.5 bg-purple-100/80 dark:bg-purple-900/30 border-b border-purple-200 dark:border-purple-700 hover:bg-purple-200/60 dark:hover:bg-purple-900/50 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400 animate-pulse" />
                        <span className="text-xs font-semibold text-purple-700 dark:text-purple-300">
                          Thinking...
                        </span>
                      </div>
                      {streamingThinkingCollapsed ? (
                        <ChevronDown className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                      ) : (
                        <ChevronUp className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                      )}
                    </button>
                    {!streamingThinkingCollapsed && (
                      <div className="px-4 py-3">
                        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2 text-purple-900 dark:text-purple-100">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {currentThinking}
                          </ReactMarkdown>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                {/* Streaming Regular Content */}
                {currentResponse && (
                  <div className="rounded-2xl px-4 py-3 bg-white dark:bg-zinc-800 border-2 border-emerald-300 dark:border-emerald-700 shadow-lg shadow-emerald-500/10">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                      <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                        Generating...
                      </span>
                    </div>
                    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {currentResponse}
                      </ReactMarkdown>
                    </div>
                    {currentStats && (
                      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-emerald-200 dark:border-emerald-800 text-[10px] font-medium">
                        <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                          ⚡ {currentStats.timeToFirstToken}s
                        </span>
                        <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                          🚀 {currentStats.tokensPerSecond} tok/s
                        </span>
                        <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                          📊 {currentStats.inputTokens} / {currentStats.outputTokens}
                        </span>
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
        <div className="border-t border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-6 py-4">
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
