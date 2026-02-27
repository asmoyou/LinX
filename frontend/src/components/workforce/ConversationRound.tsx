import React, { useState, useMemo, useEffect } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  Zap,
  PlayCircle,
  Clock,
  Layout,
  FileText,
  FolderOpen,
  Download,
  Loader2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ConversationRound } from '@/types/streaming';
import { RetryIndicator } from './RetryIndicator';
import { ErrorFeedbackDisplay } from './ErrorFeedbackDisplay';
import { createMarkdownComponents } from './CodeBlock';
import { motion, AnimatePresence } from 'framer-motion';

export interface ConversationRoundArtifact {
  path: string;
  confirmed?: boolean;
}

interface ConversationRoundProps {
  round: ConversationRound;
  isLatest?: boolean;
  isStreaming?: boolean;
  defaultCollapsed?: boolean;
  artifacts?: ConversationRoundArtifact[];
  onOpenArtifact?: (path: string) => void;
  onDownloadArtifact?: (path: string) => void;
  downloadingArtifactPath?: string | null;
}

const ConversationRoundComponentBase: React.FC<ConversationRoundProps> = ({
  round,
  isLatest = false,
  isStreaming = false,
  defaultCollapsed = false,
  artifacts = [],
  onOpenArtifact,
  onDownloadArtifact,
  downloadingArtifactPath = null,
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
  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const hasRenderableContent = Boolean(round.content && round.content.trim().length > 0);
  const latestStatusType = round.statusMessages[round.statusMessages.length - 1]?.type;
  const progressHint =
    latestStatusType === 'tool_call'
      ? 'Calling tools and waiting for execution results.'
      : latestStatusType === 'tool_result'
      ? 'Tool completed. Organizing final response.'
      : latestStatusType === 'tool_error'
      ? 'Tool returned an error. Attempting recovery.'
      : 'Thinking and preparing response...';

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

      {isStreaming && !hasRenderableContent && (
        <div className="rounded-[20px] border border-indigo-100 dark:border-indigo-900/30 bg-indigo-50/40 dark:bg-indigo-950/20 px-5 py-4">
          <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <p className="text-[11px] font-black uppercase tracking-widest">Processing</p>
          </div>
          <p className="mt-1.5 text-xs font-medium text-indigo-600/90 dark:text-indigo-300/80">
            {progressHint}
          </p>
        </div>
      )}

      {artifacts.length > 0 && (
        <div className="rounded-[20px] border border-emerald-100 dark:border-emerald-900/40 bg-emerald-50/40 dark:bg-emerald-950/20 px-4 py-4 space-y-2">
          <p className="text-[11px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-300">
            File Outputs
          </p>
          {artifacts.map((artifact) => {
            const fileName = artifact.path.split('/').filter(Boolean).pop() || artifact.path;
            const isDownloading = downloadingArtifactPath === artifact.path;
            return (
              <div
                key={artifact.path}
                className="rounded-xl bg-white/90 dark:bg-zinc-900/70 border border-emerald-100 dark:border-emerald-900/30 px-3 py-2.5 flex items-center gap-3"
              >
                <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-zinc-800 dark:text-zinc-200 truncate">
                    {fileName}
                  </p>
                  <div className="flex items-center gap-2">
                    <p className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">
                      {artifact.path}
                    </p>
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wide ${
                        artifact.confirmed
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-amber-600 dark:text-amber-400'
                      }`}
                    >
                      {artifact.confirmed ? 'saved' : 'pending'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {onOpenArtifact && (
                    <button
                      type="button"
                      onClick={() => onOpenArtifact(artifact.path)}
                      className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-1 rounded-md border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
                    >
                      <FolderOpen className="w-3.5 h-3.5" />
                      Open
                    </button>
                  )}
                  {onDownloadArtifact && (
                    <button
                      type="button"
                      onClick={() => onDownloadArtifact(artifact.path)}
                      disabled={isDownloading}
                      className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-1 rounded-md bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-60 transition-colors"
                    >
                      {isDownloading ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Download className="w-3.5 h-3.5" />
                      )}
                      {isDownloading ? 'Downloading' : 'Download'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Main Response Content */}
      {hasRenderableContent && (
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
              <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
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

const areConversationRoundPropsEqual = (
  prev: ConversationRoundProps,
  next: ConversationRoundProps
): boolean =>
  prev.round === next.round &&
  prev.isLatest === next.isLatest &&
  prev.isStreaming === next.isStreaming &&
  prev.defaultCollapsed === next.defaultCollapsed &&
  prev.downloadingArtifactPath === next.downloadingArtifactPath;

export const ConversationRoundComponent = React.memo(
  ConversationRoundComponentBase,
  areConversationRoundPropsEqual
);

ConversationRoundComponent.displayName = 'ConversationRoundComponent';
