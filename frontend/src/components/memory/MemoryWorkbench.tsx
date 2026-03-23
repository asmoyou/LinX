import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  Settings2,
  User,
  Users,
  X,
} from "lucide-react";
import toast from "react-hot-toast";
import { MemoryCard } from "@/components/memory/MemoryCard";
import { MemoryConfigPanel } from "@/components/memory/MemoryConfigPanel";
import { MemoryDetailView } from "@/components/memory/MemoryDetailView";
import { MemoryRetrievalTestPanel } from "@/components/memory/MemoryRetrievalTestPanel";
import { MemorySearchBar } from "@/components/memory/MemorySearchBar";
import { memoryWorkbenchApi } from "@/api/memoryWorkbench";
import { useAuthStore } from "@/stores/authStore";
import { useMemoryWorkbenchStore } from "@/stores/memoryWorkbenchStore";
import type { MemoryRecord } from "@/types/memory";

const DEFAULT_MEMORY_PAGE_SIZE = 18;
const MEMORY_PAGE_SIZE_OPTIONS = [12, 18, 24, 36];

const getErrorDetail = (error: unknown): string | null => {
  if (!error || typeof error !== "object") {
    return null;
  }
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    .response?.data?.detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
};

type SimpleUser = { user_id: string; username: string; display_name?: string };

