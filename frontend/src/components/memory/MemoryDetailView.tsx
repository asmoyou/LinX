import React from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  Brain,
  User,
  Building,
  Clock,
  Tag,
  Share2,
  TrendingUp,
  Link as LinkIcon,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { ModalPanel } from "@/components/ModalPanel";
import type { Memory, MemoryIndexInfo } from "@/types/memory";

interface MemoryDetailViewProps {
  memory: Memory | null;
  isOpen: boolean;
  onClose: () => void;
  onShare?: (memory: Memory) => void;
  onDelete?: (memory: Memory) => void;
  onReindex?: (memory: Memory) => void;
  onInspectIndex?: (memory: Memory) => void;
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
  isReindexing = false,
  isInspectingIndex = false,
  indexInfo = null,
}) => {
  const { t } = useTranslation();

  if (!isOpen || !memory) return null;

  const getTypeIcon = (type: Memory["type"]) => {
    switch (type) {
      case "agent":
        return <Brain className="w-6 h-6 text-blue-500" />;
      case "company":
        return <Building className="w-6 h-6 text-green-500" />;
      case "user_context":
        return <User className="w-6 h-6 text-purple-500" />;
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
      style={{ marginLeft: "var(--sidebar-width, 0px)" }}
    >
      <ModalPanel className="w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            {getTypeIcon(memory.type)}
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
              {getTypeLabel(memory.type)}
            </h2>
          </div>
          <div className="flex items-center gap-2">
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
                title={t("memory.share.title")}
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
                        ? new Date(indexInfo.vectorUpdatedAt).toLocaleString()
                        : "-"}
                    </p>
                    <p>
                      {t("memory.detail.indexTimestamp")}:{" "}
                      {indexInfo.indexedTimestamp
                        ? new Date(indexInfo.indexedTimestamp).toLocaleString()
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
                        {t("memory.detail.embeddingPreview")}:{" "}
                        [{indexInfo.embeddingPreview.join(", ")}]
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
        {memory.relevanceScore !== undefined && (
          <div className="mb-6 p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-indigo-500" />
                <span className="text-sm font-medium text-gray-800 dark:text-white">
                  {t("memory.detail.relevanceScore")}
                </span>
              </div>
              <span className="text-2xl font-bold text-indigo-500">
                {(memory.relevanceScore * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-2 w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-500"
                style={{ width: `${memory.relevanceScore * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Summary */}
        {memory.summary && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
              {t("memory.detail.summary")}
            </h3>
            <p className="text-gray-700 dark:text-gray-300 bg-white/10 p-4 rounded-lg">
              {memory.summary}
            </p>
          </div>
        )}

        {/* Content */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
            {t("memory.detail.content")}
          </h3>
          <div className="text-gray-700 dark:text-gray-300 bg-white/10 p-4 rounded-lg whitespace-pre-wrap">
            {memory.content}
          </div>
        </div>

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
              {new Date(memory.createdAt).toLocaleString()}
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
                {new Date(memory.updatedAt).toLocaleString()}
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
        </div>

        {/* Tags */}
        {memory.tags.length > 0 && (
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
        {memory.metadata && Object.keys(memory.metadata).length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">
              {t("memory.detail.relatedItems")}
            </h3>
            <div className="space-y-2">
              {memory.metadata.taskId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {t("memory.detail.task")}: {memory.metadata.taskId}
                  </span>
                </div>
              )}
              {memory.metadata.goalId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {t("memory.detail.goal")}: {memory.metadata.goalId}
                  </span>
                </div>
              )}
              {memory.metadata.documentId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {t("memory.detail.document")}: {memory.metadata.documentId}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Sharing Status */}
        {memory.isShared && (
          <div className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Share2 className="w-5 h-5 text-indigo-500" />
              <span className="text-sm font-medium text-gray-800 dark:text-white">
                {t("memory.detail.sharedMemory")}
              </span>
            </div>
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
        )}
      </ModalPanel>
    </div>
  );
};
