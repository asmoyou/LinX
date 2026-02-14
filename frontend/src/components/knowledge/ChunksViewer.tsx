import React, { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  ChevronLeft,
  ChevronsRight,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { knowledgeApi } from "@/api/knowledge";
import type { KnowledgeChunk } from "@/api/knowledge";

type EmbeddingStatus = "indexed" | "missing" | "pending" | "failed" | "unknown";

const EMBEDDING_STATUS_STYLE: Record<EmbeddingStatus, string> = {
  indexed: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  missing: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  pending: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  failed: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  unknown: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
};

interface ChunksViewerProps {
  documentId: string;
  documentStatus?: "uploading" | "processing" | "completed" | "failed";
  expectedChunkCount?: number;
}

export const ChunksViewer: React.FC<ChunksViewerProps> = ({
  documentId,
  documentStatus,
  expectedChunkCount,
}) => {
  const { t } = useTranslation();
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
  const [retryCount, setRetryCount] = useState(0);
  const [embeddingConfig, setEmbeddingConfig] = useState<{
    provider?: string;
    model?: string;
    dimension?: number;
  } | null>(null);
  const [vectorLookupError, setVectorLookupError] = useState<string | null>(
    null,
  );
  const pageSize = 20;
  const maxRetries = 20;

  useEffect(() => {
    setRetryCount(0);
  }, [documentId, page]);

  const loadChunks = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await knowledgeApi.getChunks(documentId, page, pageSize);
      setChunks(data.chunks);
      setTotal(data.total);
      setEmbeddingConfig(data.embedding_config ?? null);
      setVectorLookupError(data.vector_index_lookup?.error ?? null);
    } catch {
      setChunks([]);
      setTotal(0);
      setEmbeddingConfig(null);
      setVectorLookupError(null);
    } finally {
      setIsLoading(false);
    }
  }, [documentId, page, pageSize]);

  useEffect(() => {
    loadChunks();
  }, [loadChunks]);

  const shouldRetryEmptyResult =
    chunks.length === 0 &&
    retryCount < maxRetries &&
    (documentStatus === "uploading" ||
      documentStatus === "processing" ||
      (documentStatus === "completed" && (expectedChunkCount || 0) > 0));

  useEffect(() => {
    if (isLoading || !shouldRetryEmptyResult) return;

    const timer = window.setTimeout(() => {
      setRetryCount((prev) => prev + 1);
      loadChunks();
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [isLoading, shouldRetryEmptyResult, loadChunks]);

  const toggleChunk = (index: number) => {
    setExpandedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const totalPages = Math.ceil(total / pageSize);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">
          {t("document.chunks.loading")}
        </span>
      </div>
    );
  }

  if (chunks.length === 0) {
    return (
      <div className="text-center py-12">
        {shouldRetryEmptyResult ? (
          <div className="flex items-center justify-center gap-2 text-gray-500 dark:text-gray-400">
            <Loader2 className="w-4 h-4 animate-spin" />
            <p>{t("document.chunks.preparing")}</p>
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400">
            {t("document.chunks.empty")}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        {t("document.chunks.total", { count: total })}
      </div>
      {embeddingConfig && (
        <div className="mb-3 text-xs text-gray-600 dark:text-gray-300">
          {t("document.chunks.embedding")}: {embeddingConfig.provider || "-"} /{" "}
          {embeddingConfig.model || "-"}
          {embeddingConfig.dimension ? ` (${embeddingConfig.dimension}d)` : ""}
        </div>
      )}
      {vectorLookupError && (
        <div className="mb-3 text-xs text-amber-700 dark:text-amber-300 bg-amber-500/10 rounded-md px-3 py-2">
          {t("document.chunks.vectorLookupError")}: {vectorLookupError}
        </div>
      )}

      <div className="space-y-2">
        {chunks.map((chunk) => {
          const isExpanded = expandedChunks.has(chunk.chunk_index);
          const previewText = chunk.content.slice(0, 120).replace(/\n/g, " ");
          const enrichmentApplied =
            chunk.enrichment?.applied ??
            chunk.enrichment_applied ??
            Boolean(
              (chunk.keywords?.length || 0) > 0 ||
              (chunk.questions?.length || 0) > 0 ||
              (chunk.summary || "").trim(),
            );
          const embeddingStatus: EmbeddingStatus =
            (chunk.embedding?.status as EmbeddingStatus | undefined) ||
            "unknown";
          const embeddingStatusLabel = t(
            `document.chunks.embeddingStatus.${embeddingStatus}`,
            { defaultValue: embeddingStatus },
          );

          return (
            <div
              key={chunk.chunk_id}
              className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Chunk Header */}
              <button
                onClick={() => toggleChunk(chunk.chunk_index)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/10 transition-colors text-left"
              >
                {isExpanded ? (
                  <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
                )}
                <span className="text-sm font-medium text-indigo-500 dark:text-indigo-400 flex-shrink-0">
                  #{chunk.chunk_index}
                </span>
                {chunk.token_count != null && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                    {t("document.chunks.tokenCount", {
                      count: chunk.token_count,
                    })}
                  </span>
                )}
                <span
                  className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                    enrichmentApplied
                      ? "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300"
                      : "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300"
                  }`}
                >
                  {enrichmentApplied
                    ? t("document.chunks.enriched")
                    : t("document.chunks.raw")}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${EMBEDDING_STATUS_STYLE[embeddingStatus]}`}
                >
                  {t("document.chunks.vector")}: {embeddingStatusLabel}
                </span>
                {!isExpanded && (
                  <span className="text-sm text-gray-600 dark:text-gray-400 truncate">
                    {previewText}...
                  </span>
                )}
              </button>

              {/* Expanded Content */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3">
                  {/* Content */}
                  <pre className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg font-mono max-h-[400px] overflow-auto">
                    {chunk.content}
                  </pre>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                        {t("document.chunks.enrichmentStatus")}
                      </p>
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        {enrichmentApplied
                          ? t("document.chunks.applied")
                          : t("document.chunks.notApplied")}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {t("document.chunks.keywords")}:{" "}
                        {chunk.enrichment?.keywords_count ??
                          chunk.keywords?.length ??
                          0}
                        {"  "}| {t("document.chunks.questions")}:{" "}
                        {chunk.enrichment?.questions_count ??
                          chunk.questions?.length ??
                          0}
                        {"  "}| {t("document.chunks.summary")}:{" "}
                        {(chunk.enrichment?.has_summary ??
                        Boolean((chunk.summary || "").trim()))
                          ? t("document.chunks.yes")
                          : t("document.chunks.no")}
                      </p>
                    </div>
                    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                        {t("document.chunks.embeddingStatusTitle")}
                      </p>
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        {embeddingStatus}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {chunk.embedding?.provider ||
                          embeddingConfig?.provider ||
                          "-"}{" "}
                        /{" "}
                        {chunk.embedding?.model ||
                          embeddingConfig?.model ||
                          "-"}
                        {chunk.embedding?.dimension ||
                        embeddingConfig?.dimension
                          ? ` (${chunk.embedding?.dimension || embeddingConfig?.dimension}d)`
                          : ""}
                      </p>
                    </div>
                  </div>

                  {/* Keywords */}
                  {chunk.keywords && chunk.keywords.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                        {t("document.chunks.keywords")}
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {chunk.keywords.map((kw, i) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 rounded-full text-xs"
                          >
                            {kw}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Questions */}
                  {chunk.questions && chunk.questions.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                        {t("document.chunks.questions")}
                      </p>
                      <ul className="list-disc list-inside space-y-1">
                        {chunk.questions.map((q, i) => (
                          <li
                            key={i}
                            className="text-sm text-gray-700 dark:text-gray-300"
                          >
                            {q}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Summary */}
                  {chunk.summary && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                        {t("document.chunks.summary")}
                      </p>
                      <blockquote className="border-l-2 border-indigo-400 pl-3 text-sm text-gray-700 dark:text-gray-300 italic">
                        {chunk.summary}
                      </blockquote>
                    </div>
                  )}

                  {chunk.chunk_metadata &&
                    typeof chunk.chunk_metadata === "object" &&
                    Object.keys(chunk.chunk_metadata).length > 0 && (
                      <details className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                        <summary className="text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer">
                          {t("document.chunks.metadata")}
                        </summary>
                        <pre className="mt-2 whitespace-pre-wrap text-xs text-gray-700 dark:text-gray-300 max-h-[240px] overflow-auto">
                          {JSON.stringify(chunk.chunk_metadata, null, 2)}
                        </pre>
                      </details>
                    )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="w-4 h-4 text-gray-700 dark:text-gray-300" />
          </button>
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {t("document.chunks.pageIndicator", { page, totalPages })}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronsRight className="w-4 h-4 text-gray-700 dark:text-gray-300" />
          </button>
        </div>
      )}
    </div>
  );
};
