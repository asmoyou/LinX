import React from "react";
import {
  Brain,
  Database,
  Hammer,
  Loader2,
  Paperclip,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { PersistentProcessDescriptor } from "./persistentConversationHelpers";

interface PersistentConversationProcessLineProps {
  descriptor: PersistentProcessDescriptor | null;
  isVisible: boolean;
}

function buildProcessPresentation(
  descriptor: PersistentProcessDescriptor,
  t: (key: string, fallback?: string) => string,
): {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  accentColorClass: string;
  iconShellClass: string;
} {
  switch (descriptor.kind) {
    case "memory":
      return {
        icon: Brain,
        title: t("agent.persistentProcess.memory", "抽取记忆"),
        accentColorClass: "text-emerald-700 dark:text-emerald-200",
        iconShellClass:
          "bg-emerald-100/90 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200",
      };
    case "knowledge":
      return {
        icon: Database,
        title: t("agent.persistentProcess.knowledge", "检索知识库"),
        accentColorClass: "text-sky-700 dark:text-sky-200",
        iconShellClass:
          "bg-sky-100/90 text-sky-700 dark:bg-sky-950/50 dark:text-sky-200",
      };
    case "context":
      return {
        icon: Sparkles,
        title: t("agent.persistentProcess.context", "整理上下文"),
        accentColorClass: "text-amber-700 dark:text-amber-200",
        iconShellClass:
          "bg-amber-100/90 text-amber-700 dark:bg-amber-950/50 dark:text-amber-200",
      };
    case "attachments":
      return {
        icon: Paperclip,
        title: t("agent.persistentProcess.attachments", "准备附件"),
        accentColorClass: "text-zinc-700 dark:text-zinc-200",
        iconShellClass:
          "bg-zinc-100/90 text-zinc-700 dark:bg-zinc-900/70 dark:text-zinc-200",
      };
    case "tool":
      return {
        icon: Hammer,
        title: t("agent.persistentProcess.tool", "调用工具"),
        accentColorClass: "text-violet-700 dark:text-violet-200",
        iconShellClass:
          "bg-violet-100/90 text-violet-700 dark:bg-violet-950/50 dark:text-violet-200",
      };
    case "finalizing":
      return {
        icon: WandSparkles,
        title: t("agent.persistentProcess.finalizing", "整理结果中…"),
        accentColorClass: "text-emerald-700 dark:text-emerald-200",
        iconShellClass:
          "bg-emerald-100/90 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200",
      };
    case "recovering":
      return {
        icon: Loader2,
        title: t("agent.persistentProcess.recovering", "继续处理中…"),
        accentColorClass: "text-rose-700 dark:text-rose-200",
        iconShellClass:
          "bg-rose-100/90 text-rose-700 dark:bg-rose-950/50 dark:text-rose-200",
      };
    default:
      return {
        icon: Sparkles,
        title: t("agent.persistentProcess.thinking", "思考中…"),
        accentColorClass: "text-emerald-700 dark:text-emerald-200",
        iconShellClass:
          "bg-emerald-100/90 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200",
      };
  }
}

export const PersistentConversationProcessLine: React.FC<
  PersistentConversationProcessLineProps
> = ({ descriptor, isVisible }) => {
  const { t } = useTranslation();
  const translate = (key: string, fallback?: string) => t(key, fallback ?? key);

  if (!isVisible || !descriptor) {
    return null;
  }

  const presentation = buildProcessPresentation(descriptor, translate);
  const Icon = presentation.icon;

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-3xl rounded-[24px] border border-zinc-200 bg-white px-4 py-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/90">
        <div className="flex items-center gap-3 overflow-hidden">
          <div
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${presentation.iconShellClass}`}
          >
            <Icon
              className={`h-4 w-4 ${
                descriptor.kind === "recovering" ? "animate-spin" : ""
              }`}
            />
          </div>

          <div className="min-w-0 flex-1 overflow-hidden">
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span
                className={`shrink-0 text-sm font-semibold ${presentation.accentColorClass}`}
              >
                {presentation.title}
              </span>
              {descriptor.accent ? (
                <span className="shrink-0 rounded-full border border-zinc-200/80 bg-white/85 px-2.5 py-1 text-[11px] font-medium text-zinc-600 dark:border-zinc-700/80 dark:bg-zinc-900/80 dark:text-zinc-300">
                  {descriptor.accent}
                </span>
              ) : null}
              {descriptor.detail ? (
                <span className="min-w-0 truncate text-sm text-zinc-500 dark:text-zinc-400">
                  {descriptor.detail}
                </span>
              ) : (
                <span className="min-w-0 truncate text-sm text-zinc-400 dark:text-zinc-500">
                  {t("agent.persistentProcess.waitingHint", "正在处理中")}
                </span>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5 pl-1">
            {[0, 1, 2].map((dotIndex) => (
              <span
                key={dotIndex}
                className={`h-1.5 w-1.5 rounded-full bg-emerald-500/80 dark:bg-emerald-400/80 ${
                  dotIndex === 1 ? "animate-pulse" : ""
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
