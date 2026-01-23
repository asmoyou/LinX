import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Send, Loader2, AlertCircle, Bot } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Agent } from '@/types/agent';
import { agentsApi } from '@/api';

interface TestAgentModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentResponse]);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      // Add welcome message
      if (messages.length === 0) {
        setMessages([
          {
            role: 'system',
            content: `Testing ${agent?.name}. Send a message to start the conversation.`,
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

    try {
      await agentsApi.testAgent(
        agent.id,
        userMessage.content,
        (chunk) => {
          if (chunk.type === 'status') {
            // Status updates (optional: show in UI)
            console.log('Status:', chunk.content);
          } else if (chunk.type === 'content') {
            // Streaming content
            setCurrentResponse((prev) => prev + chunk.content);
          } else if (chunk.type === 'done') {
            // Complete response
            const assistantMessage: Message = {
              role: 'assistant',
              content: chunk.content,
              timestamp: new Date(),
            };
            setMessages((prev) => [...prev, assistantMessage]);
            setCurrentResponse('');
            setIsStreaming(false);
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
        },
        () => {
          setIsStreaming(false);
        }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      setIsStreaming(false);
      setCurrentResponse('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <GlassPanel className="w-full max-w-4xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-zinc-500/10">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/10 rounded-lg">
              <Bot className="w-6 h-6 text-emerald-500" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-zinc-800 dark:text-zinc-200">
                {t('agent.testAgent')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">{agent.name}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-500/5 rounded-lg transition-colors text-zinc-600 dark:text-zinc-400"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto mb-4 space-y-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${
                message.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  message.role === 'user'
                    ? 'bg-emerald-500 text-white'
                    : message.role === 'system'
                    ? 'bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 text-sm italic'
                    : 'bg-zinc-500/5 text-zinc-800 dark:text-zinc-200'
                }`}
              >
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
                <p
                  className={`text-xs mt-1 ${
                    message.role === 'user'
                      ? 'text-emerald-100'
                      : 'text-zinc-500 dark:text-zinc-400'
                  }`}
                >
                  {message.timestamp.toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}

          {/* Streaming Response */}
          {currentResponse && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-zinc-500/5 text-zinc-800 dark:text-zinc-200">
                <p className="whitespace-pre-wrap break-words">{currentResponse}</p>
                <div className="flex items-center gap-1 mt-2">
                  <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                  <div
                    className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"
                    style={{ animationDelay: '0.2s' }}
                  />
                  <div
                    className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"
                    style={{ animationDelay: '0.4s' }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="flex justify-center">
              <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-red-500/10 border border-red-500/20 flex items-start gap-2">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                    Error
                  </p>
                  <p className="text-sm text-red-600 dark:text-red-500">{error}</p>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-zinc-500/10 pt-4">
          <div className="flex gap-3">
            <textarea
              ref={inputRef}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isStreaming
                  ? 'Waiting for response...'
                  : 'Type your message... (Enter to send, Shift+Enter for new line)'
              }
              disabled={isStreaming}
              rows={3}
              className="flex-1 px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200 resize-none disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || isStreaming}
              className="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-semibold transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed self-end"
            >
              {isStreaming ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <Send className="w-5 h-5" />
                  Send
                </>
              )}
            </button>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </GlassPanel>
    </div>
  );
};
