import React, { useState } from 'react';
import { X, Search, Loader2 } from 'lucide-react';
import { ModalPanel } from '@/components/ModalPanel';
import { knowledgeApi } from '@/api/knowledge';
import type { SearchKnowledgeResponse } from '@/api/knowledge';

interface RetrievalTestPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RetrievalTestPanel: React.FC<RetrievalTestPanelProps> = ({ isOpen, onClose }) => {
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(10);
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchKnowledgeResponse | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setIsSearching(true);
    try {
      const data = await knowledgeApi.search({ query: query.trim(), limit });
      setResults(data);
    } catch {
      setResults(null);
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSearching) {
      handleSearch();
    }
  };

  const highlightQuery = (text: string, q: string) => {
    if (!q.trim()) return text;
    const terms = q.trim().split(/\s+/).filter(Boolean);
    const pattern = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    const regex = new RegExp(`(${pattern})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark key={i} className="bg-yellow-300 dark:bg-yellow-600 text-inherit rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  const getMethodBadge = (method?: string) => {
    if (!method) return null;
    const colors: Record<string, string> = {
      vector: 'bg-purple-500/20 text-purple-700 dark:text-purple-300',
      bm25: 'bg-green-500/20 text-green-700 dark:text-green-300',
      hybrid: 'bg-blue-500/20 text-blue-700 dark:text-blue-300',
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full ${colors[method] || 'bg-gray-500/20 text-gray-700 dark:text-gray-300'}`}>
        {method}
      </span>
    );
  };

  if (!isOpen) return null;

  const maxScore = results?.results?.length
    ? Math.max(...results.results.map((r) => r.similarity_score))
    : 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
      style={{ marginLeft: 'var(--sidebar-width, 0px)' }}
    >
      <ModalPanel className="w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
            Retrieval Test
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        {/* Search Input */}
        <div className="space-y-4 mb-6">
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Enter a query to test retrieval..."
                className="w-full pl-10 pr-4 py-2.5 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={isSearching || !query.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {isSearching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              Search
            </button>
          </div>

          {/* Limit slider */}
          <div className="flex items-center gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              Results: {limit}
            </label>
            <input
              type="range"
              min={1}
              max={50}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="flex-1 accent-indigo-500"
            />
          </div>
        </div>

        {/* Results */}
        {results && (
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {results.total} result{results.total !== 1 ? 's' : ''} for &quot;{results.query}&quot;
            </p>

            {results.results.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                No matching results found. Try a different query.
              </div>
            ) : (
              <div className="space-y-3">
                {results.results.map((result, idx) => {
                  const scorePercent = maxScore > 0
                    ? (result.similarity_score / maxScore) * 100
                    : 0;

                  return (
                    <div
                      key={`${result.document_id}-${result.chunk_index}-${idx}`}
                      className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                    >
                      {/* Score bar + header */}
                      <div className="flex items-center gap-3 mb-2">
                        <div className="flex-1">
                          <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-indigo-500 rounded-full transition-all"
                              style={{ width: `${scorePercent}%` }}
                            />
                          </div>
                        </div>
                        <span className="text-xs font-mono text-gray-500 dark:text-gray-400 w-16 text-right">
                          {result.similarity_score.toFixed(4)}
                        </span>
                      </div>

                      {/* Title + chunk info */}
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        {result.document_title && (
                          <span className="text-sm font-medium text-gray-800 dark:text-white">
                            {result.document_title}
                          </span>
                        )}
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          Chunk #{result.chunk_index}
                        </span>
                        {getMethodBadge(result.search_method)}
                      </div>

                      {/* Content with highlighted query */}
                      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed mb-2">
                        {highlightQuery(result.content.slice(0, 500), query)}
                        {result.content.length > 500 && '...'}
                      </p>

                      {/* Keywords */}
                      {result.keywords && result.keywords.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-1">
                          {result.keywords.map((kw, i) => (
                            <span
                              key={i}
                              className="px-2 py-0.5 bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 rounded-full text-xs"
                            >
                              {kw}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Summary */}
                      {result.summary && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 italic mt-1">
                          {result.summary}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {!results && !isSearching && (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            Enter a query above to test knowledge base retrieval.
          </div>
        )}
      </ModalPanel>
    </div>
  );
};
