import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Send, Loader2, AlertCircle, Bot, ChevronDown, ChevronUp, Brain } from 'lucide-react';
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
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  statusMessages?: StatusMessage[];  // 每个回复都有自己的状态消息
}

export const TestAgentModal: React.FC<TestAgentModalProps> = ({
  agent,
  isOpen,
  onClose,
}) => {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentResponse, setCurrentResponse] = useState('');
  const [currentStatusMessages, setCurrentStatusMessages] = useState<StatusMessage[]>([]);
  const [collapsedStatus, setCollapsedStatus] = useState<{ [key: number]: boolean }>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  
  // Use refs to track streaming data for onComplete callback
  const streamingDataRef = useRef<{
    content: string;
    statusMessages: StatusMessage[];
  }>({ content: '', statusMessages: [] });

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
      setCurrentResponse('');
      setCurrentStatusMessages([]);
      setCollapsedStatus({});
      setError(null);
      setIsStreaming(false);
    }
  }, [isOpen]);

  if (!isOpen || !agent) return null;

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isStreaming) return;

    const userMessage: Message = {
      role: 'user',
      content: inputMessage.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');
    setError(null);
    setIsStreaming(true);
    setCurrentResponse('');
    setCurrentStatusMessages([]);
    
    // Reset streaming data ref
    streamingDataRef.current = { content: '', statusMessages: [] };

    try {
      await agentsApi.testAgent(
        agent.id,
        userMessage.content,
        (chunk) => {
          if (chunk.type === 'start' || chunk.type === 'info' || chunk.type === 'thinking' || chunk.type === 'done') {
            // 收集状态消息
            const newStatus: StatusMessage = {
              content: chunk.content,
              type: chunk.type as 'start' | 'info' | 'thinking' | 'done' | 'error',
              timestamp: new Date(),
            };
            
            // Update both state and ref
            streamingDataRef.current.statusMessages.push(newStatus);
            setCurrentStatusMessages((prev) => [...prev, newStatus]);
          } else if (chunk.type === 'content') {
            // content 是最终回复内容
            streamingDataRef.current.content += chunk.content;
            setCurrentResponse(streamingDataRef.current.content);
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
          streamingDataRef.current = { content: '', statusMessages: [] };
        },
        () => {
          // Stream 结束 - 保存消息和状态
          const { content, statusMessages } = streamingDataRef.current;
          
          if (content) {
            const newMessage: Message = {
              role: 'assistant',
              content: content,
              timestamp: new Date(),
              statusMessages: statusMessages.length > 0 ? statusMessages : undefined,
            };
            
            setMessages((prev) => {
              // 默认折叠新消息的状态
              const newIndex = prev.length;
              setCollapsedStatus((prevCollapsed) => ({
                ...prevCollapsed,
                [newIndex]: true,
              }));
              
              return [...prev, newMessage];
            });
          }
          
          // Clear streaming state
          setCurrentResponse('');
          setCurrentStatusMessages([]);
          setIsStreaming(false);
          streamingDataRef.current = { content: '', statusMessages: [] };
        }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      setIsStreaming(false);
      setCurrentResponse('');
      setCurrentStatusMessages([]);
      streamingDataRef.current = { content: '', statusMessages: [] };
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm overflow-auto ml-64">
      <div className="w-full max-w-4xl my-auto h-[80vh] flex flex-col bg-white dark:bg-zinc-900 rounded-3xl shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-3 pb-3 border-b border-zinc-200 dark:border-zinc-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/10 rounded-lg">
              <Bot className="w-5 h-5 text-emerald-500" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">
                {t('agent.testAgent')}
              </h2>
              <p className="text-xs text-zinc-600 dark:text-zinc-400">{agent.name}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors text-zinc-600 dark:text-zinc-400"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto mb-3 space-y-3">
          {messages.map((message, index) => (
            <div key={index}>
              {message.role === 'user' ? (
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-xl px-3 py-2 bg-emerald-500 text-white shadow-sm">
                    <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
                    <p className="text-xs mt-1 text-emerald-100 opacity-70">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              ) : message.role === 'system' ? (
                <div className="w-full text-center">
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 italic">
                    {message.content}
                  </p>
                </div>
              ) : message.role === 'assistant' ? (
                <div className="flex justify-start">
                  <div className="max-w-[85%] space-y-2">
                    {/* Agent Process (Status Messages) */}
                    {message.statusMessages && message.statusMessages.length > 0 && (
                      <div className="rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-sm">
                        <button
                          onClick={() => toggleStatusCollapse(index)}
                          className="w-full flex items-center justify-between px-3 py-2 bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-700/50 transition-colors text-left"
                        >
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
                            <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                              Agent Process ({message.statusMessages.length} steps)
                            </span>
                          </div>
                          {collapsedStatus[index] ? (
                            <ChevronDown className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
                          ) : (
                            <ChevronUp className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
                          )}
                        </button>
                        {!collapsedStatus[index] && (
                          <div className="px-3 py-2 space-y-1 bg-zinc-50/50 dark:bg-zinc-900/50">
                            {message.statusMessages.map((status, idx) => (
                              <div key={idx} className="flex items-start gap-2 text-xs">
                                <div
                                  className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${
                                    status.type === 'start'
                                      ? 'bg-blue-500'
                                      : status.type === 'info'
                                      ? 'bg-cyan-500'
                                      : status.type === 'thinking'
                                      ? 'bg-purple-500'
                                      : status.type === 'done'
                                      ? 'bg-green-500'
                                      : 'bg-zinc-500'
                                  }`}
                                />
                                <span className="text-zinc-700 dark:text-zinc-300 flex-1">
                                  {status.content}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    
                    {/* Assistant Response */}
                    <div className="rounded-xl px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 shadow-sm">
                      <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-pre:my-1">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content}
                        </ReactMarkdown>
                      </div>
                      <p className="text-xs mt-1 text-zinc-500 dark:text-zinc-400">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          ))}

          {/* Current Status Messages (while streaming) */}
          {isStreaming && currentStatusMessages.length > 0 && (
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-sm">
                <div className="flex items-center justify-between px-3 py-2 bg-zinc-50 dark:bg-zinc-800/50">
                  <div className="flex items-center gap-2">
                    <Brain className="w-4 h-4 text-zinc-500 dark:text-zinc-400 animate-pulse" />
                    <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      Processing... ({currentStatusMessages.length} steps)
                    </span>
                  </div>
                </div>
                <div className="px-3 py-2 space-y-1 bg-zinc-50/50 dark:bg-zinc-900/50">
                  {currentStatusMessages.map((status, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs">
                      <div
                        className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${
                          status.type === 'start'
                            ? 'bg-blue-500'
                            : status.type === 'info'
                            ? 'bg-cyan-500'
                            : status.type === 'thinking'
                            ? 'bg-purple-500'
                            : status.type === 'done'
                            ? 'bg-green-500'
                            : 'bg-zinc-500'
                        }`}
                      />
                      <span className="text-zinc-700 dark:text-zinc-300 flex-1">
                        {status.content}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Streaming Response */}
          {currentResponse && (
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-xl px-3 py-2 bg-white dark:bg-zinc-800 border border-emerald-500/30 dark:border-emerald-500/30 shadow-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                  <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    Streaming
                  </span>
                </div>
                <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-pre:my-1">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {currentResponse}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="flex justify-center">
              <div className="max-w-[85%] rounded-xl px-3 py-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-start gap-2 shadow-sm">
                <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-red-700 dark:text-red-400">
                    Error
                  </p>
                  <p className="text-xs text-red-600 dark:text-red-500">{error}</p>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-zinc-200 dark:border-zinc-700 pt-3">
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isStreaming
                  ? 'Waiting for response...'
                  : 'Type your message...'
              }
              disabled={isStreaming}
              rows={2}
              className="flex-1 px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-sm text-zinc-900 dark:text-zinc-100 resize-none disabled:opacity-50 disabled:cursor-not-allowed placeholder:text-zinc-400 dark:placeholder:text-zinc-500"
            />
            <button
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || isStreaming}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-semibold transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed self-end text-sm shadow-sm"
            >
              {isStreaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
            Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
};
