/**
 * Conversation Round Component
 * 
 * Displays a single round of multi-turn agent execution.
 * Each round shows thinking, content, status messages, retries, and errors separately.
 * 
 * References:
 * - Backend: backend/agent_framework/base_agent.py
 * - Documentation: docs/backend/agent-error-recovery.md
 */

import React, { useState, useMemo } from 'react';
import { Brain, ChevronDown, ChevronUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ConversationRound } from '@/types/streaming';
import { RetryIndicator } from './RetryIndicator';
import { ErrorFeedbackDisplay } from './ErrorFeedbackDisplay';
import { createMarkdownComponents } from './CodeBlock';

interface ConversationRoundProps {
  round: ConversationRound;
  isLatest?: boolean;
  isStreaming?: boolean;
  defaultCollapsed?: boolean;
}

export const ConversationRoundComponent: React.FC<ConversationRoundProps> = ({
  round,
  isLatest = false,
  isStreaming = false,
  defaultCollapsed = false
}) => {
  const [statusCollapsed, setStatusCollapsed] = useState(defaultCollapsed);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(defaultCollapsed);

  // Memoize markdown components to prevent re-creation on each render
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);

  return (
    <div className="space-y-2">
      {/* Round header */}
      <div className="flex items-center gap-2 px-2">
        <div className={`h-px flex-1 bg-gradient-to-r from-transparent ${isStreaming ? 'via-emerald-300 dark:via-emerald-700' : 'via-zinc-300 dark:via-zinc-700'} to-transparent`} />
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
          isStreaming 
            ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-900/30 animate-pulse' 
            : 'text-zinc-500 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800'
        }`}>
          第 {round.roundNumber} 轮 {isStreaming && '(进行中)'}
        </span>
        <div className={`h-px flex-1 bg-gradient-to-r from-transparent ${isStreaming ? 'via-emerald-300 dark:via-emerald-700' : 'via-zinc-300 dark:via-zinc-700'} to-transparent`} />
      </div>

      {/* Retry attempts */}
      {round.retryAttempts && round.retryAttempts.length > 0 && (
        <div className="space-y-1.5">
          {round.retryAttempts.map((retry, idx) => (
            <RetryIndicator 
              key={idx} 
              retry={retry} 
              isActive={isStreaming && idx === round.retryAttempts!.length - 1}
            />
          ))}
        </div>
      )}

      {/* Error feedback */}
      {round.errorFeedback && round.errorFeedback.length > 0 && (
        <div className="space-y-1.5">
          {round.errorFeedback.map((feedback, idx) => (
            <ErrorFeedbackDisplay 
              key={idx} 
              feedback={feedback}
              defaultCollapsed={!isStreaming && (!isLatest || idx < round.errorFeedback!.length - 1)}
            />
          ))}
        </div>
      )}

      {/* Agent Process (Status Messages) */}
      {round.statusMessages.length > 0 && (
        <div className={`rounded-xl overflow-hidden border ${
          isStreaming ? 'border-emerald-300 dark:border-emerald-700 shadow-lg' : 'border-zinc-200 dark:border-zinc-700 shadow-sm'
        } bg-white dark:bg-zinc-800`}>
          <button
            onClick={() => setStatusCollapsed(!statusCollapsed)}
            className={`w-full flex items-center justify-between px-4 py-2.5 bg-gradient-to-r ${
              isStreaming 
                ? 'from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20' 
                : 'from-zinc-50 to-zinc-100 dark:from-zinc-800 dark:to-zinc-800/50'
            } hover:from-zinc-100 hover:to-zinc-100 dark:hover:from-zinc-700 dark:hover:to-zinc-700/50 transition-all text-left`}
          >
            <div className="flex items-center gap-2">
              <Brain className={`w-4 h-4 ${isStreaming ? 'text-emerald-500 animate-pulse' : 'text-purple-500'}`} />
              <span className={`text-xs font-semibold ${isStreaming ? 'text-emerald-700 dark:text-emerald-300' : 'text-zinc-700 dark:text-zinc-300'}`}>
                {isStreaming ? 'Processing...' : 'Agent Process'} ({round.statusMessages.length} steps)
              </span>
            </div>
            {statusCollapsed ? (
              <ChevronDown className={`w-4 h-4 ${isStreaming ? 'text-emerald-500' : 'text-zinc-500'}`} />
            ) : (
              <ChevronUp className={`w-4 h-4 ${isStreaming ? 'text-emerald-500' : 'text-zinc-500'}`} />
            )}
          </button>
          {!statusCollapsed && (
            <div className={`px-4 py-3 space-y-2 ${isStreaming ? 'bg-emerald-50/30 dark:bg-emerald-900/10' : 'bg-zinc-50/50 dark:bg-zinc-900/50'}`}>
              {round.statusMessages.map((status, idx) => (
                <div key={idx} className="flex items-start gap-2.5 text-xs">
                  <div
                    className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${
                      status.type === 'start'
                        ? 'bg-blue-500 animate-pulse'
                        : status.type === 'info'
                        ? 'bg-cyan-500'
                        : status.type === 'thinking'
                        ? 'bg-purple-500 animate-pulse'
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
          )}
        </div>
      )}

      {/* Thinking Content */}
      {round.thinking && (
        <div className={`rounded-xl overflow-hidden border ${
          isStreaming ? 'border-purple-300 dark:border-purple-700 shadow-lg' : 'border-purple-200 dark:border-purple-700 shadow-sm'
        } bg-gradient-to-br from-purple-50 to-purple-100/50 dark:from-purple-900/20 dark:to-purple-800/10`}>
          <button
            onClick={() => setThinkingCollapsed(!thinkingCollapsed)}
            className={`w-full flex items-center justify-between gap-2 px-4 py-2.5 ${
              isStreaming ? 'bg-purple-100/80 dark:bg-purple-900/30' : 'bg-purple-100/80 dark:bg-purple-900/30'
            } border-b border-purple-200 dark:border-purple-700 hover:bg-purple-200/60 dark:hover:bg-purple-900/50 transition-colors`}
          >
            <div className="flex items-center gap-2">
              <Brain className={`w-4 h-4 ${isStreaming ? 'text-purple-600 dark:text-purple-400 animate-pulse' : 'text-purple-600 dark:text-purple-400'}`} />
              <span className="text-xs font-semibold text-purple-700 dark:text-purple-300">
                {isStreaming ? 'Thinking...' : 'Thinking Process'}
              </span>
            </div>
            {thinkingCollapsed ? (
              <ChevronDown className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            ) : (
              <ChevronUp className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            )}
          </button>
          {!thinkingCollapsed && (
            <div className="px-4 py-3">
              <p className="text-sm leading-relaxed whitespace-pre-wrap break-words text-purple-900 dark:text-purple-100">
                {round.thinking}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Response Content */}
      {round.content && (
        <div className={`rounded-[24px] px-4 py-3 bg-white dark:bg-zinc-800 border ${
          isStreaming ? 'border-emerald-300 dark:border-emerald-700 shadow-lg shadow-emerald-500/10' : 'border-zinc-200 dark:border-zinc-700 shadow-lg'
        }`}>
          {isStreaming && (
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                Generating...
              </span>
            </div>
          )}
          <div className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {round.content}
            </ReactMarkdown>
          </div>
          
          {/* Stats footer */}
          {round.stats && (
            <div className={`flex items-center justify-end gap-3 mt-3 pt-3 border-t ${
              isStreaming ? 'border-emerald-200 dark:border-emerald-800' : 'border-zinc-200 dark:border-zinc-700'
            } text-[10px] font-medium`}>
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400" title="Time to first token">
                ⚡ {round.stats.timeToFirstToken}s
              </span>
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400" title="Tokens per second">
                🚀 {round.stats.tokensPerSecond} tok/s
              </span>
              <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400" title="Input / Output tokens">
                📊 {round.stats.inputTokens} / {round.stats.outputTokens}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
