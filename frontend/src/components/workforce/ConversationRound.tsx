import React, { useState, useMemo, useEffect } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  Zap,
  PlayCircle,
  Clock,
  Layout,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ConversationRound } from '@/types/streaming';
import { RetryIndicator } from './RetryIndicator';
import { ErrorFeedbackDisplay } from './ErrorFeedbackDisplay';
import { createMarkdownComponents } from './CodeBlock';
import { motion, AnimatePresence } from 'framer-motion';

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
  defaultCollapsed = false,
}) => {
  const [statusCollapsed, setStatusCollapsed] = useState(defaultCollapsed);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(defaultCollapsed);
  const [hasAutoCollapsed, setHasAutoCollapsed] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setStatusCollapsed(defaultCollapsed);
    setThinkingCollapsed(defaultCollapsed);
    setHasAutoCollapsed(false);
  }, [defaultCollapsed, round.roundNumber]);

  useEffect(() => {
    if (isStreaming && !hasAutoCollapsed && round.content && round.content.trim().length > 0) {
      setStatusCollapsed(true);
      setThinkingCollapsed(true);
      setHasAutoCollapsed(true);
    }
  }, [isStreaming, hasAutoCollapsed, round.content]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const markdownComponents = useMemo(() => createMarkdownComponents(), []);

  return (
    <div className="space-y-4">
      {/* Round Divider */}
      <div className="flex items-center gap-4 px-2">
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-zinc-200 dark:via-zinc-800 to-transparent" />
        <span className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-600">
          Round {round.roundNumber}
        </span>
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-zinc-200 dark:via-zinc-800 to-transparent" />
      </div>

      {/* Errors & Retries */}
      {(round.retryAttempts || round.errorFeedback) && (
        <div className="space-y-2">
          {round.retryAttempts?.map((retry, idx) => (
            <RetryIndicator
              key={idx}
              retry={retry}
              isActive={isStreaming && idx === round.retryAttempts!.length - 1}
            />
          ))}
          {round.errorFeedback?.map((feedback, idx) => (
            <ErrorFeedbackDisplay
              key={idx}
              feedback={feedback}
              defaultCollapsed={!isStreaming && (!isLatest || idx < round.errorFeedback!.length - 1)}
            />
          ))}
        </div>
      )}

      {/* Process & Thinking Grid */}
      <div className="grid grid-cols-1 gap-4">
        {/* Agent Process Log */}
        {round.statusMessages.length > 0 && (
          <div className="rounded-[24px] overflow-hidden border border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm">
            <button
              onClick={() => setStatusCollapsed(!statusCollapsed)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400">
                  <Layout className={`w-4 h-4 ${isStreaming ? 'animate-pulse' : ''}`} />
                </div>
                <div className="text-left">
                  <p className="text-xs font-black uppercase tracking-widest text-zinc-800 dark:text-zinc-200">
                    {isStreaming ? 'Execution Progress' : 'Execution Log'}
                  </p>
                  <p className="text-[10px] font-bold text-zinc-500 dark:text-zinc-500 mt-0.5">
                    {round.statusMessages.length} Operational Steps
                  </p>
                </div>
              </div>
              <div className="p-1.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-400 group-hover:text-zinc-600 dark:group-hover:text-zinc-300 transition-colors">
                {statusCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
              </div>
            </button>

            <AnimatePresence>
              {!statusCollapsed && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-5 pb-5 pt-1 space-y-3">
                    {round.statusMessages.map((status, idx) => (
                      <div key={idx} className="flex items-start gap-4 group">
                        <div className="relative flex flex-col items-center mt-1">
                          <div
                            className={`w-2.5 h-2.5 rounded-full z-10 border-2 border-white dark:border-zinc-900 ${
                              status.type === 'error' || status.type === 'tool_error'
                                ? 'bg-rose-500'
                                : status.type === 'done'
                                ? 'bg-emerald-500'
                                : 'bg-indigo-500'
                            } ${isStreaming && idx === round.statusMessages.length - 1 ? 'animate-ping opacity-75' : ''}`}
                          />
                          {idx < round.statusMessages.length - 1 && (
                            <div className="w-0.5 h-6 bg-zinc-100 dark:bg-zinc-800 mt-0.5" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-4">
                            <span
                              className={`text-[13px] font-medium leading-relaxed ${
                                status.type === 'error' || status.type === 'tool_error'
                                  ? 'text-rose-600 dark:text-rose-400'
                                  : status.type === 'tool_call'
                                  ? 'text-indigo-600 dark:text-indigo-400 font-bold'
                                  : 'text-zinc-600 dark:text-zinc-300'
                              }`}
                            >
                              {status.content}
                            </span>
                            {status.duration !== undefined && (
                              <span className="text-[10px] font-black font-mono text-zinc-400 dark:text-zinc-600 tabular-nums">
                                {status.duration.toFixed(2)}s
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Thinking Process */}
        {round.thinking && (
          <div className="rounded-[24px] overflow-hidden border border-purple-100 dark:border-purple-900/30 bg-purple-50/30 dark:bg-purple-950/10">
            <button
              onClick={() => setThinkingCollapsed(!thinkingCollapsed)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-purple-100/50 dark:hover:bg-purple-900/20 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-400">
                  <Brain className={`w-4 h-4 ${isStreaming ? 'animate-pulse' : ''}`} />
                </div>
                <div className="text-left">
                  <p className="text-xs font-black uppercase tracking-widest text-purple-800 dark:text-purple-200">
                    Cognitive Logic
                  </p>
                  <p className="text-[10px] font-bold text-purple-500 dark:text-purple-400 mt-0.5">
                    Internal Chain-of-Thought
                  </p>
                </div>
              </div>
              <div className="p-1.5 rounded-lg bg-purple-100/80 dark:bg-purple-900/50 text-purple-400 group-hover:text-purple-600 dark:group-hover:text-purple-300 transition-colors">
                {thinkingCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
              </div>
            </button>

            <AnimatePresence>
              {!thinkingCollapsed && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-6 pb-5 pt-1">
                    <p className="text-sm leading-relaxed text-purple-900/80 dark:text-purple-100/70 italic font-medium whitespace-pre-wrap">
                      {round.thinking}
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Main Response Content */}
      {round.content && (
        <div className="relative group">
          <div className={`rounded-[32px] rounded-tl-none px-6 py-6 bg-white dark:bg-zinc-900 border ${
            isStreaming 
              ? 'border-indigo-200 dark:border-indigo-800 shadow-xl shadow-indigo-500/5' 
              : 'border-zinc-100 dark:border-zinc-800 shadow-sm'
          }`}>
            <div className="absolute top-0 -left-2 w-4 h-4 text-white dark:text-zinc-900 overflow-hidden">
              <div className="absolute top-0 left-0 w-4 h-4 bg-current -rotate-45 transform origin-top-left rounded-sm border-t border-l border-zinc-100 dark:border-zinc-800" />
            </div>

            {isStreaming && (
              <div className="flex items-center gap-2 mb-4">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" style={{ animationDelay: `${i * 0.2}s` }} />
                  ))}
                </div>
                <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                  Synthesizing Response
                </span>
              </div>
            )}

            <div className="markdown-content prose dark:prose-invert max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {round.content}
              </ReactMarkdown>
            </div>

            {/* Metrics Footer */}
            {round.stats && (
              <div className="mt-6 pt-4 border-t border-zinc-50 dark:border-zinc-800/50 flex flex-wrap items-center justify-end gap-5">
                <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-500" title="Latency (TTFT)">
                  <Zap className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-black font-mono tabular-nums">{round.stats.timeToFirstToken}s</span>
                </div>
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-500" title="Throughput">
                  <PlayCircle className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-black font-mono tabular-nums">{round.stats.tokensPerSecond} t/s</span>
                </div>
                <div className="flex items-center gap-1.5 text-indigo-600 dark:text-indigo-500" title="Volume (In/Out)">
                  <Clock className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-black font-mono tabular-nums">{round.stats.inputTokens} / {round.stats.outputTokens}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
