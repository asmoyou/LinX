import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Search, Loader2 } from 'lucide-react';
import { LayoutModal } from '@/components/LayoutModal';
import { ModalPanel } from '@/components/ModalPanel';
import { knowledgeApi } from '@/api/knowledge';
import type {
  SearchKnowledgeRequest,
  SearchKnowledgeResponse,
  KnowledgeListResponse,
} from '@/api/knowledge';
import type { Collection, Document } from '@/types/document';

const COLLECTION_SCOPE_ALL = '__all__';
const COLLECTION_SCOPE_ROOT = '__root__';
const DOCUMENT_SCOPE_ALL = '__all__';
const SCOPE_PAGE_SIZE = 100;
const MAX_SCOPE_DOCS = 2000;

interface RetrievalTestPanelProps {
  isOpen: boolean;
  onClose: () => void;
  activeCollectionId?: string | null;
  collections: Collection[];
}

export const RetrievalTestPanel: React.FC<RetrievalTestPanelProps> = ({
  isOpen,
  onClose,
  activeCollectionId,
  collections,
}) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(10);
  const [minScore, setMinScore] = useState(0.3);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingScopeDocuments, setIsLoadingScopeDocuments] = useState(false);
  const [results, setResults] = useState<SearchKnowledgeResponse | null>(null);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>(COLLECTION_SCOPE_ALL);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>(DOCUMENT_SCOPE_ALL);
  const [scopedDocuments, setScopedDocuments] = useState<Document[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    setSelectedCollectionId(activeCollectionId || COLLECTION_SCOPE_ALL);
    setSelectedDocumentId(DOCUMENT_SCOPE_ALL);
    setMinScore(0.3);
  }, [isOpen, activeCollectionId]);

  useEffect(() => {
    if (!isOpen) return;

    const fetchAllScopeDocuments = async (
      fetchPage: (page: number, pageSize: number) => Promise<KnowledgeListResponse>
    ): Promise<Document[]> => {
      const documents: Document[] = [];
      let page = 1;
      let total = Number.POSITIVE_INFINITY;

      while (documents.length < total && documents.length < MAX_SCOPE_DOCS) {
        const response = await fetchPage(page, SCOPE_PAGE_SIZE);
        documents.push(...response.items);
        total = response.total;
        if (response.items.length < SCOPE_PAGE_SIZE) break;
        page += 1;
      }

      return documents;
    };

    const loadScopedDocuments = async () => {
      setSelectedDocumentId(DOCUMENT_SCOPE_ALL);

      if (selectedCollectionId === COLLECTION_SCOPE_ALL) {
        setScopedDocuments([]);
        return;
      }

      setIsLoadingScopeDocuments(true);
      try {
        if (selectedCollectionId === COLLECTION_SCOPE_ROOT) {
          const documents = await fetchAllScopeDocuments((page, pageSize) =>
            knowledgeApi.getAll({
              page,
              page_size: pageSize,
              collection_id: 'none',
            })
          );
          setScopedDocuments(documents);
          return;
        }

        const documents = await fetchAllScopeDocuments((page, pageSize) =>
          knowledgeApi.getCollectionItems(selectedCollectionId, page, pageSize)
        );
        setScopedDocuments(documents);
      } catch {
        setScopedDocuments([]);
      } finally {
        setIsLoadingScopeDocuments(false);
      }
    };

    loadScopedDocuments();
  }, [isOpen, selectedCollectionId]);

  const availableDocuments = useMemo(
    () => [...scopedDocuments].sort((a, b) => a.name.localeCompare(b.name)),
    [scopedDocuments]
  );

  const handleSearch = async () => {
    if (!query.trim()) return;
    setIsSearching(true);
    try {
      const filters: NonNullable<SearchKnowledgeRequest['filters']> = {};

      if (selectedCollectionId !== COLLECTION_SCOPE_ALL) {
        filters.collection_id =
          selectedCollectionId === COLLECTION_SCOPE_ROOT ? 'none' : selectedCollectionId;
      }

      if (selectedDocumentId !== DOCUMENT_SCOPE_ALL) {
        filters.document_ids = [selectedDocumentId];
      }

      const data = await knowledgeApi.search({
        query: query.trim(),
        limit,
        min_score: minScore,
        filters: Object.keys(filters).length > 0 ? filters : undefined,
      });
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
    if (terms.length === 0) return text;
    const normalizedTerms = terms.map((term) => term.toLowerCase());
    const pattern = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    const regex = new RegExp(`(${pattern})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, idx) =>
      normalizedTerms.includes(part.toLowerCase()) ? (
        <mark key={idx} className="bg-yellow-300 dark:bg-yellow-600 text-inherit rounded px-0.5">
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
      keyword: 'bg-orange-500/20 text-orange-700 dark:text-orange-300',
    };
    const label = t(`retrievalTest.methods.${method}`, { defaultValue: method.toUpperCase() });
    return (
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          colors[method] || 'bg-gray-500/20 text-gray-700 dark:text-gray-300'
        }`}
      >
        {label}
      </span>
    );
  };

  if (!isOpen) return null;

  const maxScore = results?.results?.length
    ? Math.max(...results.results.map((result) => result.similarity_score))
    : 1;

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={true}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-3xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
            {t('retrievalTest.title')}
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
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('retrievalTest.queryPlaceholder')}
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
              {t('retrievalTest.search')}
            </button>
          </div>

          <div className="flex items-center gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              {t('retrievalTest.resultsLabel', { limit })}
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

          <div className="flex items-center gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              {t('retrievalTest.minScoreLabel', { score: minScore.toFixed(2) })}
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="flex-1 accent-indigo-500"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1.5">
                {t('retrievalTest.collectionScopeLabel')}
              </label>
              <select
                value={selectedCollectionId}
                onChange={(e) => setSelectedCollectionId(e.target.value)}
                className="w-full px-3 py-2.5 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                <option value={COLLECTION_SCOPE_ALL}>
                  {t('retrievalTest.allAccessibleCollections')}
                </option>
                <option value={COLLECTION_SCOPE_ROOT}>{t('retrievalTest.rootOnly')}</option>
                {collections.map((collection) => (
                  <option key={collection.id} value={collection.id}>
                    {collection.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1.5">
                {t('retrievalTest.fileScopeLabel')}
              </label>
              <select
                value={selectedDocumentId}
                onChange={(e) => setSelectedDocumentId(e.target.value)}
                disabled={selectedCollectionId === COLLECTION_SCOPE_ALL || isLoadingScopeDocuments}
                className="w-full px-3 py-2.5 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white disabled:opacity-60 disabled:cursor-not-allowed focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                <option value={DOCUMENT_SCOPE_ALL}>{t('retrievalTest.allFilesInScope')}</option>
                {availableDocuments.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {selectedCollectionId === COLLECTION_SCOPE_ALL && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('retrievalTest.selectCollectionFirst')}
            </p>
          )}

          {selectedCollectionId !== COLLECTION_SCOPE_ALL && isLoadingScopeDocuments && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('retrievalTest.loadingScopeFiles')}
            </p>
          )}
        </div>

        {results && (
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {t('retrievalTest.resultsSummary', { count: results.total, query: results.query })}
            </p>

            {results.results.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                {t('retrievalTest.noResults')}
              </div>
            ) : (
              <div className="space-y-3">
                {results.results.map((result, idx) => {
                  const scorePercent = maxScore > 0 ? (result.similarity_score / maxScore) * 100 : 0;

                  return (
                    <div
                      key={`${result.document_id}-${result.chunk_index}-${idx}`}
                      className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                    >
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

                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        {result.document_title && (
                          <span className="text-sm font-medium text-gray-800 dark:text-white">
                            {result.document_title}
                          </span>
                        )}
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {t('retrievalTest.chunkLabel', { index: result.chunk_index })}
                        </span>
                        {getMethodBadge(result.search_method)}
                      </div>

                      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed mb-2">
                        {highlightQuery(result.content.slice(0, 500), query)}
                        {result.content.length > 500 && '...'}
                      </p>

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
            {t('retrievalTest.emptyHint')}
          </div>
        )}
      </ModalPanel>
    </LayoutModal>
  );
};
