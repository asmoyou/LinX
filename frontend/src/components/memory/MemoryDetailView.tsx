import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  Brain,
  User,
  Clock,
  Tag,
  Share2,
  TrendingUp,
  Link as LinkIcon,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  Loader2,
  Pencil,
  Save,
} from "lucide-react";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import type { MemoryRecord, MemoryFact, MemoryIndexInfo } from "@/types/memory";

const parseFacts = (memory: MemoryRecord): MemoryFact[] => {
  const raw = memory.metadata?.facts;
  if (!Array.isArray(raw)) {
    return [];
  }
  const parsed = raw
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

  const sopTitleValue = parsed.find(
    (entry) => entry.key === "interaction.sop.title",
  )?.value;
  const shouldDropSopTopic = Boolean(
    sopTitleValue &&
    parsed.some(
      (entry) =>
        entry.key === "interaction.sop.topic" && entry.value === sopTitleValue,
    ),
  );

  const uniqueFacts: MemoryFact[] = [];
  const seenPairs = new Set<string>();
  for (const entry of parsed) {
    if (
      shouldDropSopTopic &&
      entry.key === "interaction.sop.topic" &&
      entry.value === sopTitleValue
    ) {
      continue;
    }
    const signature = `${entry.key}\0${entry.value}`;
    if (seenPairs.has(signature)) {
      continue;
    }
    seenPairs.add(signature);
    uniqueFacts.push(entry);
  }
  return uniqueFacts;
};

const getMetadataText = (
  memory: MemoryRecord,
  ...candidates: string[]
): string | undefined => {
  const metadata = memory.metadata;
  if (!metadata || typeof metadata !== "object") {
    return undefined;
  }
  for (const key of candidates) {
    const raw = metadata[key];
    if (typeof raw === "string" && raw.trim()) {
      return raw.trim();
    }
  }
  return undefined;
};

