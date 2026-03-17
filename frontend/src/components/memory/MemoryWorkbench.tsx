import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';
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
import { memoryWorkbenchApi } from '@/api/memoryWorkbench';
import { useMemoryWorkbenchStore } from '@/stores/memoryWorkbenchStore';
import type { MemoryRecord, MemorySurfaceType } from '@/types/memory';

const DEFAULT_MEMORY_PAGE_SIZE = 18;
const MEMORY_PAGE_SIZE_OPTIONS = [12, 18, 24, 36];
const FETCH_LIMITS: Record<MemorySurfaceType, number> = {
  user_memory: 100,
  skill_proposal: 200,
};

const SURFACE_META: Record<
  MemorySurfaceType,
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

const matchesLocalQuery = (record: MemoryRecord, query: string): boolean => {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  const searchSpace = [
    record.summary || '',
    record.content,
    ...(record.tags || []),
    ...Object.values(record.metadata || {}).map((value) =>
      typeof value === 'string' ? value : JSON.stringify(value)
    ),
  ]
    .join('\n')
    .toLowerCase();

  return searchSpace.includes(normalized);
};

const sortRecords = (items: MemoryRecord[]): MemoryRecord[] => {
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

interface MemoryWorkbenchProps {
  memoryType: MemorySurfaceType;
  title: string;
  description: string;
}

export const MemoryWorkbench: React.FC<MemoryWorkbenchProps> = ({
  memoryType,
  title,
  description,
}) => {
  const { t } = useTranslation();
  const {
    records,
    isLoading,
    error,
    setRecordsByType,
    updateRecord,
    setLoading,
    setError,
    clearError,
    setActiveTab,
  } = useMemoryWorkbenchStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<MemoryRecord | null>(null);
  const [isDetailViewOpen, setIsDetailViewOpen] = useState(false);
  const [isConfigPanelOpen, setIsConfigPanelOpen] = useState(false);
  const [isRetrievalTestOpen, setIsRetrievalTestOpen] = useState(false);
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_MEMORY_PAGE_SIZE);
  const [reviewingCandidateId, setReviewingCandidateId] = useState<string | null>(null);
  const [deletingRecordId, setDeletingRecordId] = useState<string | null>(null);

  const memoryQuery = memoryType === 'user_memory' ? debouncedSearchQuery : undefined;
  const activeRecords = useMemo(
    () => records.filter((record) => record.type === memoryType),
    [records, memoryType]
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
          ? await memoryWorkbenchApi.listUserMemory({
              query: memoryQuery || undefined,
              limit: FETCH_LIMITS[memoryType],
            })
          : await memoryWorkbenchApi.listSkillProposals({
              review_status: 'all',
              limit: FETCH_LIMITS[memoryType],
            });
      setRecordsByType(memoryType, items);
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
    setRecordsByType,
    t,
  ]);

  useEffect(() => {
    void fetchMemories();
  }, [fetchMemories]);

  const allTags = useMemo(
    () => Array.from(new Set(activeRecords.flatMap((record) => record.tags))),
    [activeRecords]
  );

  const filteredRecords = useMemo(() => {
    return sortRecords(
      activeRecords.filter((record) => {
        if (dateFrom && new Date(record.createdAt) < new Date(dateFrom)) {
          return false;
        }
        if (dateTo && new Date(record.createdAt) > new Date(dateTo)) {
          return false;
        }
        if (selectedTags.length > 0 && !selectedTags.some((tag) => record.tags.includes(tag))) {
          return false;
        }
        if (memoryType === 'skill_proposal' && !matchesLocalQuery(record, debouncedSearchQuery)) {
          return false;
        }
        return true;
      })
    );
  }, [activeRecords, dateFrom, dateTo, debouncedSearchQuery, memoryType, selectedTags]);

  const effectiveTotal = filteredRecords.length;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / pageSize));
  const visibleRecords = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredRecords.slice(start, start + pageSize);
  }, [currentPage, filteredRecords, pageSize]);
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
    if (selectedRecord && !activeRecords.some((item) => item.id === selectedRecord.id)) {
      setSelectedRecord(null);
      setIsDetailViewOpen(false);
    }
  }, [activeRecords, selectedRecord]);

  const handleRecordClick = (record: MemoryRecord) => {
    setSelectedRecord(record);
    setIsDetailViewOpen(true);
  };

  const handleReviewCandidate = async (
    record: MemoryRecord,
    action: 'publish' | 'reject' | 'revise'
  ) => {
    if (reviewingCandidateId) {
      return;
    }

    setReviewingCandidateId(record.id);
    try {
      const updated = await memoryWorkbenchApi.reviewSkillProposal(record.id, { action });
      updateRecord(record.id, updated);
      if (selectedRecord?.id === record.id) {
        setSelectedRecord(updated);
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

  const handleDeleteRecord = async (record: MemoryRecord) => {
    if (deletingRecordId) {
      return;
    }

    const confirmed = window.confirm(
      record.type === 'skill_proposal'
        ? t('memory.delete.confirmSkillProposal', {
            defaultValue:
              'Delete this skill proposal? If it is the only proposal linked to a published skill, the published skill will also be removed.',
          })
        : t('memory.delete.confirmUserMemory', {
            defaultValue: 'Delete this memory record and its linked surfaces?',
          })
    );
    if (!confirmed) {
      return;
    }

    setDeletingRecordId(record.id);
    try {
      if (record.type === 'skill_proposal') {
        await memoryWorkbenchApi.deleteSkillProposal(record.id, true);
      } else {
        const memorySource =
          record.metadata?.memory_source === 'entry' ? 'entry' : 'user_memory_view';
        await memoryWorkbenchApi.deleteUserMemory(record.id, memorySource);
      }
      if (selectedRecord?.id === record.id) {
        setSelectedRecord(null);
        setIsDetailViewOpen(false);
      }
      await fetchMemories();
      toast.success(
        record.type === 'skill_proposal'
          ? t('memory.delete.skillProposalSuccess', {
              defaultValue: 'Skill proposal deleted',
            })
          : t('memory.delete.userMemorySuccess', {
              defaultValue: 'Memory record deleted',
            })
      );
    } catch (deleteError: unknown) {
      toast.error(getErrorDetail(deleteError) || t('memory.delete.error', {
        defaultValue: 'Failed to delete record',
      }));
    } finally {
      setDeletingRecordId(null);
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
              {activeRecords.length}
            </span>
          </div>
          <div>
            <h1 className="text-3xl font-bold text-zinc-800 dark:text-white">{title}</h1>
            <p className={`mt-2 text-sm ${surfaceMeta.accentClassName}`}>{description}</p>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t('memory.resetNotice', {
                defaultValue:
                  'Memory System keeps durable user memory and reviewable skill proposals together. Shared organizational knowledge lives in Knowledge Base.',
              })}
            </p>
          </div>
          <div className="inline-flex rounded-xl border border-zinc-200 bg-white/70 p-1 dark:border-zinc-700 dark:bg-zinc-900/60">
            <NavLink
              to="/memory/user-memory"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-500 text-white'
                    : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
                }`
              }
            >
              {t('nav.userMemory', { defaultValue: 'User Memory' })}
            </NavLink>
            <NavLink
              to="/memory/skill-proposals"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-sky-500 text-white'
                    : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
                }`
              }
            >
              {t('nav.skillProposals', { defaultValue: 'Skill Proposals' })}
            </NavLink>
          </div>
          <p className="max-w-3xl text-sm text-zinc-500 dark:text-zinc-400">
            {t('memory.tabsHint', {
              defaultValue:
                'User Memory stores durable facts and events about a user. Skill Proposals store reusable action patterns distilled from the same memory pipeline and can be reviewed before publishing into the Skill Library.',
            })}
          </p>
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
          {visibleRecords.length === 0 ? (
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
            visibleRecords.map((record) => (
              <MemoryCard
                key={record.id}
                memory={record}
                onClick={handleRecordClick}
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
        key={selectedRecord?.id || 'memory-detail'}
        memory={selectedRecord}
        isOpen={isDetailViewOpen}
        onClose={() => {
          setIsDetailViewOpen(false);
          setSelectedRecord(null);
        }}
        onDelete={handleDeleteRecord}
        onReviewCandidate={
          selectedRecord?.type === 'skill_proposal' ? handleReviewCandidate : undefined
        }
        isReviewingCandidate={selectedRecord ? reviewingCandidateId === selectedRecord.id : false}
      />
      <MemoryConfigPanel isOpen={isConfigPanelOpen} onClose={() => setIsConfigPanelOpen(false)} />
      <MemoryRetrievalTestPanel
        isOpen={isRetrievalTestOpen}
        onClose={() => setIsRetrievalTestOpen(false)}
      />
    </div>
  );
};
