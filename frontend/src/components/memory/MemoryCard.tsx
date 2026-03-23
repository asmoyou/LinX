import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  Clock,
  Database,
  Layers,
  Loader2,
  Tag,
  TrendingUp,
  User,
} from "lucide-react";
import { GlassPanel } from "@/components/GlassPanel";
import type { MemoryFact, MemoryRecord } from "@/types/memory";

const parseFacts = (memory: MemoryRecord): MemoryFact[] => {
  const raw = memory.metadata?.facts;
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw
    .filter((entry): entry is MemoryFact => {
      return (
        !!entry &&
        typeof entry === "object" &&
        typeof (entry as MemoryFact).key === "string" &&
        typeof (entry as MemoryFact).value === "string" &&
        Boolean((entry as MemoryFact).key.trim()) &&
        Boolean((entry as MemoryFact).value.trim())
      );
    })
    .map((entry) => ({
      ...entry,
      key: entry.key.trim(),
      value: entry.value.trim(),
    }));
};

const parseStructuredContentLines = (
  content: string,
): Array<{ key: string; value: string }> => {
  return String(content || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const separatorIndex = line.indexOf("=");
      if (separatorIndex <= 0) {
        return null;
      }
      const key = line.slice(0, separatorIndex).trim();
      const value = line.slice(separatorIndex + 1).trim();
      if (!key || !value) {
        return null;
      }
      return { key, value };
    })
    .filter((item): item is { key: string; value: string } => item !== null);
};

interface MemoryCardProps {
  memory: MemoryRecord;
  onClick: (memory: MemoryRecord) => void;
  showRelevance?: boolean;
}

export const MemoryCard: React.FC<MemoryCardProps> = ({
  memory,
  onClick,
  showRelevance = false,
}) => {
  const { t } = useTranslation();
  const memoryFacts = useMemo(() => parseFacts(memory), [memory]);
  const structuredLines = useMemo(
    () => parseStructuredContentLines(memory.content),
    [memory.content],
  );
  const factPreview = memoryFacts.slice(0, 2);
  const structuredPreview = structuredLines.slice(0, 2);
  const relevanceScore =
    typeof memory.relevanceScore === "number" &&
    Number.isFinite(memory.relevanceScore)
      ? Math.max(0, Math.min(1, memory.relevanceScore))
      : null;
  const indexStatus = String(memory.indexStatus || "").toLowerCase();

  const indexBadge = (() => {
    switch (indexStatus) {
      case "synced":
        return {
          icon: <CheckCircle2 className="w-3 h-3" />,
          label: t("memory.indexStatus.synced"),
          className: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
        };
      case "pending":
        return {
          icon: <Loader2 className="w-3 h-3 animate-spin" />,
          label: t("memory.indexStatus.pending"),
          className: "bg-amber-500/20 text-amber-700 dark:text-amber-300",
        };
      default:
        return {
          icon: <Clock className="w-3 h-3" />,
          label: t("memory.indexStatus.unknown"),
          className: "bg-zinc-500/20 text-zinc-700 dark:text-zinc-300",
        };
    }
  })();

  const memorySource = String(memory.metadata?.memory_source || "").toLowerCase();
  const recordType = String(memory.metadata?.record_type || "").toLowerCase();

  const sourceBadge = (() => {
    if (memorySource === "user_memory_view" || recordType === "user_profile") {
      return {
        icon: <Layers className="w-3 h-3" />,
        label: t("memory.source.profile", { defaultValue: "Profile" }),
        className: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
      };
    }
    if (recordType === "episode") {
      return {
        icon: <Layers className="w-3 h-3" />,
        label: t("memory.source.episode", { defaultValue: "Episode" }),
        className: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300",
      };
    }
    return {
      icon: <Database className="w-3 h-3" />,
      label: t("memory.source.entry", { defaultValue: "Entry" }),
      className: "bg-orange-500/15 text-orange-700 dark:text-orange-300",
    };
  })();

  return (
    <div onClick={() => onClick(memory)} className="cursor-pointer">
      <GlassPanel className="hover:scale-[1.02] transition-transform duration-200">
        <div className="mb-3 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-blue-500/15 px-2.5 py-1 text-xs text-blue-700 dark:text-blue-300 flex items-center gap-1.5 font-medium">
              <User className="w-3.5 h-3.5" />
              {memory.userName ||
                t("memory.card.unknownUser", { defaultValue: "Unknown" })}
            </span>
            <span
              className={`rounded-full px-2 py-1 text-xs flex items-center gap-1 ${sourceBadge.className}`}
            >
              {sourceBadge.icon}
              {sourceBadge.label}
            </span>
            <span
              className={`rounded-full px-2 py-1 text-xs flex items-center gap-1 ${indexBadge.className}`}
            >
              {indexBadge.icon}
              {indexBadge.label}
            </span>
          </div>
          {showRelevance && relevanceScore !== null && (
            <div className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
              <TrendingUp className="w-3 h-3" />
              {(relevanceScore * 100).toFixed(0)}%
            </div>
          )}
          <span className="text-xs text-zinc-400 dark:text-zinc-500 whitespace-nowrap">
            {(() => {
              try {
                const d = new Date(memory.updatedAt || memory.createdAt);
                return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
              } catch {
                return "";
              }
            })()}
          </span>
        </div>

        <div className="mb-3">
          {memory.summary &&
            memory.summary.trim() !== memory.content.trim() && (
              <p className="mb-2 text-sm font-medium text-gray-800 dark:text-white">
                {memory.summary}
              </p>
            )}
          {factPreview.length > 0 ? (
            <div className="space-y-2">
              {factPreview.map((fact, index) => (
                <div
                  key={`${fact.key}-${index}`}
                  className="rounded-lg bg-white/10 p-2"
                >
                  <p className="text-[11px] text-indigo-600 dark:text-indigo-300 font-mono break-all">
                    {fact.key}
                  </p>
                  <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {fact.value}
                  </p>
                </div>
              ))}
            </div>
          ) : structuredPreview.length > 0 ? (
            <div className="space-y-2">
              {structuredPreview.map((line, index) => (
                <div
                  key={`${line.key}-${index}`}
                  className="rounded-lg bg-white/10 p-2"
                >
                  <p className="text-[11px] text-indigo-600 dark:text-indigo-300 font-mono break-all">
                    {line.key}
                  </p>
                  <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {line.value}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-4 whitespace-pre-wrap">
              {memory.content}
            </p>
          )}
        </div>

        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {memory.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-full bg-zinc-500/10 px-2 py-1 text-xs text-zinc-600 dark:text-zinc-300"
              >
                <Tag className="w-3 h-3" />
                {tag}
              </span>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
};
