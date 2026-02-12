import React, { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Brain,
  Building,
  User,
  Plus,
  Settings2,
  Loader2,
  AlertCircle,
  X,
} from "lucide-react";
import toast from "react-hot-toast";
import { MemoryCard } from "@/components/memory/MemoryCard";
import { MemorySearchBar } from "@/components/memory/MemorySearchBar";
import { MemoryDetailView } from "@/components/memory/MemoryDetailView";
import { MemorySharingModal } from "@/components/memory/MemorySharingModal";
import { MemoryConfigPanel } from "@/components/memory/MemoryConfigPanel";
import { memoriesApi } from "@/api/memories";
import { agentsApi } from "@/api/agents";
import { useMemoryStore } from "@/stores/memoryStore";
import { ModalPanel } from "@/components/ModalPanel";
import type {
  Memory as MemoryType,
  MemoryType as MemoryCategory,
  MemoryIndexInfo,
} from "@/types/memory";
import type { Agent } from "@/types/agent";

const getErrorDetail = (error: unknown): string | null => {
  if (!error || typeof error !== "object") {
    return null;
  }

  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data
    ?.detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
};

const CreateMemoryModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onCreated: (memory: MemoryType) => void;
}> = ({ isOpen, onClose, onCreated }) => {
  const { t } = useTranslation();
  // Only allow company type for manual creation
  const type: MemoryCategory = "company";
  const [content, setContent] = useState("");
  const [summary, setSummary] = useState("");
  const [tags, setTags] = useState("");
  const [agentId, setAgentId] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch agents for the selector
  useEffect(() => {
    if (!isOpen) return;
    const fetchAgents = async () => {
      setIsLoadingAgents(true);
      try {
        const data = await agentsApi.getAll();
        setAgents(data);
      } catch {
        setAgents([]);
      } finally {
        setIsLoadingAgents(false);
      }
    };
    fetchAgents();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!content.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const memory = await memoriesApi.create({
        type,
        content: content.trim(),
        summary: summary.trim() || undefined,
        agent_id: agentId || undefined,
        tags: tagList.length > 0 ? tagList : undefined,
      });
      onCreated(memory);
      setContent("");
      setSummary("");
      setTags("");
      setAgentId("");
      onClose();
    } catch (error: unknown) {
      setError(getErrorDetail(error) || t("memory.create.error"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
      style={{ marginLeft: "var(--sidebar-width, 0px)" }}
    >
      <ModalPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
            {t("memory.create.title")}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        {/* Info banner: only company memory can be manually created */}
        <div className="mb-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg text-blue-700 dark:text-blue-400 text-sm">
          {t("memory.create.companyOnly")}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-600 dark:text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {/* Agent selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("memory.create.agentBinding")}
            </label>
            {isLoadingAgents ? (
              <div className="flex items-center gap-2 px-3 py-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm text-gray-500">
                  {t("common.loading")}
                </span>
              </div>
            ) : (
              <select
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white"
              >
                <option value="">{t("memory.create.agentUnbound")}</option>
                {agents.map((agent) => (
                  <option
                    key={agent.agentId || agent.id}
                    value={agent.agentId || agent.id}
                  >
                    {agent.name}
                  </option>
                ))}
              </select>
            )}
            <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
              {t("memory.create.agentBindingHint")}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("memory.create.summary")}
            </label>
            <input
              type="text"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={t("memory.create.summaryPlaceholder")}
              className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("memory.create.contentRequired")}
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t("memory.create.contentPlaceholder")}
              rows={5}
              className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("memory.create.tags")}
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder={t("memory.create.tagsPlaceholder")}
              className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
          >
            {t("memory.create.cancel")}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!content.trim() || isSubmitting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Plus className="w-5 h-5" />
            )}
            {t("memory.create.submit")}
          </button>
        </div>
      </ModalPanel>
    </div>
  );
};

export const Memory: React.FC = () => {
  const { t } = useTranslation();
  const {
    memories,
    isLoading,
    error,
    setMemoriesByType,
    addMemory,
    updateMemory,
    removeMemory,
    setLoading,
    setError,
    clearError,
  } = useMemoryStore();

  const [activeTab, setActiveTab] = useState<MemoryCategory>("agent");
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedMemory, setSelectedMemory] = useState<MemoryType | null>(null);
  const [isDetailViewOpen, setIsDetailViewOpen] = useState(false);
  const [sharingMemory, setSharingMemory] = useState<MemoryType | null>(null);
  const [isSharingModalOpen, setIsSharingModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isConfigPanelOpen, setIsConfigPanelOpen] = useState(false);
  const [useSemanticSearchResults, setUseSemanticSearchResults] =
    useState(false);
  const [reindexingMemoryId, setReindexingMemoryId] = useState<string | null>(
    null,
  );
  const [updatingMemoryId, setUpdatingMemoryId] = useState<string | null>(null);
  const [indexInspectingMemoryId, setIndexInspectingMemoryId] = useState<
    string | null
  >(null);
  const [indexInfoByMemoryId, setIndexInfoByMemoryId] = useState<
    Record<string, MemoryIndexInfo>
  >({});

  const tabDescriptionKey: Record<MemoryCategory, string> = {
    agent: "memory.description.agent",
    company: "memory.description.company",
    user_context: "memory.description.userContext",
  };

  const emptyKey: Record<MemoryCategory, string> = {
    agent: "memory.empty.agent",
    company: "memory.empty.company",
    user_context: "memory.empty.userContext",
  };

  // Fetch memories for a specific type (merges into store without clearing other types)
  const fetchMemoriesByType = useCallback(
    async (type: MemoryCategory) => {
      try {
        const data = await memoriesApi.getByType(type);
        setMemoriesByType(type, data);
      } catch {
        // Silently fail for background tab loading
      }
    },
    [setMemoriesByType],
  );

  // Load all tab counts on mount
  useEffect(() => {
    const types: MemoryCategory[] = ["agent", "company", "user_context"];
    types.forEach((type) => fetchMemoriesByType(type));
  }, [fetchMemoriesByType]);

  // Fetch active tab memories when tab changes
  const fetchActiveTabMemories = useCallback(async () => {
    setLoading(true);
    clearError();
    try {
      const data = await memoriesApi.getByType(activeTab);
      setMemoriesByType(activeTab, data);
    } catch (error: unknown) {
      setError(getErrorDetail(error) || t("memory.loadError"));
    } finally {
      setLoading(false);
    }
  }, [activeTab, setMemoriesByType, setLoading, setError, clearError, t]);

  useEffect(() => {
    fetchActiveTabMemories();
  }, [fetchActiveTabMemories]);

  // Debounced search
  useEffect(() => {
    const query = searchQuery.trim();
    if (!query) {
      setUseSemanticSearchResults(false);
      return;
    }

    // Company and user-context tabs use local keyword filtering
    // so users can still search when embedding services are unavailable.
    if (activeTab !== "agent") {
      setUseSemanticSearchResults(false);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      setUseSemanticSearchResults(true);
      try {
        const data = await memoriesApi.search({
          query,
          type: activeTab,
          limit: 50,
        });
        setMemoriesByType(activeTab, data);
      } catch {
        // Fallback to local keyword filtering if semantic search fails.
        setUseSemanticSearchResults(false);
      } finally {
        setLoading(false);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery, activeTab, setMemoriesByType, setLoading]);

  // Re-fetch when search is cleared
  useEffect(() => {
    if (searchQuery === "") {
      fetchActiveTabMemories();
    }
  }, [searchQuery, fetchActiveTabMemories]);

  // Get all unique tags for the current type
  const allTags = Array.from(
    new Set(
      memories.filter((m) => m.type === activeTab).flatMap((m) => m.tags),
    ),
  );

  // Filter memories locally (for date/tag filters)
  const filteredMemories = memories.filter((memory) => {
    if (memory.type !== activeTab) return false;
    if (dateFrom && new Date(memory.createdAt) < new Date(dateFrom))
      return false;
    if (dateTo && new Date(memory.createdAt) > new Date(dateTo)) return false;
    if (selectedTags.length > 0) {
      if (!selectedTags.some((tag) => memory.tags.includes(tag))) return false;
    }
    if (searchQuery.trim() && !useSemanticSearchResults) {
      const query = searchQuery.trim().toLowerCase();
      const summaryText = memory.summary?.toLowerCase() || "";
      const hasMatchingTag = memory.tags.some((tag) =>
        tag.toLowerCase().includes(query),
      );
      if (
        !memory.content.toLowerCase().includes(query) &&
        !summaryText.includes(query) &&
        !hasMatchingTag
      ) {
        return false;
      }
    }
    return true;
  });

  const handleMemoryClick = (memory: MemoryType) => {
    setSelectedMemory(memory);
    setIsDetailViewOpen(true);
  };

  const handleShare = (memory: MemoryType) => {
    setSharingMemory(memory);
    setIsSharingModalOpen(true);
  };

  const handleShareSubmit = async (
    memoryId: string,
    payload: { agentIds: string[]; userIds: string[] },
  ) => {
    try {
      const updated = await memoriesApi.share(memoryId, {
        agent_ids: payload.agentIds,
        user_ids: payload.userIds,
      });
      updateMemory(memoryId, updated);
      if (selectedMemory?.id === memoryId) {
        setSelectedMemory(updated);
      }
      fetchActiveTabMemories();
      toast.success(t("memory.share.success"));
    } catch (error: unknown) {
      toast.error(getErrorDetail(error) || t("memory.share.error"));
      throw error;
    }
  };

  const handleInspectIndex = async (memory: MemoryType) => {
    if (indexInspectingMemoryId) return;
    setIndexInspectingMemoryId(memory.id);
    try {
      const detail = await memoriesApi.getIndex(memory.id);
      setIndexInfoByMemoryId((prev) => ({
        ...prev,
        [memory.id]: detail,
      }));
    } catch (error: unknown) {
      toast.error(getErrorDetail(error) || t("memory.indexInspect.error"));
    } finally {
      setIndexInspectingMemoryId(null);
    }
  };

  const handleReindex = async (memory: MemoryType) => {
    if (reindexingMemoryId) return;
    setReindexingMemoryId(memory.id);
    try {
      const updated = await memoriesApi.reindex(memory.id);
      updateMemory(memory.id, updated);
      if (selectedMemory?.id === memory.id) {
        setSelectedMemory(updated);
      }
      setIndexInfoByMemoryId((prev) => {
        const next = { ...prev };
        delete next[memory.id];
        return next;
      });
      toast.success(t("memory.reindex.success"));
    } catch (error: unknown) {
      toast.error(getErrorDetail(error) || t("memory.reindex.error"));
    } finally {
      setReindexingMemoryId(null);
    }
  };

  const handleUpdateMemory = async (
    memory: MemoryType,
    updates: {
      content: string;
      summary?: string;
      tags: string[];
    },
    options: {
      reindexAfterSave: boolean;
    },
  ) => {
    if (updatingMemoryId) return;
    setUpdatingMemoryId(memory.id);
    try {
      const updated = await memoriesApi.update(memory.id, {
        content: updates.content,
        summary: updates.summary,
        tags: updates.tags,
      });
      updateMemory(memory.id, updated);
      if (selectedMemory?.id === memory.id) {
        setSelectedMemory(updated);
      }

      let finalMemory = updated;
      if (options.reindexAfterSave) {
        finalMemory = await memoriesApi.reindex(memory.id);
        updateMemory(memory.id, finalMemory);
        if (selectedMemory?.id === memory.id) {
          setSelectedMemory(finalMemory);
        }
        setIndexInfoByMemoryId((prev) => {
          const next = { ...prev };
          delete next[memory.id];
          return next;
        });
      }

      fetchMemoriesByType(activeTab);
      toast.success(
        options.reindexAfterSave
          ? t("memory.detail.saveAndReindexSuccess", "Memory updated and index rebuilt")
          : t("memory.detail.saveSuccess", "Memory updated"),
      );
    } catch (error: unknown) {
      toast.error(
        getErrorDetail(error) ||
          t("memory.detail.saveError", "Failed to update memory"),
      );
      throw error;
    } finally {
      setUpdatingMemoryId(null);
    }
  };

  const handleDelete = async (memory: MemoryType) => {
    try {
      await memoriesApi.delete(memory.id);
      removeMemory(memory.id);
      setIsDetailViewOpen(false);
      setSelectedMemory(null);
    } catch {
      // Delete failed
    }
  };

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  };

  const handleMemoryCreated = (memory: MemoryType) => {
    addMemory(memory);
    setActiveTab("company");
    setSearchQuery("");
    setDateFrom("");
    setDateTo("");
    setSelectedTags([]);
    setUseSemanticSearchResults(false);
    fetchMemoriesByType("company");
    toast.success(t("memory.create.success"));
  };

  const tabs = [
    {
      id: "agent" as MemoryCategory,
      label: t("memory.tabs.agent"),
      icon: Brain,
      color: "text-blue-500",
    },
    {
      id: "company" as MemoryCategory,
      label: t("memory.tabs.company"),
      icon: Building,
      color: "text-green-500",
    },
    {
      id: "user_context" as MemoryCategory,
      label: t("memory.tabs.userContext"),
      icon: User,
      color: "text-purple-500",
    },
  ];
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-zinc-800 dark:text-white">
          {t("memory.title")}
        </h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsConfigPanelOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
          >
            <Settings2 className="w-5 h-5" />
            {t("memory.config.manage", "Config")}
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium"
          >
            <Plus className="w-5 h-5" />
            {t("memory.newMemory")}
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-600 dark:text-red-400">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
          <button onClick={clearError} className="ml-auto">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-4 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const count = memories.filter((m) => m.type === tab.id).length;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 rounded-lg transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? "bg-indigo-500 text-white"
                  : "glass text-gray-700 dark:text-gray-300 hover:bg-white/30 dark:hover:bg-black/30"
              }`}
            >
              <Icon
                className={`w-5 h-5 ${activeTab === tab.id ? "text-white" : tab.color}`}
              />
              <span className="font-medium">{tab.label}</span>
              <span
                className={`px-2 py-0.5 rounded-full text-xs ${
                  activeTab === tab.id
                    ? "bg-white/20"
                    : "bg-black/10 dark:bg-white/10"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Tab description */}
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        {t(tabDescriptionKey[activeTab])}
      </p>

      {/* Search Bar */}
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

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
        </div>
      )}

      {/* Memory Grid */}
      {!isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredMemories.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <p className="text-gray-500 dark:text-gray-400">
                {memories.filter((m) => m.type === activeTab).length === 0
                  ? t(emptyKey[activeTab])
                  : t("memory.noResults")}
              </p>
            </div>
          ) : (
            filteredMemories.map((memory) => (
              <MemoryCard
                key={memory.id}
                memory={memory}
                onClick={handleMemoryClick}
                showRelevance={memory.type === "agent"}
                onReindex={handleReindex}
                isReindexing={reindexingMemoryId === memory.id}
              />
            ))
          )}
        </div>
      )}

      {/* Modals */}
      <MemoryDetailView
        key={selectedMemory?.id || "memory-detail"}
        memory={selectedMemory}
        isOpen={isDetailViewOpen}
        onClose={() => {
          setIsDetailViewOpen(false);
          setSelectedMemory(null);
        }}
        onShare={handleShare}
        onDelete={handleDelete}
        onUpdate={handleUpdateMemory}
        onReindex={handleReindex}
        onInspectIndex={handleInspectIndex}
        isUpdating={
          selectedMemory ? updatingMemoryId === selectedMemory.id : false
        }
        isReindexing={
          selectedMemory ? reindexingMemoryId === selectedMemory.id : false
        }
        isInspectingIndex={
          selectedMemory
            ? indexInspectingMemoryId === selectedMemory.id
            : false
        }
        indexInfo={
          selectedMemory ? indexInfoByMemoryId[selectedMemory.id] || null : null
        }
      />
      <MemorySharingModal
        memory={sharingMemory}
        isOpen={isSharingModalOpen}
        onClose={() => {
          setIsSharingModalOpen(false);
          setSharingMemory(null);
        }}
        onShare={handleShareSubmit}
      />
      <CreateMemoryModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreated={handleMemoryCreated}
      />
      <MemoryConfigPanel
        isOpen={isConfigPanelOpen}
        onClose={() => setIsConfigPanelOpen(false)}
      />
    </div>
  );
};
