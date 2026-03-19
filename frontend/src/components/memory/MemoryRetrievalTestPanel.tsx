import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Search, X } from "lucide-react";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { memoryWorkbenchApi } from "@/api/memoryWorkbench";
import type { MemoryRecord } from "@/types/memory";

const normalizeScore = (score: unknown): number | null => {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return null;
  }
  return Math.max(0, Math.min(1, score));
};

interface MemoryRetrievalTestPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MemoryRetrievalTestPanel: React.FC<
  MemoryRetrievalTestPanelProps
> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(20);
  const [minScore, setMinScore] = useState(0.3);
  const [results, setResults] = useState<MemoryRecord[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  const resultStats = useMemo(() => {
    const entries = (results || [])
      .map((item) => normalizeScore(item.relevanceScore))
      .filter((score): score is number => score !== null);

    if (entries.length === 0) {
      return {
        scoredCount: 0,
        maxScore: null as number | null,
        avgScore: null as number | null,
      };
    }

    const maxScore = Math.max(...entries);
    const avgScore =
      entries.reduce((sum, value) => sum + value, 0) / entries.length;
    return {
      scoredCount: entries.length,
      maxScore,
      avgScore,
    };
  }, [results]);

  const handleSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }

    setIsSearching(true);
    try {
      const data = await memoryWorkbenchApi.listUserMemory({
        query: trimmed,
        limit,
        minScore,
      });
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !isSearching) {
      void handleSearch();
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-4xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
            {t("memory.retrievalTest.title")}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 transition-colors hover:bg-white/20"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        <div className="mb-6 space-y-4">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t("memory.retrievalTest.queryPlaceholder")}
                className="w-full rounded-lg border border-gray-300 bg-white/10 py-2.5 pl-10 pr-4 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-gray-600 dark:text-white"
              />
            </div>
            <button
              onClick={() => void handleSearch()}
              disabled={isSearching || !query.trim()}
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-5 py-2.5 font-medium text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSearching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              {t("memory.retrievalTest.search")}
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="text-sm text-gray-600 dark:text-gray-300">
              <span className="mb-1 block">
                {t("memory.retrievalTest.limitLabel", { limit })}
              </span>
              <input
                type="range"
                min={1}
                max={100}
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
                className="w-full accent-indigo-500"
              />
            </label>

            <label className="text-sm text-gray-600 dark:text-gray-300">
              <span className="mb-1 block">
                {t("memory.retrievalTest.minScoreLabel", {
                  score: minScore.toFixed(2),
                })}
              </span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={minScore}
                onChange={(event) => setMinScore(Number(event.target.value))}
                className="w-full accent-indigo-500"
              />
            </label>
          </div>
        </div>

        {isSearching ? (
          <div className="flex items-center justify-center gap-2 py-10 text-gray-600 dark:text-gray-300">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>{t("memory.retrievalTest.searching")}</span>
          </div>
        ) : results === null ? (
          <div className="py-8 text-center text-gray-500 dark:text-gray-400">
            {t("memory.retrievalTest.emptyHint")}
          </div>
        ) : results.length === 0 ? (
          <div className="py-8 text-center text-gray-500 dark:text-gray-400">
            {t("memory.retrievalTest.noResults")}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {t("memory.retrievalTest.resultSummary", {
                total: results.length,
                scored: resultStats.scoredCount,
                max:
                  resultStats.maxScore !== null
                    ? (resultStats.maxScore * 100).toFixed(1)
                    : "-",
                avg:
                  resultStats.avgScore !== null
                    ? (resultStats.avgScore * 100).toFixed(1)
                    : "-",
              })}
            </div>

            {results.map((item) => {
              const score = normalizeScore(item.relevanceScore);
              return (
                <div
                  key={item.id}
                  className="rounded-xl border border-zinc-200 bg-white/70 p-4 dark:border-zinc-700 dark:bg-zinc-900/50"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-medium text-zinc-900 dark:text-zinc-100">
                        {item.summary || item.content}
                      </p>
                      <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-sm text-zinc-600 dark:text-zinc-300">
                        {item.content}
                      </p>
                    </div>
                    {score !== null && (
                      <span className="rounded-full bg-indigo-500/10 px-2 py-1 text-xs text-indigo-700 dark:text-indigo-300">
                        {(score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ModalPanel>
    </LayoutModal>
  );
};
