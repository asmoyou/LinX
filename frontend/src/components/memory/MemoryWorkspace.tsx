import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  Brain,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  Settings2,
  User,
  X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { MemoryCard } from '@/components/memory/MemoryCard';
import { MemoryConfigPanel } from '@/components/memory/MemoryConfigPanel';
import { MemoryDetailView } from '@/components/memory/MemoryDetailView';
import { MemoryRetrievalTestPanel } from '@/components/memory/MemoryRetrievalTestPanel';
import { MemorySearchBar } from '@/components/memory/MemorySearchBar';
import { memoriesApi } from '@/api/memories';
import { useMemoryStore } from '@/stores/memoryStore';
import type { Memory, MemoryProductType } from '@/types/memory';

const DEFAULT_MEMORY_PAGE_SIZE = 18;
const MEMORY_PAGE_SIZE_OPTIONS = [12, 18, 24, 36];
const FETCH_LIMITS: Record<MemoryProductType, number> = {
  user_memory: 100,
  skill_proposal: 200,
};

const SURFACE_META: Record<
  MemoryProductType,
  {
    icon: typeof User;
    accentClassName: string;
    badgeClassName: string;
    iconContainerClassName: string;
  }
> = {
  user_memory: {
    icon: User,
    accentClassName: 'text-emerald-700 dark:text-emerald-300',
    badgeClassName:
      'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300',
    iconContainerClassName:
      'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300',
  },
  skill_proposal: {
    icon: Brain,
    accentClassName: 'text-sky-700 dark:text-sky-300',
    badgeClassName:
      'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-300',
    iconContainerClassName:
      'bg-sky-100 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300',
  },
};

const getErrorDetail = (error: unknown): string | null => {
  if (!error || typeof error !== 'object') {
    return null;
  }

  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : null;
};

const matchesLocalQuery = (memory: Memory, query: string): boolean => {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  const searchSpace = [
    memory.summary || '',
    memory.content,
    ...(memory.tags || []),
    ...Object.values(memory.metadata || {}).map((value) =>
      typeof value === 'string' ? value : JSON.stringify(value)
    ),
  ]
    .join('\n')
    .toLowerCase();

  return searchSpace.includes(normalized);
};

const sortMemories = (items: Memory[]): Memory[] => {
  return [...items].sort((left, right) => {
    const leftStatus = String(left.metadata?.review_status || 'pending').toLowerCase();
    const rightStatus = String(right.metadata?.review_status || 'pending').toLowerCase();
    const statusRank = (value: string) => {
      if (value === 'pending') return 0;
      if (value === 'published') return 1;
      if (value === 'rejected') return 2;
      return 3;
    };

    const leftTime = new Date(left.updatedAt || left.createdAt).getTime();
    const rightTime = new Date(right.updatedAt || right.createdAt).getTime();

    if (left.type === 'skill_proposal' && right.type === 'skill_proposal') {
      const rankDelta = statusRank(leftStatus) - statusRank(rightStatus);
      if (rankDelta !== 0) {
        return rankDelta;
      }
    }

    return rightTime - leftTime;
  });
};

interface MemoryWorkspaceProps {
  memoryType: MemoryProductType;
  title: string;
  description: string;
}

