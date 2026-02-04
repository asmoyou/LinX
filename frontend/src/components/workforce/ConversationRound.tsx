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

import React, { useState } from 'react';
import { Brain, ChevronDown, ChevronUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ConversationRound } from '@/types/streaming';
import { RetryIndicator } from './RetryIndicator';
import { ErrorFeedbackDisplay } from './ErrorFeedbackDisplay';

interface ConversationRoundProps {
  round: ConversationRound;
  isLatest?: boolean;
  defaultCollapsed?: boolean;
}

export const ConversationRoundComponent: React.FC<ConversationRoundProps> = ({ 
  round, 
  isLatest = false,
  defaultCollapsed = false 
}) => {
  const [statusCollapsed, setStatusCollapsed] = useState(defaultCollapsed);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(defaultCollapsed);

  return (
    <div className="space-y-2">
      {/* Round header */}
      <div className="flex items-center gap-2 px-2">
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-zinc-300 dark:via-zinc-700 to-transparent" />
        <span className="text-[10px] font-semibold text-zinc-500 dark:text-zinc-400 px-2 py-0.5 bg-zinc-100 dark:bg-zinc-800 rounded-full">
          第 {round.roundNumber} 轮
        </span>
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-zinc-300 dark:via-zinc-700 to-transparent" />
      </div>

      {/* Retry attempts */}
      {round.retryAttempts && round.retryAttempts.length > 0 && (
        <div className="space-y-1.5">
          {round.retryAttempts.map((retry, idx) => (
            <RetryIndicator 
              key={idx} 
              retry={retry} 
              isActive={isLatest && idx === round.retryAttempts!.length - 1}
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
              defaultCollapsed={!isLatest || idx < round.errorFeedback!.length - 1}
            />
          ))}
        </div>
      )}

      {/* Agent Process (Status Messages) */}
      {round.statusMessages.length > 0 && (
        <div className="rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-sm">
          <button
            onClick={() => setStatusCollapsed(!statusCollapsed)}
            className="w-full flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-zinc-50 to-zinc-100 dark:from-zinc-800 dark:to-zinc-800/50 hover:from-zinc-100 hover:to-zinc-100 dark:hover:from-zinc-700 dark:hover:to-zinc-700/50 transition-all text-left"
          >
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-500" />
              <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                Agent Process ({round.statusMessages.length} steps)
              </span>
            </div>
            {statusCollapsed ? (
              <ChevronDown className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
            ) : (
              <ChevronUp className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />
            )}
          </button>
          {!statusCollapsed && (
            <div className="px-4 py-3 space-y-2 bg-zinc-50/50 dark:bg-zinc-900/50">
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
        <div className="rounded-xl overflow-hidden border border-purple-200 dark:border-purple-700 bg-gradient-to-br from-purple-50 to-purple-100/50 dark:from-purple-900/20 dark:to-purple-800/10 shadow-sm">
          <button
            onClick={() => setThinkingCollapsed(!thinkingCollapsed)}
            className="w-full flex items-center justify-between gap-2 px-4 py-2.5 bg-purple-100/80 dark:bg-purple-900/30 border-b border-purple-200 dark:border-purple-700 hover:bg-purple-200/60 dark:hover:bg-purple-900/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-600 dark:text-purple-400" />
              <span className="text-xs font-semibold text-purple-700 dark:text-purple-300">
                Thinking Process
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
              <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2 text-purple-900 dark:text-purple-100 prose-pre:overflow-x-auto prose-code:break-all">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {round.thinking}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Response Content */}
      {round.content && (
        <div className="rounded-[24px] px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 shadow-lg">
          <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-zinc-900 prose-pre:text-zinc-100 prose-pre:overflow-x-auto prose-code:break-all">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {round.content}
            </ReactMarkdown>
          </div>
          
          {/* Stats footer */}
          {round.stats && (
            <div className="flex items-center justify-end gap-3 mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700 text-[10px] font-medium">
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
