import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Brain,
  User,
  Building,
  Clock,
  Tag,
  Share2,
  TrendingUp,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { GlassPanel } from "@/components/GlassPanel";
import type { Memory, MemoryFact } from "@/types/memory";

const parseFacts = (memory: Memory): MemoryFact[] => {
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
  memory: Memory;
  onClick: (memory: Memory) => void;
  showRelevance?: boolean;
  onReindex?: (memory: Memory) => void;
  isReindexing?: boolean;
}

export const MemoryCard: React.FC<MemoryCardProps> = ({
  memory,
  onClick,
  showRelevance = false,
  onReindex,
  isReindexing = false,
}) => {
  const { t } = useTranslation();
  const memoryFacts = useMemo(() => parseFacts(memory), [memory]);
  const structuredLines = useMemo(
    () => parseStructuredContentLines(memory.content),
    [memory.content],
  );
  const factPreview = memoryFacts.slice(0, 2);
  const structuredPreview = structuredLines.slice(0, 2);

  const getTypeIcon = (type: Memory["type"]) => {
    switch (type) {
      case "agent":
        return <Brain className="w-5 h-5 text-blue-500" />;
      case "company":
        return <Building className="w-5 h-5 text-green-500" />;
      case "user_context":
        return <User className="w-5 h-5 text-purple-500" />;
    }
  };

  const getTypeLabel = (type: Memory["type"]) => {
    switch (type) {
      case "agent":
        return t("memory.tabs.agent");
      case "company":
        return t("memory.tabs.company");
      case "user_context":
        return t("memory.tabs.userContext");
    }
  };

  const getTypeColor = (type: Memory["type"]) => {
    switch (type) {
      case "agent":
        return "bg-blue-500/20 text-blue-700 dark:text-blue-400";
      case "company":
        return "bg-green-500/20 text-green-700 dark:text-green-400";
      case "user_context":
        return "bg-purple-500/20 text-purple-700 dark:text-purple-400";
    }
  };

  const indexStatus = String(memory.indexStatus || "").toLowerCase();
  const statusKey = (
    indexStatus === "synced" ||
    indexStatus === "pending" ||
    indexStatus === "failed"
      ? indexStatus
      : "unknown"
  ) as "synced" | "pending" | "failed" | "unknown";

  const getIndexStatusBadge = () => {
    switch (statusKey) {
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
      case "failed":
        return {
          icon: <AlertTriangle className="w-3 h-3" />,
          label: t("memory.indexStatus.failed"),
          className: "bg-rose-500/20 text-rose-700 dark:text-rose-300",
        };
      default:
        return {
          icon: <Clock className="w-3 h-3" />,
          label: t("memory.indexStatus.unknown"),
          className: "bg-gray-500/20 text-gray-700 dark:text-gray-300",
        };
    }
  };

  const indexBadge = getIndexStatusBadge();
  const relevanceScore =
    typeof memory.relevanceScore === "number" &&
    Number.isFinite(memory.relevanceScore)
      ? Math.max(0, Math.min(1, memory.relevanceScore))
      : null;
  const sharedTargetNames = (
    memory.sharedWithNames && memory.sharedWithNames.length > 0
      ? memory.sharedWithNames
      : memory.sharedWith || []
  ).slice(0, 3);
  const publishMode = String(memory.metadata?.publish_mode || "")
    .trim()
    .toLowerCase();
  const hasPromotionBacklink = Boolean(memory.metadata?.last_promoted_memory_id);
  const rawVisibility = String(memory.metadata?.visibility || "")
    .trim()
    .toLowerCase();
  const visibility = (() => {
    if (memory.type === "user_context") {
      return rawVisibility === "explicit" || rawVisibility === "private"
        ? rawVisibility
        : "private";
    }
    if (rawVisibility) {
      return rawVisibility;
    }
    if (memory.type === "agent") {
      return "private";
    }
    return "department_tree";
  })();
  const hasPolicyScope = [
    "explicit",
    "department",
    "department_tree",
    "public",
  ].includes(visibility);
  const isPublished =
    publishMode === "promote" ||
    hasPromotionBacklink ||
    (memory.type === "agent" &&
      ["explicit", "department", "department_tree", "public", "account"].includes(visibility));
  const sharingBadgeText = isPublished
    ? t("memory.card.published")
    : t("memory.card.shared");
  const scopeSuffix = (() => {
    switch (visibility) {
      case "private":
        return t("memory.share.scope.private");
      case "account":
        return t("memory.share.scope.account");
      case "department":
        return t("memory.share.scope.department");
      case "department_tree":
        return t("memory.share.scope.departmentTree");
      case "public":
        return t("memory.share.scope.public");
      case "explicit":
        return t("memory.share.scope.explicit");
      default:
        return "";
    }
  })();
  const isPolicyShared = Boolean(memory.isShared) || hasPolicyScope || isPublished;
  const policyHintText =
    sharedTargetNames.length > 0
      ? t("memory.card.sharedWithNames", {
          names: sharedTargetNames.join(", "),
        })
      : scopeSuffix
        ? t("memory.card.scopeLabel", { scope: scopeSuffix })
        : isPolicyShared
          ? t("memory.card.policyApplied")
          : "";

  return (
    <div onClick={() => onClick(memory)} className="cursor-pointer">
      <GlassPanel className="hover:scale-[1.02] transition-transform duration-200">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            {getTypeIcon(memory.type)}
            <span
              className={`text-xs px-2 py-1 rounded-full ${getTypeColor(memory.type)}`}
            >
              {getTypeLabel(memory.type)}
            </span>
            <span
              className={`text-xs px-2 py-1 rounded-full flex items-center gap-1 ${indexBadge.className}`}
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
        </div>

        {/* Content */}
        <div className="mb-3">
          {memory.summary && (
            <p className="text-sm font-medium text-gray-800 dark:text-white mb-2">
              {memory.summary}
            </p>
          )}
          {factPreview.length > 0 ? (
            <div className="space-y-2">
              {factPreview.map((fact, index) => (
                <div key={`${fact.key}-${index}`} className="rounded-lg bg-white/10 p-2">
                  <p className="text-[11px] text-indigo-600 dark:text-indigo-300 font-mono break-all">
                    {fact.key}
                  </p>
                  <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {fact.value}
                  </p>
                </div>
              ))}
              {memoryFacts.length > factPreview.length && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t("memory.card.moreFacts", {
                    count: memoryFacts.length - factPreview.length,
                  })}
                </p>
              )}
            </div>
          ) : structuredPreview.length > 0 ? (
            <div className="space-y-2">
              {structuredPreview.map((line, index) => (
                <div key={`${line.key}-${index}`} className="rounded-lg bg-white/10 p-2">
                  <p className="text-[11px] text-indigo-600 dark:text-indigo-300 font-mono break-all">
                    {line.key}
                  </p>
                  <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {line.value}
                  </p>
                </div>
              ))}
              {structuredLines.length > structuredPreview.length && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t("memory.card.moreFacts", {
                    count: structuredLines.length - structuredPreview.length,
                  })}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-4 whitespace-pre-wrap">
              {memory.content}
            </p>
          )}
        </div>

        {/* Tags */}
        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {memory.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="flex items-center gap-1 text-xs px-2 py-0.5 bg-white/20 rounded-full text-gray-700 dark:text-gray-300"
              >
                <Tag className="w-3 h-3" />
                {tag}
              </span>
            ))}
            {memory.tags.length > 3 && (
              <span className="text-xs px-2 py-0.5 bg-white/20 rounded-full text-gray-700 dark:text-gray-300">
                +{memory.tags.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Metadata */}
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(memory.createdAt).toLocaleDateString()}
            </div>
            {memory.agentName && (
              <span className="truncate max-w-[120px]" title={memory.agentName}>
                {memory.agentName}
              </span>
            )}
          </div>
          {isPolicyShared && (
            <div className="flex items-center gap-1 text-indigo-500">
              <Share2 className="w-3 h-3" />
              <span>{sharingBadgeText}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between mt-2">
          {policyHintText ? (
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate pr-2">
              {policyHintText}
            </p>
          ) : (
            <span />
          )}
          {onReindex && (
            <button
              onClick={(event) => {
                event.stopPropagation();
                onReindex(memory);
              }}
              disabled={isReindexing}
              className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-white/15 hover:bg-white/25 text-gray-700 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isReindexing ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <RefreshCw className="w-3 h-3" />
              )}
              {t("memory.card.rebuildIndex")}
            </button>
          )}
        </div>
      </GlassPanel>
    </div>
  );
};