export const MemoryWorkspace: React.FC<MemoryWorkspaceProps> = ({
  memoryType,
  title,
  description,
}) => {
  const { t } = useTranslation();
  const {
    memories,
    isLoading,
    error,
    setMemoriesByType,
    updateMemory,
    setLoading,
    setError,
    clearError,
    setActiveTab,
  } = useMemoryStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [isDetailViewOpen, setIsDetailViewOpen] = useState(false);
  const [isConfigPanelOpen, setIsConfigPanelOpen] = useState(false);
  const [isRetrievalTestOpen, setIsRetrievalTestOpen] = useState(false);
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_MEMORY_PAGE_SIZE);
  const [reviewingCandidateId, setReviewingCandidateId] = useState<string | null>(null);

  const memoryQuery = memoryType === 'user_memory' ? debouncedSearchQuery : undefined;
  const activeMemories = useMemo(
    () => memories.filter((memory) => memory.type === memoryType),
    [memories, memoryType]
  );
  const surfaceMeta = SURFACE_META[memoryType];
  const SurfaceIcon = surfaceMeta.icon;

  useEffect(() => {
    setActiveTab(memoryType);
  }, [memoryType, setActiveTab]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim());
    }, 400);
    return () => {
      window.clearTimeout(timer);
    };
  }, [searchQuery]);

  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearchQuery, memoryType, dateFrom, dateTo, pageSize, selectedTags]);

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    clearError();

    try {
      const items =
        memoryType === 'user_memory'
          ? await memoriesApi.listUserMemory({
              query: memoryQuery || undefined,
              limit: FETCH_LIMITS[memoryType],
            })
          : await memoriesApi.listSkillProposals({
              review_status: 'all',
              limit: FETCH_LIMITS[memoryType],
            });
      setMemoriesByType(memoryType, items);
    } catch (fetchError: unknown) {
      setError(getErrorDetail(fetchError) || t('memory.loadError', { defaultValue: 'Failed to load memory data' }));
    } finally {
      setLoading(false);
    }
  }, [
    clearError,
    memoryQuery,
    memoryType,
    setError,
    setLoading,
    setMemoriesByType,
    t,
  ]);

  useEffect(() => {
    void fetchMemories();
  }, [fetchMemories]);

  const allTags = useMemo(
    () => Array.from(new Set(activeMemories.flatMap((memory) => memory.tags))),
    [activeMemories]
  );

  const filteredMemories = useMemo(() => {
    return sortMemories(
      activeMemories.filter((memory) => {
        if (dateFrom && new Date(memory.createdAt) < new Date(dateFrom)) {
          return false;
        }
        if (dateTo && new Date(memory.createdAt) > new Date(dateTo)) {
          return false;
        }
        if (selectedTags.length > 0 && !selectedTags.some((tag) => memory.tags.includes(tag))) {
          return false;
        }
        if (memoryType === 'skill_proposal' && !matchesLocalQuery(memory, debouncedSearchQuery)) {
          return false;
        }
        return true;
      })
    );
  }, [activeMemories, dateFrom, dateTo, debouncedSearchQuery, memoryType, selectedTags]);

  const effectiveTotal = filteredMemories.length;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / pageSize));
  const visibleMemories = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredMemories.slice(start, start + pageSize);
  }, [currentPage, filteredMemories, pageSize]);
  const hasActiveFilters = Boolean(
    debouncedSearchQuery || dateFrom || dateTo || selectedTags.length > 0
  );
  const pageStart = effectiveTotal === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageEnd = effectiveTotal === 0 ? 0 : Math.min(effectiveTotal, currentPage * pageSize);
  const showPagerPanel = effectiveTotal > 0 || hasActiveFilters;

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  useEffect(() => {
    if (selectedMemory && !activeMemories.some((item) => item.id === selectedMemory.id)) {
      setSelectedMemory(null);
      setIsDetailViewOpen(false);
    }
  }, [activeMemories, selectedMemory]);

  const handleMemoryClick = (memory: Memory) => {
    setSelectedMemory(memory);
    setIsDetailViewOpen(true);
  };

  const handleReviewCandidate = async (
    memory: Memory,
    action: 'publish' | 'reject' | 'revise'
  ) => {
    if (reviewingCandidateId) {
      return;
    }

    setReviewingCandidateId(memory.id);
    try {
      const updated = await memoriesApi.reviewSkillProposal(memory.id, { action });
      updateMemory(memory.id, updated);
      if (selectedMemory?.id === memory.id) {
        setSelectedMemory(updated);
      }
      await fetchMemories();
      toast.success(
        action === 'publish'
          ? t('memory.share.reviewApproveSuccess', {
              defaultValue: 'Skill proposal approved and published',
            })
          : action === 'reject'
            ? t('memory.share.reviewRejectSuccess', {
                defaultValue: 'Skill proposal rejected',
              })
            : t('memory.share.reviewReviseSuccess', {
                defaultValue: 'Skill proposal status updated',
              })
      );
    } catch (reviewError: unknown) {
      toast.error(getErrorDetail(reviewError) || t('memory.share.error'));
    } finally {
      setReviewingCandidateId(null);
    }
  };

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((value) => value !== tag) : [...prev, tag]
    );
  };

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-3">
          <div
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium ${surfaceMeta.badgeClassName}`}
          >
            <span
              className={`inline-flex h-7 w-7 items-center justify-center rounded-full ${surfaceMeta.iconContainerClassName}`}
            >
              <SurfaceIcon className="h-4 w-4" />
            </span>
            <span>{title}</span>
            <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs dark:bg-black/20">
              {activeMemories.length}
            </span>
          </div>
          <div>
            <h1 className="text-3xl font-bold text-zinc-800 dark:text-white">{title}</h1>
            <p className={`mt-2 text-sm ${surfaceMeta.accentClassName}`}>{description}</p>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t('memory.resetNotice', {
                defaultValue:
                  'This surface only keeps final-model user memory and skill proposals. Shared organizational content now lives in Knowledge Base.',
              })}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsRetrievalTestOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-gray-200 px-4 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
          >
            <Search className="h-5 w-5" />
            {t('memory.retrievalTest.trigger', 'Retrieval Test')}
          </button>
          <button
            onClick={() => setIsConfigPanelOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-gray-200 px-4 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
          >
            <Settings2 className="h-5 w-5" />
            {t('memory.config.manage', 'Config')}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-red-600 dark:text-red-400">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
          <button onClick={clearError} className="ml-auto">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <MemorySearchBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFromChange={setDateFrom}
        onDateToChange={setDateTo}
        selectedTags={selectedTags}
        availableTags={allTags}
        onTagToggle={handleTagToggle}
      />

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        </div>
      )}

      {!isLoading && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {visibleMemories.length === 0 ? (
            <div className="col-span-full py-12 text-center">
              <p className="text-gray-500 dark:text-gray-400">
                {effectiveTotal === 0 && !hasActiveFilters
                  ? memoryType === 'user_memory'
                    ? t('memory.empty.userMemory', { defaultValue: 'No user memory yet.' })
                    : t('memory.empty.skillProposal', { defaultValue: 'No skill proposals yet.' })
                  : t('memory.noResults')}
              </p>
            </div>
          ) : (
            visibleMemories.map((memory) => (
              <MemoryCard
                key={memory.id}
                memory={memory}
                onClick={handleMemoryClick}
                showRelevance={memoryType === 'user_memory' && Boolean(debouncedSearchQuery)}
              />
            ))
          )}
        </div>
      )}

      {!isLoading && showPagerPanel && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('memory.pagination.summary', {
              start: pageStart,
              end: pageEnd,
              total: effectiveTotal,
              defaultValue: '{{start}}-{{end}} / {{total}}',
            })}
          </p>
          <div className="flex items-center gap-2">
            <select
              value={String(pageSize)}
              onChange={(event) => setPageSize(Number(event.target.value))}
              className="rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              {MEMORY_PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {t('memory.pagination.pageSize', {
                    size,
                    defaultValue: '{{size}} / page',
                  })}
                </option>
              ))}
            </select>
            <button
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage <= 1}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              {t('memory.pagination.prev', { defaultValue: 'Prev' })}
            </button>
            <span className="px-3 py-1 text-xs text-zinc-600 dark:text-zinc-400">
              {t('memory.pagination.page', {
                current: currentPage,
                total: totalPages,
                defaultValue: 'Page {{current}} / {{total}}',
              })}
            </span>
            <button
              onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={currentPage >= totalPages}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              {t('memory.pagination.next', { defaultValue: 'Next' })}
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      <MemoryDetailView
        key={selectedMemory?.id || 'memory-detail'}
        memory={selectedMemory}
        isOpen={isDetailViewOpen}
        onClose={() => {
          setIsDetailViewOpen(false);
          setSelectedMemory(null);
        }}
        onReviewCandidate={
          selectedMemory?.type === 'skill_proposal' ? handleReviewCandidate : undefined
        }
        isReviewingCandidate={selectedMemory ? reviewingCandidateId === selectedMemory.id : false}
      />
      <MemoryConfigPanel isOpen={isConfigPanelOpen} onClose={() => setIsConfigPanelOpen(false)} />
      <MemoryRetrievalTestPanel
        isOpen={isRetrievalTestOpen}
        onClose={() => setIsRetrievalTestOpen(false)}
      />
    </div>
  );
};