// ── Searchable User Selector ──
const UserSelector: React.FC<{
  value: string;
  onChange: (v: string) => void;
  userList: SimpleUser[];
}> = ({ value, onChange, userList }) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const builtInOptions: { id: string; label: string }[] = [
    { id: "", label: t("memory.userSelector.myMemory", { defaultValue: "My Memories" }) },
    { id: "all", label: t("memory.userSelector.allUsers", { defaultValue: "All Users" }) },
  ];

  const filteredUsers = search.trim()
    ? userList.filter((u) => {
        const q = search.toLowerCase();
        return (
          (u.display_name || "").toLowerCase().includes(q) ||
          u.username.toLowerCase().includes(q)
        );
      })
    : userList;

  const currentLabel = (() => {
    const bi = builtInOptions.find((o) => o.id === value);
    if (bi) return bi.label;
    const u = userList.find((u) => u.user_id === value);
    return u ? u.display_name || u.username : value;
  })();

  const select = (id: string) => {
    onChange(id);
    setOpen(false);
    setSearch("");
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white/50 px-3 py-1.5 text-sm text-gray-700 hover:bg-white/70 dark:border-gray-600 dark:bg-black/20 dark:text-gray-200 dark:hover:bg-black/30"
      >
        <Users className="h-4 w-4 text-gray-500 dark:text-gray-400" />
        <span className="max-w-[140px] truncate">{currentLabel}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1 w-64 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-zinc-900">
          <div className="border-b border-gray-200 p-2 dark:border-gray-700">
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("memory.userSelector.search", { defaultValue: "Search users..." })}
              className="w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-gray-600 dark:bg-zinc-800 dark:text-white"
            />
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {builtInOptions.map((opt) => (
              <button
                key={opt.id}
                onClick={() => select(opt.id)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-gray-100 dark:hover:bg-zinc-800 ${
                  value === opt.id ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300" : "text-gray-700 dark:text-gray-300"
                }`}
              >
                {opt.label}
              </button>
            ))}
            {filteredUsers.length > 0 && (
              <div className="my-1 border-t border-gray-200 dark:border-gray-700" />
            )}
            {filteredUsers.map((u) => (
              <button
                key={u.user_id}
                onClick={() => select(u.user_id)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-gray-100 dark:hover:bg-zinc-800 ${
                  value === u.user_id ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300" : "text-gray-700 dark:text-gray-300"
                }`}
              >
                <User className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
                <span className="truncate">{u.display_name || u.username}</span>
                {u.display_name && (
                  <span className="ml-auto text-xs text-gray-400 truncate">{u.username}</span>
                )}
              </button>
            ))}
            {filteredUsers.length === 0 && search.trim() && (
              <p className="px-3 py-2 text-xs text-gray-400">
                {t("memory.userSelector.noResults", { defaultValue: "No users found" })}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ── Main Workbench ──

interface MemoryWorkbenchProps {
  title: string;
  description: string;
}

export const MemoryWorkbench: React.FC<MemoryWorkbenchProps> = ({
  title,
  description,
}) => {
  const { t } = useTranslation();
  const currentUser = useAuthStore((s) => s.user);
  const isAdmin =
    currentUser?.role === "admin" || currentUser?.role === "manager";

  const {
    records,
    isLoading,
    error,
    setRecordsByType,
    setLoading,
    setError,
    clearError,
    setActiveTab,
  } = useMemoryWorkbenchStore();

  // ── Filter state (immediate) ──
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedFactKinds, setSelectedFactKinds] = useState<string[]>([]);
  const [selectedRecordType, setSelectedRecordType] = useState("");
  const [importanceMin, setImportanceMin] = useState("");
  const [importanceMax, setImportanceMax] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [userList, setUserList] = useState<SimpleUser[]>([]);

  // ── Pagination state ──
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_MEMORY_PAGE_SIZE);
  const [serverTotal, setServerTotal] = useState(0);

  // ── UI state ──
  const [selectedRecord, setSelectedRecord] = useState<MemoryRecord | null>(null);
  const [isDetailViewOpen, setIsDetailViewOpen] = useState(false);
  const [isConfigPanelOpen, setIsConfigPanelOpen] = useState(false);
  const [isRetrievalTestOpen, setIsRetrievalTestOpen] = useState(false);
  const [deletingRecordId, setDeletingRecordId] = useState<string | null>(null);

  // ── Debounced filter snapshot ──
  const [debouncedFilters, setDebouncedFilters] = useState({
    query: "",
    dateFrom: "",
    dateTo: "",
    factKinds: [] as string[],
    recordType: "",
    impMin: "",
    impMax: "",
  });

  // ── Race condition guard: discard stale fetch results ──
  const fetchVersionRef = useRef(0);

  const activeRecords = useMemo(
    () => records.filter((record) => record.type === "user_memory"),
    [records],
  );

  useEffect(() => {
    setActiveTab("user_memory");
  }, [setActiveTab]);

  // Fetch user list for admin selector (exclude current user)
  useEffect(() => {
    if (!isAdmin) return;
    memoryWorkbenchApi
      .listUsers()
      .then((users) =>
        setUserList(users.filter((u) => u.user_id !== currentUser?.id)),
      )
      .catch(() => {});
  }, [isAdmin, currentUser?.id]);

  // Single consolidated debounce for all filter changes
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedFilters({
        query: searchQuery.trim(),
        dateFrom,
        dateTo,
        factKinds: [...selectedFactKinds],
        recordType: selectedRecordType,
        impMin: importanceMin,
        impMax: importanceMax,
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [searchQuery, dateFrom, dateTo, selectedFactKinds, selectedRecordType, importanceMin, importanceMax]);

  // Reset to page 1 when filters or user change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedFilters, selectedUserId, pageSize]);

  const fetchRef = useRef<() => Promise<void>>();

  const fetchMemories = useCallback(async () => {
    const version = ++fetchVersionRef.current;
    setLoading(true);
    clearError();

    const offset = (currentPage - 1) * pageSize;
    const impMin = debouncedFilters.impMin ? parseFloat(debouncedFilters.impMin) : undefined;
    const impMax = debouncedFilters.impMax ? parseFloat(debouncedFilters.impMax) : undefined;

    try {
      const { items, total } = await memoryWorkbenchApi.listUserMemory({
        query: debouncedFilters.query || undefined,
        user_id: selectedUserId || undefined,
        limit: pageSize,
        offset,
        date_from: debouncedFilters.dateFrom || undefined,
        date_to: debouncedFilters.dateTo || undefined,
        fact_kind:
          debouncedFilters.factKinds.length > 0
            ? debouncedFilters.factKinds.join(",")
            : undefined,
        record_type: debouncedFilters.recordType || undefined,
        importance_min:
          impMin !== undefined && !isNaN(impMin) ? impMin : undefined,
        importance_max:
          impMax !== undefined && !isNaN(impMax) ? impMax : undefined,
      });
      if (fetchVersionRef.current !== version) return; // stale response
      setRecordsByType("user_memory", items);
      setServerTotal(total);
    } catch (fetchError: unknown) {
      if (fetchVersionRef.current !== version) return;
      setError(
        getErrorDetail(fetchError) ||
          t("memory.loadError", { defaultValue: "Failed to load memory data" }),
      );
    } finally {
      if (fetchVersionRef.current === version) {
        setLoading(false);
      }
    }
  }, [
    clearError,
    currentPage,
    pageSize,
    debouncedFilters,
    selectedUserId,
    setError,
    setLoading,
    setRecordsByType,
    t,
  ]);

  fetchRef.current = fetchMemories;

  useEffect(() => {
    void fetchMemories();
  }, [fetchMemories]);

  // Close detail if record disappears from current page
  useEffect(() => {
    if (
      selectedRecord &&
      !activeRecords.some((item) => item.id === selectedRecord.id)
    ) {
      setSelectedRecord(null);
      setIsDetailViewOpen(false);
    }
  }, [activeRecords, selectedRecord]);

  const allTags = useMemo(
    () => Array.from(new Set(activeRecords.flatMap((record) => record.tags))),
    [activeRecords],
  );

  // Client-side: only tag filtering (everything else is server-side)
  const filteredRecords = useMemo(() => {
    if (selectedTags.length === 0) return activeRecords;
    return activeRecords.filter((record) =>
      selectedTags.some((tag) => record.tags.includes(tag)),
    );
  }, [activeRecords, selectedTags]);

  const effectiveTotal = selectedTags.length > 0 ? filteredRecords.length : serverTotal;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / pageSize));
  const shouldShowBlockingLoader = isLoading && activeRecords.length === 0;

  const hasActiveFilters = Boolean(
    debouncedFilters.query ||
      dateFrom ||
      dateTo ||
      selectedTags.length > 0 ||
      selectedFactKinds.length > 0 ||
      selectedRecordType ||
      importanceMin ||
      importanceMax,
  );
  const displayStart = effectiveTotal === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const displayEnd = effectiveTotal === 0 ? 0 : Math.min(effectiveTotal, currentPage * pageSize);
  const showPagerPanel = effectiveTotal > 0 || hasActiveFilters;

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const handleRecordClick = (record: MemoryRecord) => {
    setSelectedRecord(record);
    setIsDetailViewOpen(true);
  };

  const handleDeleteRecord = async (record: MemoryRecord) => {
    if (deletingRecordId) return;

    const confirmed = window.confirm(
      t("memory.delete.confirmUserMemory", {
        defaultValue: "Delete this memory record and its linked surfaces?",
      }),
    );
    if (!confirmed) return;

    setDeletingRecordId(record.id);
    try {
      const memorySource =
        record.metadata?.memory_source === "entry" ? "entry" : "user_memory_view";
      await memoryWorkbenchApi.deleteUserMemory(record.id, memorySource);
      if (selectedRecord?.id === record.id) {
        setSelectedRecord(null);
        setIsDetailViewOpen(false);
      }
      await fetchRef.current?.();
      toast.success(
        t("memory.delete.userMemorySuccess", { defaultValue: "Memory record deleted" }),
      );
    } catch (deleteError: unknown) {
      toast.error(
        getErrorDetail(deleteError) ||
          t("memory.delete.error", { defaultValue: "Failed to delete record" }),
      );
    } finally {
      setDeletingRecordId(null);
    }
  };

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((v) => v !== tag) : [...prev, tag],
    );
  };

  const handleFactKindToggle = (kind: string) => {
    setSelectedFactKinds((prev) =>
      prev.includes(kind) ? prev.filter((v) => v !== kind) : [...prev, kind],
    );
  };

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
              <User className="h-4 w-4" />
            </span>
            <span>{title}</span>
            <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs dark:bg-black/20">
              {effectiveTotal}
            </span>
          </div>
          <div>
            <h1 className="text-3xl font-bold text-zinc-800 dark:text-white">{title}</h1>
            <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-300">{description}</p>
            <p className="mt-2 max-w-3xl text-sm text-zinc-500 dark:text-zinc-400">
              {t("memory.resetNotice", {
                defaultValue:
                  "Memory Workbench now focuses on durable user memory only. Skill candidates and bindings move to the Skills page.",
              })}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isAdmin && (
            <UserSelector
              value={selectedUserId}
              onChange={setSelectedUserId}
              userList={userList}
            />
          )}
          <button
            onClick={() => setIsRetrievalTestOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-gray-200 px-4 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
          >
            <Search className="h-5 w-5" />
            {t("memory.retrievalTest.trigger", "Retrieval Test")}
          </button>
          <button
            onClick={() => setIsConfigPanelOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-gray-200 px-4 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
          >
            <Settings2 className="h-5 w-5" />
            {t("memory.config.manage", "Config")}
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
        selectedFactKinds={selectedFactKinds}
        onFactKindToggle={handleFactKindToggle}
        selectedRecordType={selectedRecordType}
        onRecordTypeChange={setSelectedRecordType}
        importanceMin={importanceMin}
        importanceMax={importanceMax}
        onImportanceMinChange={setImportanceMin}
        onImportanceMaxChange={setImportanceMax}
      />

      {shouldShowBlockingLoader && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        </div>
      )}

      {!shouldShowBlockingLoader && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filteredRecords.length === 0 ? (
            <div className="col-span-full py-12 text-center">
              <p className="text-gray-500 dark:text-gray-400">
                {effectiveTotal === 0 && !hasActiveFilters
                  ? t("memory.empty.userMemory", { defaultValue: "No user memory yet." })
                  : t("memory.noResults")}
              </p>
            </div>
          ) : (
            filteredRecords.map((record) => (
              <MemoryCard
                key={record.id}
                memory={record}
                onClick={handleRecordClick}
                showRelevance={Boolean(debouncedFilters.query)}
              />
            ))
          )}
        </div>
      )}

      {!shouldShowBlockingLoader && showPagerPanel && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t("memory.pagination.summary", {
              start: displayStart,
              end: displayEnd,
              total: effectiveTotal,
              defaultValue: "{{start}}-{{end}} / {{total}}",
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
                  {t("memory.pagination.pageSize", {
                    size,
                    defaultValue: "{{size}} / page",
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
              {t("memory.pagination.prev", { defaultValue: "Prev" })}
            </button>
            <span className="px-3 py-1 text-xs text-zinc-600 dark:text-zinc-400">
              {t("memory.pagination.page", {
                current: currentPage,
                total: totalPages,
                defaultValue: "Page {{current}} / {{total}}",
              })}
            </span>
            <button
              onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={currentPage >= totalPages}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              {t("memory.pagination.next", { defaultValue: "Next" })}
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      <MemoryDetailView
        memory={selectedRecord}
        isOpen={isDetailViewOpen}
        onClose={() => {
          setIsDetailViewOpen(false);
          setSelectedRecord(null);
        }}
        onDelete={handleDeleteRecord}
      />
      <MemoryConfigPanel
        isOpen={isConfigPanelOpen}
        onClose={() => setIsConfigPanelOpen(false)}
      />
      <MemoryRetrievalTestPanel
        isOpen={isRetrievalTestOpen}
        onClose={() => setIsRetrievalTestOpen(false)}
      />
    </div>
  );
};
