import React, { useState, useMemo, useEffect } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  Zap,
  PlayCircle,
  Clock,
  Layout,
  Download,
  Loader2,
} from 'lucide-react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
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

const WORKSPACE_FILE_LINK_PREFIX = 'workspace-file:';
const WORKSPACE_FILE_HASH_PREFIX = '#workspace-file=';

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function buildPathVariants(path: string): string[] {
  const normalized = String(path || '').trim();
  if (!normalized) return [];

  const variants: string[] = [normalized];
  if (normalized.startsWith('/workspace/')) {
    const relative = normalized.slice('/workspace/'.length);
    if (relative) {
      variants.push(relative);
      variants.push(`./${relative}`);
    }
  }
  return [...new Set(variants)];
}

function buildWorkspaceHref(path: string): string {
  const normalized = String(path || '').trim();
  if (!normalized) return '';

  return normalized
    .split('/')
    .map((segment, index) => (index === 0 ? segment : encodeURIComponent(segment)))
    .join('/');
}

function decodeWorkspacePath(path: string): string {
  try {
    return decodeURIComponent(path);
  } catch {
    return path;
  }
}

function resolveWorkspaceLinkPath(href: string): string | null {
  const raw = String(href || '').trim();
  if (!raw) return null;

  if (raw.startsWith(WORKSPACE_FILE_LINK_PREFIX)) {
    return decodeWorkspacePath(raw.slice(WORKSPACE_FILE_LINK_PREFIX.length));
  }

  if (raw.startsWith(WORKSPACE_FILE_HASH_PREFIX)) {
    return decodeWorkspacePath(raw.slice(WORKSPACE_FILE_HASH_PREFIX.length));
  }

  const normalized = raw.startsWith('workspace/') ? `/${raw}` : raw;
  if (normalized.startsWith('/workspace/')) {
    return decodeWorkspacePath(normalized);
  }

  return null;
}

function workspaceAwareUrlTransform(url: string): string {
  if (url.startsWith(WORKSPACE_FILE_LINK_PREFIX)) {
    return url;
  }
  return defaultUrlTransform(url);
}

function replaceOutsideCodeFences(content: string, pattern: RegExp, replacement: string): string {
  const segments = content.split(/(```[\s\S]*?```)/g);
  return segments
    .map((segment, index) => (index % 2 === 1 ? segment : segment.replace(pattern, replacement)))
    .join('');
}

function enrichContentWithWorkspaceLinks(
  content: string,
  artifacts: ConversationRoundArtifact[]
): string {
  let enriched = String(content || '');
  if (!enriched || artifacts.length === 0) return enriched;

  const candidates = artifacts
    .map((artifact) => String(artifact.path || '').trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);

  for (const artifactPath of candidates) {
    const pathVariants = buildPathVariants(artifactPath).sort((a, b) => b.length - a.length);
    for (const variant of pathVariants) {
      const escapedVariant = escapeRegExp(variant);
      const linkTarget = buildWorkspaceHref(artifactPath);
      const inlineCodePattern = new RegExp(`\\x60(${escapedVariant})\\x60`, 'g');
      const inlineCodeReplacement = `[$1](${linkTarget})`;
      enriched = replaceOutsideCodeFences(enriched, inlineCodePattern, inlineCodeReplacement);

      const pattern = new RegExp(
        `(^|[\\s"'(（【])(${escapedVariant})(?=$|[\\s"')\\]}>，。；;!?])`,
        'g'
      );
      const replacement = `$1[$2](${linkTarget})`;
      enriched = replaceOutsideCodeFences(enriched, pattern, replacement);
    }
  }

  return enriched;
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

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setStatusCollapsed(defaultCollapsed);
    setThinkingCollapsed(defaultCollapsed);
  }, [defaultCollapsed, round.roundNumber]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const markdownComponents = useMemo(() => {
    const baseComponents = createMarkdownComponents() as Record<string, any>;
    return {
      ...baseComponents,
      a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
        const link = String(href || '');
        const artifactPath = resolveWorkspaceLinkPath(link);
        if (!artifactPath) {
          return (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 dark:text-indigo-400 underline decoration-indigo-300 hover:decoration-indigo-500 transition-colors"
            >
              {children}
            </a>
          );
        }
        const isDownloading = downloadingArtifactPath === artifactPath;

        return (
          <span className="inline-flex items-center gap-1 align-middle">
            <button
              type="button"
              onClick={() =>
                onOpenArtifact ? onOpenArtifact(artifactPath) : onDownloadArtifact?.(artifactPath)
              }
              className="inline-flex items-center gap-1 rounded-md border border-emerald-200 dark:border-emerald-800 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors"
            >
              {children}
            </button>
            {onDownloadArtifact && (
              <button
                type="button"
                onClick={() => onDownloadArtifact(artifactPath)}
                disabled={isDownloading}
                className="inline-flex items-center justify-center rounded-md border border-emerald-200 dark:border-emerald-800 p-1 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 disabled:opacity-60 transition-colors"
                title={isDownloading ? 'Downloading' : 'Download'}
              >
                {isDownloading ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Download className="w-3 h-3" />
                )}
              </button>
            )}
          </span>
        );
      },
    };
  }, [downloadingArtifactPath, onDownloadArtifact, onOpenArtifact]);
  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const statusMarkdownComponents = useMemo(() => {
    const baseComponents = markdownComponents as Record<string, any>;
    return {
      ...baseComponents,
      p: ({ children }: { children?: React.ReactNode }) => (
        <span className="whitespace-pre-wrap break-words">{children}</span>
      ),
    };
  }, [markdownComponents]);
  const hasRenderableContent = Boolean(round.content && round.content.trim().length > 0);
  const enrichedContent = useMemo(
    () => enrichContentWithWorkspaceLinks(round.content, artifacts),
    [artifacts, round.content]
  );
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
                            <div
                              className={`text-[13px] font-medium leading-relaxed ${
                                status.type === 'error' || status.type === 'tool_error'
                                  ? 'text-rose-600 dark:text-rose-400'
                                  : status.type === 'tool_call'
                                  ? 'text-indigo-600 dark:text-indigo-400 font-bold'
                                  : 'text-zinc-600 dark:text-zinc-300'
                              }`}
                            >
                              <ReactMarkdown
                                remarkPlugins={remarkPlugins}
                                components={statusMarkdownComponents}
                                urlTransform={workspaceAwareUrlTransform}
                              >
                                {status.content}
                              </ReactMarkdown>
                            </div>
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
              <ReactMarkdown
                remarkPlugins={remarkPlugins}
                components={markdownComponents}
                urlTransform={workspaceAwareUrlTransform}
              >
                {enrichedContent}
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
