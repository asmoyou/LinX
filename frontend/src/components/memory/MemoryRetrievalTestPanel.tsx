import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Search, X } from "lucide-react";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { memoriesApi } from "@/api/memories";
import type { Memory, MemoryType } from "@/types/memory";

type RetrievalScope = MemoryType | "all";

interface MemoryRetrievalTestPanelProps {
  isOpen: boolean;
  onClose: () => void;
  activeType?: MemoryType | null;
}

const normalizeScore = (score: unknown): number | null => {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return null;
  }
  return Math.max(0, Math.min(1, score));
};

export const MemoryRetrievalTestPanel: React.FC<MemoryRetrievalTestPanelProps> = ({
  isOpen,
  onClose,
  activeType,
}) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<RetrievalScope>("all");
  const [limit, setLimit] = useState(20);
  const [minScore, setMinScore] = useState(0.3);
  const [results, setResults] = useState<Memory[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setScope(activeType || "all");
    setResults(null);
  }, [activeType, isOpen]);

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
    const avgScore = entries.reduce((sum, value) => sum + value, 0) / entries.length;
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
      const data = await memoriesApi.search({
        query: trimmed,
        type: scope === "all" ? undefined : scope,
        limit,
        min_score: minScore,
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
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
            {t("memory.retrievalTest.title")}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        <div className="space-y-4 mb-6">
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t("memory.retrievalTest.queryPlaceholder")}
                className="w-full pl-10 pr-4 py-2.5 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <button
              onClick={() => void handleSearch()}
              disabled={isSearching || !query.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {isSearching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              {t("memory.retrievalTest.search")}
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-300">
              <span className="block mb-1">{t("memory.retrievalTest.scopeLabel")}</span>
              <select
                value={scope}
                onChange={(event) => setScope(event.target.value as RetrievalScope)}
                className="w-full px-3 py-2 rounded-lg bg-white/10 border border-gray-300 dark:border-gray-600"
              >
                <option value="all">{t("memory.retrievalTest.scopeAll")}</option>
                <option value="agent">{t("memory.retrievalTest.scopeAgent")}</option>
                <option value="company">{t("memory.retrievalTest.scopeCompany")}</option>
                <option value="user_context">
                  {t("memory.retrievalTest.scopeUserContext")}
                </option>
              </select>
            </label>

            <label className="text-sm text-gray-600 dark:text-gray-300">
              <span className="block mb-1">
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
              <span className="block mb-1">
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
          <div className="py-10 flex items-center justify-center text-gray-600 dark:text-gray-300 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>{t("memory.retrievalTest.searching")}</span>
          </div>
        ) : results === null ? (
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            {t("memory.retrievalTest.emptyHint")}
          </div>
        ) : results.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            {t("memory.retrievalTest.noResults")}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {t("memory.retrievalTest.resultSummary", {
                total: results.length,
                scored: resultStats.scoredCount,
                max: resultStats.maxScore !== null ? (resultStats.maxScore * 100).toFixed(1) : "-",
                avg: resultStats.avgScore !== null ? (resultStats.avgScore * 100).toFixed(1) : "-",
              })}
            </div>
            {results.map((item) => {
              const score = normalizeScore(item.relevanceScore);
              return (
                <div
                  key={item.id}
                  className="p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 bg-white/40 dark:bg-zinc-900/40"
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                      {item.summary || item.content.slice(0, 64)}
                    </div>
                    <div className="text-xs px-2 py-1 rounded-full bg-indigo-500/15 text-indigo-700 dark:text-indigo-300">
                      {score !== null
                        ? t("memory.retrievalTest.scoreBadge", {
                            score: (score * 100).toFixed(1),
                          })
                        : t("memory.retrievalTest.noScore")}
                    </div>
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                    {t("memory.retrievalTest.typeLabel")}:{" "}
                    {item.type === "agent"
                      ? t("memory.tabs.agent")
                      : item.type === "company"
                        ? t("memory.tabs.company")
                        : t("memory.tabs.userContext")}
                  </div>
                  <p className="text-sm text-zinc-700 dark:text-zinc-300 line-clamp-3">
                    {item.content}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </ModalPanel>
    </LayoutModal>
  );
};
