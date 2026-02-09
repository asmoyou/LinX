import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Loader2, ChevronLeft, ChevronsRight } from 'lucide-react';
import { knowledgeApi } from '@/api/knowledge';
import type { KnowledgeChunk } from '@/api/knowledge';

interface ChunksViewerProps {
  documentId: string;
}

export const ChunksViewer: React.FC<ChunksViewerProps> = ({ documentId }) => {
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
  const pageSize = 20;

  useEffect(() => {
    loadChunks();
  }, [documentId, page]);

  const loadChunks = async () => {
    setIsLoading(true);
    try {
      const data = await knowledgeApi.getChunks(documentId, page, pageSize);
      setChunks(data.chunks);
      setTotal(data.total);
    } catch {
      setChunks([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  };

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
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading chunks...</span>
      </div>
    );
  }

  if (chunks.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 dark:text-gray-400">No chunks available for this document.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        {total} chunks total
      </div>

      <div className="space-y-2">
        {chunks.map((chunk) => {
          const isExpanded = expandedChunks.has(chunk.chunk_index);
          const previewText = chunk.content.slice(0, 120).replace(/\n/g, ' ');

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
                    {chunk.token_count} tokens
                  </span>
                )}
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

                  {/* Keywords */}
                  {chunk.keywords && chunk.keywords.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                        Keywords
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
                        Questions
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
                        Summary
                      </p>
                      <blockquote className="border-l-2 border-indigo-400 pl-3 text-sm text-gray-700 dark:text-gray-300 italic">
                        {chunk.summary}
                      </blockquote>
                    </div>
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
            Page {page} of {totalPages}
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