const getMetadataNumber = (
  memory: MemoryRecord,
  ...candidates: string[]
): number | undefined => {
  const metadata = memory.metadata;
  if (!metadata || typeof metadata !== "object") {
    return undefined;
  }
  for (const key of candidates) {
    const raw = metadata[key];
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return raw;
    }
    if (typeof raw === "string" && raw.trim()) {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return undefined;
};

const formatFactScore = (value: unknown): string | null => {
  const numeric =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number(value)
        : Number.NaN;
  if (!Number.isFinite(numeric)) {
    return null;
  }
  const bounded = Math.max(0, Math.min(1, numeric));
  return `${(bounded * 100).toFixed(0)}%`;
};

interface MemoryDetailViewProps {
  memory: MemoryRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onShare?: (memory: MemoryRecord) => void;
  onDelete?: (memory: MemoryRecord) => void;
  onReindex?: (memory: MemoryRecord) => void;
  onInspectIndex?: (memory: MemoryRecord) => void;
  onUpdate?: (
    memory: MemoryRecord,
    updates: {
      content: string;
      summary?: string;
      tags: string[];
    },
    options: {
      reindexAfterSave: boolean;
    },
  ) => Promise<void> | void;
  onReviewCandidate?: (
    memory: MemoryRecord,
    action: "publish" | "reject" | "revise",
  ) => Promise<void> | void;
  isUpdating?: boolean;
  isReviewingCandidate?: boolean;
  isReindexing?: boolean;
  isInspectingIndex?: boolean;
  indexInfo?: MemoryIndexInfo | null;
}

export const MemoryDetailView: React.FC<MemoryDetailViewProps> = ({
  memory,
  isOpen,
  onClose,
  onShare,
  onDelete,
  onReindex,
  onInspectIndex,
  onUpdate,
  onReviewCandidate,
  isUpdating = false,
  isReviewingCandidate = false,
  isReindexing = false,
  isInspectingIndex = false,
  indexInfo = null,
}) => {
  const { t } = useTranslation();
  const relevanceScore =
    typeof memory?.relevanceScore === "number" &&
    Number.isFinite(memory.relevanceScore)
      ? Math.max(0, Math.min(1, memory.relevanceScore))
      : null;
  const effectiveSummary =
    memory?.summary && memory.summary.trim() !== (memory.content || "").trim()
      ? memory.summary
      : undefined;
  const [isEditing, setIsEditing] = useState(false);
  const [editSummary, setEditSummary] = useState(() => memory?.summary || "");
  const [editContent, setEditContent] = useState(() => memory?.content || "");
  const [editTags, setEditTags] = useState(() =>
    (memory?.tags || []).join(", "),
  );
  const [reindexAfterSave, setReindexAfterSave] = useState(true);

  if (!isOpen || !memory) return null;
  const extractedFacts = parseFacts(memory);
  const taskId = getMetadataText(memory, "taskId", "task_id");
  const goalId = getMetadataText(memory, "goalId", "goal_id");
  const documentId = getMetadataText(memory, "documentId", "document_id");
  const memoryTier = getMetadataText(memory, "memoryTier", "memory_tier");
  const importanceLevel = getMetadataText(
    memory,
    "importanceLevel",
    "importance_level",
  );
  const importanceScore = getMetadataNumber(
    memory,
    "importanceScore",
    "importance_score",
  );
  const metadataPresent =
    !!memory.metadata &&
    typeof memory.metadata === "object" &&
    Object.keys(memory.metadata).length > 0;

  const handleEditToggle = () => {
    if (isEditing) {
      setIsEditing(false);
      return;
    }
    setEditSummary(effectiveSummary || "");
    setEditContent(memory.content || "");
    setEditTags((memory.tags || []).join(", "));
    setReindexAfterSave(true);
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!onUpdate) return;
    const normalizedContent = editContent.trim();
    if (!normalizedContent) return;

    const tags = editTags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);

    try {
      await onUpdate(
        memory,
        {
          content: normalizedContent,
          summary: editSummary.trim() || undefined,
          tags,
        },
        {
          reindexAfterSave,
        },
      );
      setIsEditing(false);
    } catch {
      // Error is handled by parent page toast.
    }
  };

  const getTypeIcon = (type: MemoryRecord["type"]) => {
    switch (type) {
      case "skill_proposal":
        return <Brain className="w-6 h-6 text-blue-500" />;
      case "user_memory":
        return <User className="w-6 h-6 text-purple-500" />;
    }
  };

  const getTypeLabel = (type: MemoryRecord["type"]) => {
    switch (type) {
      case "skill_proposal":
        return t("memory.tabs.skillProposal", { defaultValue: "技能提案" });
      case "user_memory":
        return memory.userName
          ? t("memory.card.userMemoryOwner", {
              defaultValue: "{{name}} 的记忆",
              name: memory.userName,
            })
          : t("memory.tabs.userMemory", { defaultValue: "用户记忆" });
    }
  };

  const rawVisibility = String(memory.metadata?.visibility || "")
    .trim()
    .toLowerCase();
  const signalType = String(memory.metadata?.signal_type || "")
    .trim()
    .toLowerCase();
  const reviewStatus = String(memory.metadata?.review_status || "")
    .trim()
    .toLowerCase();
  const isAgentCandidate =
    signalType === "skill_proposal" || memory.type === "skill_proposal";
  const candidateStatusKey =
    reviewStatus === "published" || reviewStatus === "rejected"
      ? reviewStatus
      : "pending";
  const candidateStatusView = (() => {
    if (!isAgentCandidate) {
      return null;
    }
    if (candidateStatusKey === "published") {
      return {
        label: t("memory.card.reviewPublished", { defaultValue: "已审批" }),
        hint: t("memory.card.reviewPublishedHint", {
          defaultValue: "该技能提案已审批，会参与技能经验注入。",
        }),
        className: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
      };
    }
    if (candidateStatusKey === "rejected") {
      return {
        label: t("memory.card.reviewRejected", { defaultValue: "已拒绝" }),
        hint: t("memory.card.reviewRejectedHint", {
          defaultValue: "该技能提案已拒绝，不会参与技能经验注入。",
        }),
        className: "bg-rose-500/20 text-rose-700 dark:text-rose-300",
      };
    }
    return {
      label: t("memory.card.reviewPending", { defaultValue: "待审批" }),
      hint: t("memory.card.reviewPendingHint", {
        defaultValue: "该技能提案待审批，当前不会参与技能经验注入。",
      }),
      className: "bg-amber-500/20 text-amber-700 dark:text-amber-300",
    };
  })();
  const visibility = (() => {
    if (memory.type === "user_memory") {
      return rawVisibility === "explicit" || rawVisibility === "private"
        ? rawVisibility
        : "private";
    }
    if (rawVisibility) {
      return rawVisibility;
    }
    return "private";
  })();
  const hasPolicyScope = [
    "explicit",
    "department",
    "department_tree",
    "public",
  ].includes(visibility);
  const publishMode = String(memory.metadata?.publish_mode || "")
    .trim()
    .toLowerCase();
  const hasPromotionBacklink = Boolean(
    memory.metadata?.last_promoted_memory_id,
  );
  const candidatePublished =
    isAgentCandidate && candidateStatusKey === "published";
  const isPublished = isAgentCandidate
    ? candidatePublished
    : publishMode === "promote" ||
      hasPromotionBacklink ||
      [
        "explicit",
        "department",
        "department_tree",
        "public",
        "account",
      ].includes(visibility);
  const sharingScopeLabel = (() => {
    switch (visibility) {
      case "private":
        return t("memory.share.scope.private");
      case "explicit":
        return t("memory.share.scope.explicit");
      case "department":
        return t("memory.share.scope.department");
      case "department_tree":
        return t("memory.share.scope.departmentTree");
      case "account":
        return t("memory.share.scope.account");
      case "public":
        return t("memory.share.scope.public");
      default:
        return t("memory.share.scope.unknown");
    }
  })();
  const sharingTitle = isAgentCandidate
    ? t("memory.share.reviewPublishTitle", { defaultValue: "审批并发布" })
    : memory.type === "skill_proposal"
      ? t("memory.share.publishTitle")
      : t("memory.share.title");
  const isPolicyShared = isAgentCandidate
    ? candidatePublished
    : Boolean(memory.isShared) || hasPolicyScope || isPublished;
  const canRenderCandidateReviewActions =
    isAgentCandidate && typeof onReviewCandidate === "function";

  const formatTimestamp = (value?: string | null) => {
    if (!value) return "-";

    const normalized = value.trim();
    if (!normalized) return "-";

    let parsed = new Date(normalized);
    if (Number.isNaN(parsed.getTime()) && /^-?\d+(\.\d+)?$/.test(normalized)) {
      const numeric = Number(normalized);
      if (Number.isFinite(numeric)) {
        const magnitude = Math.abs(Math.trunc(numeric));
        const milliseconds =
          magnitude >= 100_000_000_000
            ? numeric
            : magnitude >= 1_000_000_000
              ? numeric * 1000
              : Number.NaN;

        if (Number.isFinite(milliseconds)) {
          parsed = new Date(milliseconds);
        }
      }
    }

    if (Number.isNaN(parsed.getTime())) {
      return normalized;
    }
    return parsed.toLocaleString();
  };

  const indexStatus = String(memory.indexStatus || "").toLowerCase();
  const indexStatusKey = (
    indexStatus === "synced" ||
    indexStatus === "pending" ||
    indexStatus === "failed"
      ? indexStatus
      : "unknown"
  ) as "synced" | "pending" | "failed" | "unknown";

  const indexStatusView = (() => {
    switch (indexStatusKey) {
      case "synced":
        return {
          icon: <CheckCircle2 className="w-4 h-4 text-emerald-500" />,
          text: t("memory.indexStatus.synced"),
        };
      case "pending":
        return {
          icon: <Loader2 className="w-4 h-4 animate-spin text-amber-500" />,
          text: t("memory.indexStatus.pending"),
        };
      case "failed":
        return {
          icon: <AlertTriangle className="w-4 h-4 text-rose-500" />,
          text: t("memory.indexStatus.failed"),
        };
      default:
        return {
          icon: <Clock className="w-4 h-4 text-gray-500" />,
          text: t("memory.indexStatus.unknown"),
        };
    }
  })();

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-3xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            {getTypeIcon(memory.type)}
            <div className="flex items-center gap-2">
              <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                {getTypeLabel(memory.type)}
              </h2>
              {candidateStatusView && (
                <span
                  className={`text-xs px-2 py-1 rounded-full ${candidateStatusView.className}`}
                >
                  {candidateStatusView.label}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {onUpdate && (
              <button
                onClick={handleEditToggle}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                title={t("memory.detail.edit", "Edit")}
                disabled={isUpdating}
              >
                {isUpdating ? (
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                ) : (
                  <Pencil className="w-5 h-5 text-indigo-500" />
                )}
              </button>
            )}
            {onReindex && (
              <button
                onClick={() => onReindex(memory)}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                title={t("memory.card.rebuildIndex")}
                disabled={isReindexing}
              >
                {isReindexing ? (
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                ) : (
                  <RefreshCw className="w-5 h-5 text-indigo-500" />
                )}
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => {
                  if (window.confirm(t("memory.detail.deleteConfirm"))) {
                    onDelete(memory);
                  }
                }}
                className="p-2 hover:bg-red-500/20 rounded-lg transition-colors"
                title={t("common.delete")}
              >
                <Trash2 className="w-5 h-5 text-red-500" />
              </button>
            )}
            {onShare && (
              <button
                onClick={() => onShare(memory)}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                title={sharingTitle}
              >
                <Share2 className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
            >
              <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
            </button>
          </div>
        </div>

        <div className="mb-4 p-3 bg-white/10 rounded-lg">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              {indexStatusView.icon}
              <span>
                {t("memory.detail.indexStatus")}: {indexStatusView.text}
              </span>
            </div>
            {onInspectIndex && (
              <button
                onClick={() => onInspectIndex(memory)}
                disabled={isInspectingIndex}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-white/15 hover:bg-white/25 text-gray-700 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isInspectingIndex ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <LinkIcon className="w-3 h-3" />
                )}
                {t("memory.detail.viewIndexRecord")}
              </button>
            )}
          </div>
          {memory.indexError && (
            <p className="mt-2 text-xs text-rose-500 break-words">
              {memory.indexError}
            </p>
          )}
          {(isInspectingIndex || indexInfo) && (
            <div className="mt-3 p-3 bg-black/10 rounded-lg text-xs text-gray-700 dark:text-gray-300 space-y-2">
              {isInspectingIndex && !indexInfo && (
                <p>{t("memory.detail.indexLoading")}</p>
              )}
              {indexInfo && (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <p>
                      {t("memory.detail.indexCollection")}:{" "}
                      {indexInfo.collection || "-"}
                    </p>
                    <p>
                      {t("memory.detail.indexMilvusId")}:{" "}
                      {indexInfo.milvusId ?? "-"}
                    </p>
                    <p>
                      {t("memory.detail.indexExists")}:{" "}
                      {indexInfo.existsInMilvus
                        ? t("memory.detail.indexExistsYes")
                        : t("memory.detail.indexExistsNo")}
                    </p>
                    <p>
                      {t("memory.detail.indexUpdated")}:{" "}
                      {indexInfo.vectorUpdatedAt
                        ? formatTimestamp(indexInfo.vectorUpdatedAt)
                        : "-"}
                    </p>
                    <p>
                      {t("memory.detail.indexTimestamp")}:{" "}
                      {indexInfo.indexedTimestamp
                        ? formatTimestamp(indexInfo.indexedTimestamp)
                        : "-"}
                    </p>
                    <p>
                      {t("memory.detail.embeddingDim")}:{" "}
                      {indexInfo.embeddingDimension ?? "-"}
                    </p>
                  </div>
                  {indexInfo.embeddingPreview &&
                    indexInfo.embeddingPreview.length > 0 && (
                      <p className="break-all">
                        {t("memory.detail.embeddingPreview")}: [
                        {indexInfo.embeddingPreview.join(", ")}]
                      </p>
                    )}
                  {indexInfo.milvusError && (
                    <p className="text-rose-500 break-words">
                      {t("memory.detail.indexUnavailable")}:{" "}
                      {indexInfo.milvusError}
                    </p>
                  )}
                  {indexInfo.indexedContent && (
                    <div>
                      <p className="mb-1 text-gray-500 dark:text-gray-400">
                        {t("memory.detail.indexPayload")}
                      </p>
                      <div className="max-h-28 overflow-y-auto whitespace-pre-wrap break-words bg-white/10 rounded p-2">
                        {indexInfo.indexedContent}
                      </div>
                    </div>
                  )}
                  {indexInfo.indexedMetadata && (
                    <details>
                      <summary className="cursor-pointer text-gray-500 dark:text-gray-400">
                        {t("memory.detail.indexMetadata")}
                      </summary>
                      <pre className="mt-2 whitespace-pre-wrap break-all bg-white/10 rounded p-2">
                        {JSON.stringify(indexInfo.indexedMetadata, null, 2)}
                      </pre>
                    </details>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Relevance Score */}
        {relevanceScore !== null && (
          <div className="mb-6 p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-indigo-500" />
                <span className="text-sm font-medium text-gray-800 dark:text-white">
                  {t("memory.detail.relevanceScore")}
                </span>
              </div>
              <span className="text-2xl font-bold text-indigo-500">
                {(relevanceScore * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-2 w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-500"
                style={{ width: `${relevanceScore * 100}%` }}
              />
            </div>
          </div>
        )}

        {isEditing ? (
          <div className="mb-6 p-4 bg-white/10 rounded-lg space-y-4">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
              {t("memory.detail.editTitle", "Edit Memory")}
            </h3>

            <label className="block text-sm text-gray-700 dark:text-gray-300">
              <span className="block mb-1">{t("memory.detail.summary")}</span>
              <input
                value={editSummary}
                onChange={(event) => setEditSummary(event.target.value)}
                className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white"
                placeholder={t(
                  "memory.detail.summaryPlaceholder",
                  "Optional summary",
                )}
              />
            </label>

            <label className="block text-sm text-gray-700 dark:text-gray-300">
              <span className="block mb-1">{t("memory.detail.content")}</span>
              <textarea
                value={editContent}
                onChange={(event) => setEditContent(event.target.value)}
                rows={7}
                className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white resize-none"
                placeholder={t("memory.detail.content")}
              />
            </label>

            <label className="block text-sm text-gray-700 dark:text-gray-300">
              <span className="block mb-1">{t("memory.detail.tags")}</span>
              <input
                value={editTags}
                onChange={(event) => setEditTags(event.target.value)}
                className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white"
                placeholder={t(
                  "memory.detail.tagsPlaceholder",
                  "tag1, tag2, tag3",
                )}
              />
            </label>

            <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              <input
                type="checkbox"
                checked={reindexAfterSave}
                onChange={(event) => setReindexAfterSave(event.target.checked)}
                className="rounded"
              />
              {t(
                "memory.detail.reindexAfterSave",
                "Rebuild vector index after saving",
              )}
            </label>

            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setIsEditing(false)}
                disabled={isUpdating}
                className="px-4 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
              >
                {t("common.cancel", "Cancel")}
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={isUpdating || !editContent.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isUpdating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                {reindexAfterSave
                  ? t("memory.detail.saveAndReindex", "Save & Rebuild Index")
                  : t("common.save", "Save")}
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Extracted Facts */}
            {extractedFacts.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
                    {t("memory.detail.extractedFacts")}
                  </h3>
                  <span className="text-xs px-2 py-1 rounded-full bg-indigo-500/15 text-indigo-700 dark:text-indigo-300">
                    {t("memory.detail.factCount", {
                      count: extractedFacts.length,
                    })}
                  </span>
                </div>
                <div className="max-h-72 overflow-y-auto pr-1 space-y-2">
                  {extractedFacts.map((fact, index) => {
                    const confidence = formatFactScore(fact.confidence);
                    const importance = formatFactScore(fact.importance);
                    return (
                      <div
                        key={`${fact.key}-${index}`}
                        className="rounded-lg bg-white/10 p-3 border border-white/10"
                      >
                        <div className="flex items-center justify-between gap-3 mb-1">
                          <code className="text-xs font-medium text-indigo-600 dark:text-indigo-300 break-all">
                            {fact.key}
                          </code>
                          <div className="flex items-center gap-2 text-[11px] text-gray-600 dark:text-gray-400 whitespace-nowrap">
                            {importance && (
                              <span>
                                {t("memory.detail.factImportance")}:{" "}
                                {importance}
                              </span>
                            )}
                            {confidence && (
                              <span>
                                {t("memory.detail.factConfidence")}:{" "}
                                {confidence}
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words">
                          {fact.value}
                        </p>
                        {fact.source && (
                          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {t("memory.detail.factSource")}: {fact.source}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Summary */}
            {effectiveSummary && (
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
                  {t("memory.detail.summary")}
                </h3>
                <p className="text-gray-700 dark:text-gray-300 bg-white/10 p-4 rounded-lg">
                  {effectiveSummary}
                </p>
              </div>
            )}

            {/* Content */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
                {t("memory.detail.content")}
              </h3>
              <div className="max-h-80 overflow-y-auto text-gray-700 dark:text-gray-300 bg-white/10 p-4 rounded-lg whitespace-pre-wrap break-words">
                {memory.content}
              </div>
            </div>
          </>
        )}

        {/* Metadata Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div className="p-4 bg-white/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-5 h-5 text-blue-500" />
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {t("memory.detail.created")}
              </span>
            </div>
            <p className="text-gray-800 dark:text-white font-medium">
              {formatTimestamp(memory.createdAt)}
            </p>
          </div>

          {memory.updatedAt && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-5 h-5 text-green-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {t("memory.detail.updated")}
                </span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {formatTimestamp(memory.updatedAt)}
              </p>
            </div>
          )}

          {memory.agentName && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-5 h-5 text-blue-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {t("memory.detail.agent")}
                </span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {memory.agentName}
              </p>
            </div>
          )}

          {memory.userName && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <User className="w-5 h-5 text-purple-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {t("memory.detail.user")}
                </span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {memory.userName}
              </p>
            </div>
          )}

          {memoryTier && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-5 h-5 text-indigo-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {t("memory.detail.tier")}
                </span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium capitalize">
                {memoryTier}
              </p>
            </div>
          )}

          {(importanceLevel || importanceScore !== undefined) && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-5 h-5 text-amber-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {t("memory.detail.importance")}
                </span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {importanceLevel ? importanceLevel : "-"}
                {importanceScore !== undefined
                  ? ` (${(importanceScore * 100).toFixed(0)}%)`
                  : ""}
              </p>
            </div>
          )}
        </div>

        {/* Tags */}
        {!isEditing && memory.tags.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">
              {t("memory.detail.tags")}
            </h3>
            <div className="flex flex-wrap gap-2">
              {memory.tags.map((tag) => (
                <span
                  key={tag}
                  className="flex items-center gap-1 px-3 py-1 bg-white/20 rounded-full text-sm text-gray-700 dark:text-gray-300"
                >
                  <Tag className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Related Items */}
        {metadataPresent && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">
              {t("memory.detail.relatedItems")}
            </h3>
            <div className="space-y-2">
              {taskId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {t("memory.detail.task")}: {taskId}
                  </span>
                </div>
              )}
              {goalId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {t("memory.detail.goal")}: {goalId}
                  </span>
                </div>
              )}
              {documentId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {t("memory.detail.document")}: {documentId}
                  </span>
                </div>
              )}
            </div>

            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400">
                {t("memory.detail.rawMetadata")}
              </summary>
              <pre className="mt-2 whitespace-pre-wrap break-all bg-white/10 rounded p-3 text-xs text-gray-700 dark:text-gray-300">
                {JSON.stringify(memory.metadata, null, 2)}
              </pre>
            </details>
          </div>
        )}

        {/* Visibility / Sharing Status */}
        <div className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
          {candidateStatusView && (
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
              {candidateStatusView.hint}
            </p>
          )}
          {canRenderCandidateReviewActions && (
            <div className="mb-3 flex flex-wrap gap-2">
              {candidateStatusKey !== "published" && (
                <button
                  onClick={() => onReviewCandidate?.(memory, "publish")}
                  disabled={isReviewingCandidate}
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-500 text-white px-3 py-1.5 text-xs font-medium hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isReviewingCandidate
                    ? t("common.loading")
                    : t("memory.share.reviewApprove", {
                        defaultValue: "审批发布",
                      })}
                </button>
              )}
              {candidateStatusKey === "pending" && (
                <button
                  onClick={() => onReviewCandidate?.(memory, "reject")}
                  disabled={isReviewingCandidate}
                  className="inline-flex items-center gap-1 rounded-md bg-rose-500 text-white px-3 py-1.5 text-xs font-medium hover:bg-rose-600 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isReviewingCandidate
                    ? t("common.loading")
                    : t("memory.share.reviewReject", {
                        defaultValue: "拒绝候选",
                      })}
                </button>
              )}
            </div>
          )}
          {!isPolicyShared && !isPublished ? (
            <div className="flex items-center gap-2 mb-2">
              <ShieldAlert className="w-5 h-5 text-indigo-500" />
              <span className="text-sm font-medium text-gray-800 dark:text-white">
                {t("memory.detail.visibilityScope")}
              </span>
            </div>
          ) : null}
          {(isPolicyShared || isPublished) && (
            <div className="flex items-center gap-2 mb-2">
              <Share2 className="w-5 h-5 text-indigo-500" />
              <span className="text-sm font-medium text-gray-800 dark:text-white">
                {isPublished
                  ? t("memory.detail.publishedMemory")
                  : t("memory.detail.sharedMemory")}
              </span>
            </div>
          )}
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t("memory.share.scopeLabel")}: {sharingScopeLabel}
          </p>
          {memory.metadata?.expires_at && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t("memory.share.expiresAt")}:{" "}
              {formatTimestamp(String(memory.metadata.expires_at))}
            </p>
          )}
          {memory.metadata?.share_reason && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t("memory.share.reason")}: {String(memory.metadata.share_reason)}
            </p>
          )}
          {memory.sharedWith && memory.sharedWith.length > 0 && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t("memory.detail.sharedWith")}:{" "}
              {(memory.sharedWithNames && memory.sharedWithNames.length > 0
                ? memory.sharedWithNames
                : memory.sharedWith
              ).join(", ")}
            </p>
          )}
        </div>
      </ModalPanel>
    </LayoutModal>
  );
};
