import React, { useMemo } from "react";
import { Bot, Download, FileText, FolderOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTranslation } from "react-i18next";

import { createMarkdownComponents } from "@/components/workforce/CodeBlock";
import type { ScheduleCreatedEvent } from "@/types/schedule";

import { PersistentConversationScheduleCard } from "./PersistentConversationScheduleCard";
import type { PersistentConversationArtifactItem } from "./persistentConversationHelpers";

interface PersistentConversationAssistantMessageProps {
  content: string;
  artifactItems: PersistentConversationArtifactItem[];
  scheduleItems: ScheduleCreatedEvent[];
  errorText?: string | null;
  onOpenArtifact?: (path: string) => void;
  onDownloadArtifact?: (path: string) => void;
  downloadingArtifactPath?: string | null;
}

export const PersistentConversationAssistantMessage: React.FC<
  PersistentConversationAssistantMessageProps
> = ({
  content,
  artifactItems,
  scheduleItems,
  errorText = null,
  onOpenArtifact,
  onDownloadArtifact,
  downloadingArtifactPath = null,
}) => {
  const { t } = useTranslation();
  const markdownComponents = useMemo(() => createMarkdownComponents(), []);
  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const trimmedContent = String(content || "").trim();
  const hasRenderableBody =
    Boolean(trimmedContent) ||
    Boolean(errorText) ||
    artifactItems.length > 0 ||
    scheduleItems.length > 0;

  if (!hasRenderableBody) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-[28px] rounded-tl-[14px] border border-zinc-200 bg-zinc-50 px-6 py-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950/40">
        <div className="mb-4 flex items-center gap-2 text-[11px] font-medium tracking-[0.12em] text-zinc-400 dark:text-zinc-500">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300">
            <Bot className="h-4 w-4" />
          </span>
          {t("agent.agentResponse", "代理响应")}
        </div>

        {trimmedContent ? (
          <div className="markdown-content text-[15px] leading-7 text-zinc-700 dark:text-zinc-200">
            <ReactMarkdown
              remarkPlugins={remarkPlugins}
              components={markdownComponents}
            >
              {trimmedContent}
            </ReactMarkdown>
          </div>
        ) : null}

        {errorText ? (
          <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900/40 dark:bg-red-950/30">
            <p className="text-xs font-semibold tracking-[0.12em] text-red-700 dark:text-red-300">
              {t("agent.persistentResult.partialError", "执行未完整完成")}
            </p>
            <p className="mt-1 text-sm text-red-700 dark:text-red-200">
              {errorText}
            </p>
          </div>
        ) : null}
      </div>

      {artifactItems.length > 0 ? (
        <div className="space-y-2">
          <p className="px-1 text-[11px] font-semibold leading-5 tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
            {t("agent.persistentResult.files", "结果文件")}
          </p>
          <div className="space-y-2">
            {artifactItems.map((artifact) => {
              const isDownloading = downloadingArtifactPath === artifact.path;
              return (
                <div
                  key={artifact.path}
                  className="flex items-center justify-between gap-3 rounded-[22px] border border-zinc-200 bg-white px-4 py-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="rounded-2xl bg-emerald-100 p-2.5 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-300">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {artifact.name}
                      </p>
                      <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                        {artifact.path}
                      </p>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    {onOpenArtifact ? (
                      <button
                        type="button"
                        onClick={() => onOpenArtifact(artifact.path)}
                        className="inline-flex items-center gap-1 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/80 dark:text-zinc-200 dark:hover:bg-zinc-800"
                      >
                        <FolderOpen className="h-3.5 w-3.5" />
                        {t(
                          "agent.persistentResult.openInWorkspace",
                          "在工作区打开",
                        )}
                      </button>
                    ) : null}
                    {onDownloadArtifact ? (
                      <button
                        type="button"
                        onClick={() => onDownloadArtifact(artifact.path)}
                        disabled={isDownloading}
                        className="inline-flex items-center gap-1 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-700 disabled:opacity-60"
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t("agent.persistentResult.download", "下载")}
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {scheduleItems.length > 0 ? (
        <div className="space-y-2">
          <p className="px-1 text-[11px] font-semibold leading-5 tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
            {t("agent.persistentResult.schedules", "定时任务")}
          </p>
          <div className="space-y-2">
            {scheduleItems.map((event) => (
              <PersistentConversationScheduleCard
                key={event.schedule_id}
                event={event}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};
