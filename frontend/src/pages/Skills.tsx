import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CheckCircle2,
  Inbox,
  Link2,
  Loader2,
  Package,
  Plug,
  Plus,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import SkillCardV2 from "@/components/skills/SkillCardV2";
import AddSkillModalV2 from "@/components/skills/AddSkillModalV2";
import EditSkillModal from "@/components/skills/EditSkillModal";
import AgentSkillViewer from "@/components/skills/AgentSkillViewer";
import SkillTesterModal from "@/components/skills/SkillTesterModal";
import BindSkillModal from "@/components/skills/BindSkillModal";
import McpServerCard from "@/components/skills/McpServerCard";
import AddMcpServerModal from "@/components/skills/AddMcpServerModal";
import EditMcpServerModal from "@/components/skills/EditMcpServerModal";
import { agentsApi } from "@/api";
import {
  mcpServersApi,
  type McpServer,
} from "@/api/mcpServers";
import {
  skillsApi,
  type CreateSkillRequest,
  type Skill,
  type SkillBinding,
  type SkillCandidate,
  type SkillOverviewStats,
  type StoreSkill,
  type AgentSkillBindingDraft,
} from "@/api/skills";
import type { Agent } from "@/types/agent";

type SkillsSection = "inbox" | "library" | "store" | "bindings" | "mcp_servers";

const SECTION_PARAM = "section";
const LIBRARY_PAGE_SIZE = 24;

const getSectionFromSearchParam = (value: string | null): SkillsSection => {
  if (value === "inbox" || value === "store" || value === "bindings" || value === "mcp_servers") {
    return value;
  }
  return "library";
};

const buildOverviewStatsFromSkills = (skills: Skill[]): SkillOverviewStats => {
  const activeSkills = skills.filter(
    (skill) => skill.is_active !== false,
  ).length;
  const skillsWithDependencies = skills.filter(
    (skill) =>
      Array.isArray(skill.dependencies) && skill.dependencies.length > 0,
  ).length;
  const totalExecutionCount = skills.reduce(
    (total, skill) => total + (skill.execution_count ?? 0),
    0,
  );
  const averageExecutionTimeSamples = skills.filter(
    (skill) =>
      (skill.execution_count ?? 0) > 0 &&
      typeof skill.average_execution_time === "number",
  );
  const averageExecutionTime = averageExecutionTimeSamples.length
    ? averageExecutionTimeSamples.reduce(
        (total, skill) => total + (skill.average_execution_time ?? 0),
        0,
      ) / averageExecutionTimeSamples.length
    : 0;

  return {
    total_skills: skills.length,
    active_skills: activeSkills,
    inactive_skills: Math.max(skills.length - activeSkills, 0),
    agent_skills: skills.filter((skill) => skill.skill_type === "agent_skill")
      .length,
    langchain_tool_skills: skills.filter(
      (skill) => skill.skill_type === "langchain_tool",
    ).length,
    skills_with_dependencies: skillsWithDependencies,
    total_execution_count: totalExecutionCount,
    average_execution_time: averageExecutionTime,
    last_executed_at: null,
  };
};

const normalizeSearchValue = (value: string): string =>
  value.trim().toLowerCase();

const formatDateTime = (value?: string | null): string => {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

const statusBadgeClassName = (status: string): string => {
  switch (status) {
    case "published":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "rejected":
      return "bg-rose-500/10 text-rose-700 dark:text-rose-300";
    default:
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
};

const matchesCandidateSearch = (
  candidate: SkillCandidate,
  query: string,
): boolean => {
  if (!query) {
    return true;
  }
  const searchSpace = [
    candidate.title,
    candidate.summary,
    candidate.content,
    candidate.skill_slug || "",
    candidate.source_agent_name || "",
    ...(candidate.tags || []),
  ]
    .join("\n")
    .toLowerCase();
  return searchSpace.includes(query);
};

const getSkillTypeLabel = (
  t: TFunction,
  skillType?: string | null,
): string | null => {
  switch (skillType) {
    case "langchain_tool":
      return t("skills.langchainTool");
    case "agent_skill":
      return t("skills.agentSkill");
    case "mcp_tool":
      return t("skills.mcpTool", "MCP Tool");
    default:
      return skillType || null;
  }
};

const getCandidateStatusLabel = (
  t: TFunction,
  status: string,
): string => {
  switch (status) {
    case "published":
      return t("skills.candidateStatusPublished");
    case "rejected":
      return t("skills.candidateStatusRejected");
    case "revise":
      return t("skills.candidateStatusRevise");
    default:
      return t("skills.candidateStatusPending");
  }
};

const getBindingSourceLabel = (
  t: TFunction,
  source?: string | null,
): string => {
  switch (source) {
    case "auto_learned":
      return t("skills.bindingSourceAutoLearned");
    case "template_default":
      return t("skills.bindingSourceTemplateDefault");
    default:
      return t("skills.bindingSourceManual");
  }
};

const getOwnerTypeLabel = (
  t: TFunction,
  ownerType: string,
): string => {
  if (ownerType === "agent") {
    return t("skills.bindingOwnerTypeAgent");
  }
  return ownerType;
};

const matchesBindingSearch = (
  binding: SkillBinding,
  query: string,
): boolean => {
  if (!query) {
    return true;
  }
  const searchSpace = [
    binding.owner_name,
    binding.owner_type,
    binding.display_name,
    binding.skill_slug,
    binding.skill_type || "",
  ]
    .join("\n")
    .toLowerCase();
  return searchSpace.includes(query);
};

const groupBindingsByOwner = (bindings: SkillBinding[]) => {
  const groups = new Map<
    string,
    {
      ownerId: string;
      ownerName: string;
      ownerType: string;
      bindings: SkillBinding[];
    }
  >();

  for (const binding of bindings) {
    const key = `${binding.owner_type}:${binding.owner_id}`;
    const existing = groups.get(key);
    if (existing) {
      existing.bindings.push(binding);
      continue;
    }
    groups.set(key, {
      ownerId: binding.owner_id,
      ownerName: binding.owner_name,
      ownerType: binding.owner_type,
      bindings: [binding],
    });
  }

  return Array.from(groups.values()).sort((left, right) =>
    left.ownerName.localeCompare(right.ownerName),
  );
};

export default function Skills() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeSection = getSectionFromSearchParam(
    searchParams.get(SECTION_PARAM),
  );

  const [skills, setSkills] = useState<Skill[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryPage, setLibraryPage] = useState(1);
  const [overviewStats, setOverviewStats] = useState<SkillOverviewStats | null>(
    null,
  );
  const [candidates, setCandidates] = useState<SkillCandidate[]>([]);
  const [bindings, setBindings] = useState<SkillBinding[]>([]);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [bindingsError, setBindingsError] = useState<string | null>(null);
  const [isLibraryLoading, setIsLibraryLoading] = useState(true);
  const [isCandidatesLoading, setIsCandidatesLoading] = useState(true);
  const [isBindingsLoading, setIsBindingsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [candidateActionId, setCandidateActionId] = useState<string | null>(
    null,
  );
  const [librarySearchQuery, setLibrarySearchQuery] = useState("");
  const [candidateSearchQuery, setCandidateSearchQuery] = useState("");
  const [bindingSearchQuery, setBindingSearchQuery] = useState("");
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isAgentSkillViewerOpen, setIsAgentSkillViewerOpen] = useState(false);
  const [isTesterModalOpen, setIsTesterModalOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [selectedSkillMode, setSelectedSkillMode] = useState<"view" | "edit">(
    "edit",
  );
  const [storeSkills, setStoreSkills] = useState<StoreSkill[]>([]);
  const [isStoreLoading, setIsStoreLoading] = useState(true);
  const [storeLoadError, setStoreLoadError] = useState<string | null>(null);
  const [storeActionError, setStoreActionError] = useState<string | null>(null);
  const [storeActionSkillId, setStoreActionSkillId] = useState<string | null>(null);
  const [storeAgents, setStoreAgents] = useState<Agent[]>([]);
  const [isBindModalOpen, setIsBindModalOpen] = useState(false);
  const [bindTargetSkill, setBindTargetSkill] = useState<StoreSkill | null>(null);
  const [selectedBindAgentIds, setSelectedBindAgentIds] = useState<string[]>([]);
  const [bindInitiallyHadSelection, setBindInitiallyHadSelection] = useState(false);
  const [isAgentsLoading, setIsAgentsLoading] = useState(false);
  const [isBindingSkill, setIsBindingSkill] = useState(false);
  const [bindError, setBindError] = useState<string | null>(null);

  // MCP servers state
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [isMcpLoading, setIsMcpLoading] = useState(true);
  const [isAddMcpModalOpen, setIsAddMcpModalOpen] = useState(false);
  const [editingMcpServer, setEditingMcpServer] = useState<McpServer | null>(null);
  const libraryRequestSequence = useRef(0);
  const trimmedLibrarySearchQuery = librarySearchQuery.trim();
  const deferredLibrarySearchQuery = useDeferredValue(trimmedLibrarySearchQuery);
  const isLibrarySearchPending =
    trimmedLibrarySearchQuery !== deferredLibrarySearchQuery;

  useEffect(() => {
    void loadAuxiliaryData();
  }, []);

  useEffect(() => {
    if (isLibrarySearchPending) {
      return;
    }
    void loadLibraryPage({
      page: libraryPage,
      query: deferredLibrarySearchQuery,
    });
  }, [deferredLibrarySearchQuery, isLibrarySearchPending, libraryPage]);

  const setSection = (section: SkillsSection) => {
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.set(SECTION_PARAM, section);
    setSearchParams(nextSearchParams);
  };

  const loadLibraryPage = async ({
    page,
    query,
  }: {
    page: number;
    query: string;
  }) => {
    const requestId = ++libraryRequestSequence.current;

    setIsLibraryLoading(true);
    setLibraryError(null);

    try {
      const result = await skillsApi.listPage({
        limit: LIBRARY_PAGE_SIZE,
        offset: (page - 1) * LIBRARY_PAGE_SIZE,
        includeCode: false,
        query: query || undefined,
      });

      if (requestId !== libraryRequestSequence.current) {
        return;
      }

      setSkills(result.items);
      setLibraryTotal(result.total);
    } catch (error) {
      if (requestId !== libraryRequestSequence.current) {
        return;
      }

      console.error("Failed to load skills library:", error);
      setSkills([]);
      setLibraryTotal(0);
      setLibraryError(
        t("skills.loadError", {
          defaultValue: "Failed to load skills library.",
        }),
      );
    } finally {
      if (requestId === libraryRequestSequence.current) {
        setIsLibraryLoading(false);
      }
    }
  };

  const loadAuxiliaryData = async () => {
    setIsCandidatesLoading(true);
    setIsBindingsLoading(true);
    setIsMcpLoading(true);
    setIsStoreLoading(true);
    setCandidatesError(null);
    setBindingsError(null);
    setStoreLoadError(null);

    const [candidatesResult, bindingsResult, overviewResult, mcpResult, storeResult] =
      await Promise.allSettled([
        skillsApi.getCandidates({ status: "all", limit: 100 }),
        skillsApi.getBindings({ limit: 200 }),
        skillsApi.getOverviewStats(),
        mcpServersApi.getAll(false),
        skillsApi.getStore(),
      ]);

    if (overviewResult.status === "fulfilled") {
      setOverviewStats(overviewResult.value);
    }

    if (candidatesResult.status === "fulfilled") {
      setCandidates(candidatesResult.value);
    } else {
      setCandidatesError(
        t("skills.loadInboxError", {
          defaultValue: "Failed to load skill inbox.",
        }),
      );
    }
    setIsCandidatesLoading(false);

    if (bindingsResult.status === "fulfilled") {
      setBindings(bindingsResult.value);
    } else {
      setBindingsError(
        t("skills.loadBindingsError", {
          defaultValue: "Failed to load skill bindings.",
        }),
      );
    }
    setIsBindingsLoading(false);

    if (mcpResult.status === "fulfilled") {
      setMcpServers(mcpResult.value);
    }
    setIsMcpLoading(false);

    if (storeResult.status === "fulfilled") {
      setStoreSkills(storeResult.value);
    } else {
      setStoreLoadError(
        t("skills.loadStoreError", {
          defaultValue: "Failed to load official skill store.",
        }),
      );
    }
    setIsStoreLoading(false);
  };

  const loadPageData = async ({
    page = libraryPage,
    query = trimmedLibrarySearchQuery,
  }: {
    page?: number;
    query?: string;
  } = {}) => {
    setIsRefreshing(true);
    try {
      await Promise.all([
        loadAuxiliaryData(),
        loadLibraryPage({
          page,
          query: query ?? "",
        }),
      ]);
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleCreateSkill = async (data: CreateSkillRequest) => {
    await skillsApi.create(data);
    startTransition(() => {
      setLibraryPage(1);
    });
    await loadPageData({ page: 1 });
  };

  const handleEditSkill = async (skill: Skill) => {
    try {
      const resolvedSkill =
        skill.skill_type === "agent_skill" || typeof skill.code === "string"
          ? skill
          : await skillsApi.getById(skill.skill_id);

      setSelectedSkill(resolvedSkill);
      setSelectedSkillMode(skill.can_edit ? "edit" : "view");
      if (resolvedSkill.skill_type === "agent_skill") {
        setIsAgentSkillViewerOpen(true);
      } else {
        setIsEditModalOpen(true);
      }
    } catch (error) {
      console.error("Failed to load skill details:", error);
    }
  };

  const handleUpdateSkill = async (skillId: string, data: any) => {
    await skillsApi.update(skillId, data);
    await loadPageData();
  };

  const handleDeleteSkill = async (skillId: string) => {
    if (!confirm(t("skills.deleteConfirm"))) {
      return;
    }
    await skillsApi.delete(skillId);
    await loadPageData();
  };

  const handleToggleActive = async (
    skillId: string,
    currentlyActive: boolean,
  ) => {
    if (currentlyActive) {
      await skillsApi.deactivateSkill(skillId);
    } else {
      await skillsApi.activateSkill(skillId);
    }
    await loadPageData();
  };

  const handleTestSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    setIsTesterModalOpen(true);
  };

  const handleInstallStoreSkill = async (skill: StoreSkill) => {
    setStoreActionSkillId(skill.skill_id);
    setStoreActionError(null);
    try {
      await skillsApi.installSkill(skill.skill_id);
      await loadPageData();
    } catch (error) {
      console.error("Failed to install curated skill:", error);
      setStoreActionError(
        t("skills.installError", {
          defaultValue: "Failed to install this official skill.",
        }),
      );
    } finally {
      setStoreActionSkillId(null);
    }
  };

  const openBindSkillModal = async (skill: StoreSkill) => {
    setBindTargetSkill(skill);
    setSelectedBindAgentIds([]);
    setBindInitiallyHadSelection(false);
    setBindError(null);
    setIsBindModalOpen(true);
    setIsAgentsLoading(true);
    try {
      const agents = await agentsApi.getAll();
      const manageableAgents = agents.filter((agent) => agent.canManage !== false);
      setStoreAgents(manageableAgents);
      const preselectedAgentIds = skill.installed_skill_id
        ? bindings
            .filter(
              (binding) =>
                binding.owner_type === 'agent' && binding.skill_id === skill.installed_skill_id,
            )
            .map((binding) => binding.owner_id)
        : [];
      setSelectedBindAgentIds(preselectedAgentIds);
      setBindInitiallyHadSelection(preselectedAgentIds.length > 0);
    } catch (error) {
      console.error("Failed to load agents for binding:", error);
      setStoreAgents([]);
      setBindError(
        t("skills.loadAgentsError", {
          defaultValue: "Failed to load available agents.",
        }),
      );
    } finally {
      setIsAgentsLoading(false);
    }
  };

  const closeBindSkillModal = () => {
    setIsBindModalOpen(false);
    setBindTargetSkill(null);
    setSelectedBindAgentIds([]);
    setBindInitiallyHadSelection(false);
    setBindError(null);
    setIsAgentsLoading(false);
    setIsBindingSkill(false);
  };

  const buildBindingMode = (runtimeMode?: string | null): AgentSkillBindingDraft["binding_mode"] => {
    if (runtimeMode === "tool" || runtimeMode === "doc" || runtimeMode === "retrieval" || runtimeMode === "hybrid") {
      return runtimeMode;
    }
    return "doc";
  };

  const handleBindSkillToAgent = async () => {
    if (!bindTargetSkill) {
      return;
    }
    setIsBindingSkill(true);
    setBindError(null);
    try {
      let installedSkillId = bindTargetSkill.installed_skill_id || null;
      if (!installedSkillId) {
        const installResult = await skillsApi.installSkill(bindTargetSkill.skill_id);
        installedSkillId = installResult.installed_skill_id;
      }
      if (!installedSkillId) {
        throw new Error("Installed skill ID is missing after install.");
      }

      const currentlyBoundAgentIds = bindings
        .filter(
          (binding) =>
            binding.owner_type === 'agent' && binding.skill_id === installedSkillId,
        )
        .map((binding) => binding.owner_id);
      const affectedAgentIds = Array.from(
        new Set([...currentlyBoundAgentIds, ...selectedBindAgentIds]),
      );

      for (const agentId of affectedAgentIds) {
        const bindingConfig = await skillsApi.getAgentBindings(agentId);
        const shouldBind = selectedBindAgentIds.includes(agentId);
        const nextBindings = [...bindingConfig.bindings];
        const existingIndex = nextBindings.findIndex((binding) => binding.skill_id === installedSkillId);
        if (shouldBind && existingIndex >= 0) {
          nextBindings[existingIndex] = {
            ...nextBindings[existingIndex],
            enabled: true,
            binding_mode: buildBindingMode(bindTargetSkill.runtime_mode),
          };
        } else if (shouldBind) {
          const maxPriority = nextBindings.reduce(
            (maxValue, binding) => Math.max(maxValue, binding.priority ?? 0),
            -1,
          );
          nextBindings.push({
            skill_id: installedSkillId,
            binding_mode: buildBindingMode(bindTargetSkill.runtime_mode),
            enabled: true,
            priority: maxPriority + 1,
            source: "manual",
            auto_update_policy: "follow_active",
            revision_pin_id: null,
          });
        } else {
          const filteredBindings = nextBindings.filter((binding) => binding.skill_id !== installedSkillId);
          await skillsApi.updateAgentBindings(agentId, filteredBindings);
          continue;
        }

        await skillsApi.updateAgentBindings(agentId, nextBindings);
      }
      closeBindSkillModal();
      await loadPageData();
    } catch (error) {
      console.error("Failed to bind skill to agent:", error);
      setBindError(
        t("skills.bindError", {
          defaultValue: "Failed to bind this skill to the selected agent.",
        }),
      );
      setIsBindingSkill(false);
    }
  };

  const handleUninstallStoreSkill = async (skill: StoreSkill) => {
    setStoreActionSkillId(skill.skill_id);
    setStoreActionError(null);
    try {
      await skillsApi.uninstallSkill(skill.skill_id);
      await loadPageData();
    } catch (error) {
      console.error("Failed to uninstall curated skill:", error);
      setStoreActionError(
        t("skills.uninstallError", {
          defaultValue: "Failed to uninstall this official skill.",
        }),
      );
    } finally {
      setStoreActionSkillId(null);
    }
  };

  const handleReviewCandidate = async (
    candidateId: string,
    action: "approve" | "reject",
  ) => {
    setCandidateActionId(candidateId);
    try {
      if (action === "approve") {
        await skillsApi.promoteCandidate(candidateId, {
          auto_bind_source_agent: true,
        });
      } else {
        await skillsApi.rejectCandidate(candidateId);
      }
      await loadPageData();
    } finally {
      setCandidateActionId(null);
    }
  };

  const resolvedOverviewStats = overviewStats
    ? overviewStats
    : {
        ...buildOverviewStatsFromSkills(skills),
        total_skills: Math.max(libraryTotal, skills.length),
      };
  const candidateQuery = normalizeSearchValue(candidateSearchQuery);
  const bindingQuery = normalizeSearchValue(bindingSearchQuery);
  const libraryTotalPages = Math.max(1, Math.ceil(libraryTotal / LIBRARY_PAGE_SIZE));
  const libraryDisplayStart =
    libraryTotal === 0 ? 0 : (libraryPage - 1) * LIBRARY_PAGE_SIZE + 1;
  const libraryDisplayEnd =
    libraryTotal === 0
      ? 0
      : Math.min(libraryTotal, libraryPage * LIBRARY_PAGE_SIZE);

  const filteredCandidates = useMemo(() => {
    return candidates.filter((candidate) =>
      matchesCandidateSearch(candidate, candidateQuery),
    );
  }, [candidateQuery, candidates]);

  const filteredBindings = useMemo(() => {
    return bindings.filter((binding) =>
      matchesBindingSearch(binding, bindingQuery),
    );
  }, [bindingQuery, bindings]);

  const bindingGroups = useMemo(
    () => groupBindingsByOwner(filteredBindings),
    [filteredBindings],
  );

  const pendingCandidateCount = candidates.filter(
    (candidate) =>
      candidate.status === "pending" || candidate.status === "revise",
  ).length;
  const totalBindingsCount = bindings.length;
  const boundOwnerCount = useMemo(
    () =>
      new Set(
        bindings.map((binding) => `${binding.owner_type}:${binding.owner_id}`),
      ).size,
    [bindings],
  );

  useEffect(() => {
    if (libraryPage > libraryTotalPages) {
      startTransition(() => {
        setLibraryPage(libraryTotalPages);
      });
    }
  }, [libraryPage, libraryTotalPages]);

  const sectionTabs: Array<{
    id: SkillsSection;
    label: string;
    icon: typeof Inbox;
    count: number;
  }> = [
    {
      id: "inbox",
      label: t("skills.sectionInbox"),
      icon: Inbox,
      count: pendingCandidateCount,
    },
    {
      id: "library",
      label: t("skills.sectionLibrary"),
      icon: Package,
      count: resolvedOverviewStats.total_skills,
    },
    {
      id: "store",
      label: t("skills.sectionStore", "Skill Store"),
      icon: Package,
      count: storeSkills.length,
    },
    {
      id: "bindings",
      label: t("skills.sectionBindings"),
      icon: Link2,
      count: totalBindingsCount,
    },
    {
      id: "mcp_servers",
      label: t("skills.sectionMcpServers", "MCP Servers"),
      icon: Plug,
      count: mcpServers.length,
    },
  ];

  return (
    <div>
      <div className="mx-auto max-w-7xl space-y-6 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white/80 px-3 py-1 text-sm text-zinc-700 shadow-sm dark:border-zinc-700 dark:bg-zinc-900/70 dark:text-zinc-200">
              <Inbox className="h-4 w-4 text-emerald-600 dark:text-emerald-300" />
              <span>{t("skills.title")}</span>
            </div>
            <div>
              <h1 className="bg-gradient-to-r from-emerald-600 to-cyan-600 bg-clip-text text-3xl font-bold text-transparent">
                {t("skills.title")}
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                {t("skills.pageSummary")}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => void loadPageData()}
              disabled={isRefreshing}
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
              />
              {t("skills.refresh")}
            </button>
            {activeSection === "library" && (
              <button
                onClick={() => setIsAddModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-5 py-2.5 text-sm font-medium text-white shadow-lg transition-transform hover:-translate-y-0.5"
              >
                <Plus className="h-4 w-4" />
                {t("skills.addSkill")}
              </button>
            )}
            {activeSection === "mcp_servers" && (
              <button
                onClick={() => setIsAddMcpModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-5 py-2.5 text-sm font-medium text-white shadow-lg transition-transform hover:-translate-y-0.5"
              >
                <Plus className="h-4 w-4" />
                {t("skills.mcpAddServer", "Add MCP Server")}
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <div className="glass-panel rounded-xl border border-border/40 px-4 py-3 shadow-sm">
            <div className="text-xs font-medium text-muted-foreground">
              {t("skills.overviewInboxPending")}
            </div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {pendingCandidateCount.toLocaleString()}
            </div>
          </div>
          <div className="glass-panel rounded-xl border border-border/40 px-4 py-3 shadow-sm">
            <div className="text-xs font-medium text-muted-foreground">
              {t("skills.overviewLibrarySkills")}
            </div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {resolvedOverviewStats.total_skills.toLocaleString()}
            </div>
          </div>
          <div className="glass-panel rounded-xl border border-border/40 px-4 py-3 shadow-sm">
            <div className="text-xs font-medium text-muted-foreground">
              {t("skills.overviewActiveSkills")}
            </div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {resolvedOverviewStats.active_skills.toLocaleString()}
            </div>
          </div>
          <div className="glass-panel rounded-xl border border-border/40 px-4 py-3 shadow-sm">
            <div className="text-xs font-medium text-muted-foreground">
              {t("skills.overviewBoundAgents")}
            </div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {boundOwnerCount.toLocaleString()}
            </div>
          </div>
        </div>

        <div className="inline-flex rounded-2xl border border-zinc-200 bg-white/80 p-1 shadow-sm dark:border-zinc-700 dark:bg-zinc-900/70">
          {sectionTabs.map((tab) => {
            const TabIcon = tab.icon;
            const isActive = activeSection === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setSection(tab.id)}
                className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-emerald-500 text-white"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                }`}
              >
                <TabIcon className="h-4 w-4" />
                <span>{tab.label}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    isActive
                      ? "bg-white/20 text-white"
                      : "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200"
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        {activeSection === "inbox" && (
          <section className="space-y-4">
            <div className="glass-panel rounded-2xl p-6 shadow-xl">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-foreground">
                    {t("skills.inboxTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t("skills.inboxDescription")}
                  </p>
                </div>
                <div className="relative w-full lg:max-w-md">
                  <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={candidateSearchQuery}
                    onChange={(event) =>
                      setCandidateSearchQuery(event.target.value)
                    }
                    placeholder={t("skills.inboxSearchPlaceholder")}
                    className="w-full rounded-xl border border-border/50 bg-muted/30 py-3 pl-11 pr-4 text-sm text-foreground outline-none transition-colors focus:border-emerald-500"
                  />
                </div>
              </div>
            </div>

            {candidatesError ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
                {candidatesError}
              </div>
            ) : isCandidatesLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              </div>
            ) : filteredCandidates.length === 0 ? (
              <div className="glass-panel rounded-2xl p-16 text-center shadow-xl">
                <Inbox className="mx-auto h-10 w-10 text-muted-foreground" />
                <p className="mt-4 text-sm text-muted-foreground">
                  {t("skills.inboxEmpty")}
                </p>
              </div>
            ) : (
              <div className="grid gap-4">
                {filteredCandidates.map((candidate) => {
                  const isBusy = candidateActionId === candidate.candidate_id;
                  return (
                    <article
                      key={candidate.candidate_id}
                      className="glass-panel rounded-2xl border border-border/40 p-5 shadow-sm"
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-lg font-semibold text-foreground">
                              {candidate.title}
                            </h3>
                            <span
                              className={`rounded-full px-2 py-1 text-xs font-medium ${statusBadgeClassName(candidate.status)}`}
                            >
                              {getCandidateStatusLabel(t, candidate.status)}
                            </span>
                            {candidate.skill_type && (
                              <span className="rounded-full bg-zinc-500/10 px-2 py-1 text-xs text-zinc-600 dark:text-zinc-300">
                                {getSkillTypeLabel(t, candidate.skill_type)}
                              </span>
                            )}
                          </div>
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            {candidate.summary}
                          </p>
                          {candidate.content &&
                            candidate.content.trim() !==
                              candidate.summary.trim() && (
                              <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-600 dark:text-zinc-300">
                                {candidate.content}
                              </p>
                            )}
                          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                            <span>
                              {formatDateTime(
                                candidate.updated_at || candidate.created_at,
                              )}
                            </span>
                            {candidate.source_agent_name && (
                              <span>{candidate.source_agent_name}</span>
                            )}
                            {candidate.skill_slug && (
                              <span>{candidate.skill_slug}</span>
                            )}
                          </div>
                          {candidate.tags.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {candidate.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="rounded-full bg-zinc-500/10 px-2 py-1 text-xs text-zinc-600 dark:text-zinc-300"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                          {candidate.source_agent_name && (
                            <p className="mt-3 text-xs text-emerald-700 dark:text-emerald-300">
                              {t("skills.candidateAutoBindHint", {
                                agentName: candidate.source_agent_name,
                              })}
                            </p>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              void handleReviewCandidate(
                                candidate.candidate_id,
                                "reject",
                              )
                            }
                            disabled={isBusy || candidate.status === "rejected"}
                            className="inline-flex items-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-600 transition-colors hover:bg-rose-50 disabled:opacity-50 dark:border-rose-500/30 dark:text-rose-300 dark:hover:bg-rose-500/10"
                          >
                            {isBusy ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <XCircle className="h-4 w-4" />
                            )}
                            {t("skills.rejectCandidate")}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              void handleReviewCandidate(
                                candidate.candidate_id,
                                "approve",
                              )
                            }
                            disabled={
                              isBusy || candidate.status === "published"
                            }
                            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm text-white transition-colors hover:bg-emerald-600 disabled:opacity-50"
                          >
                            {isBusy ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <CheckCircle2 className="h-4 w-4" />
                            )}
                            {t("skills.approveCandidate")}
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {activeSection === "library" && (
          <section className="space-y-4">
            <div className="glass-panel rounded-2xl p-6 shadow-xl">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-foreground">
                    {t("skills.libraryTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t("skills.libraryDescription")}
                  </p>
                </div>
                <div className="relative w-full lg:max-w-md">
                  <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  {isLibrarySearchPending && (
                    <Loader2 className="absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
                  )}
                  <input
                    type="text"
                    value={librarySearchQuery}
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      startTransition(() => {
                        setLibrarySearchQuery(nextValue);
                        setLibraryPage(1);
                      });
                    }}
                    placeholder={t("skills.searchPlaceholder")}
                    className="w-full rounded-xl border border-border/50 bg-muted/30 py-3 pl-11 pr-11 text-sm text-foreground outline-none transition-colors focus:border-emerald-500"
                  />
                </div>
              </div>

              <div className="mt-4 flex flex-col gap-3 border-t border-border/40 pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-muted-foreground">
                  {t("skills.libraryPaginationSummary", {
                    start: libraryDisplayStart,
                    end: libraryDisplayEnd,
                    total: libraryTotal,
                    defaultValue: "Showing {{start}}-{{end}} of {{total}} skills",
                  })}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      startTransition(() => {
                        setLibraryPage((currentPage) => Math.max(1, currentPage - 1));
                      })
                    }
                    disabled={isLibraryLoading || libraryPage <= 1}
                    className="rounded-lg border border-border/50 px-3 py-2 text-sm text-foreground transition-colors hover:bg-muted/40 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {t("skills.libraryPrevPage", { defaultValue: "Previous" })}
                  </button>
                  <span className="min-w-32 text-center text-sm text-muted-foreground">
                    {t("skills.libraryPageIndicator", {
                      page: libraryPage,
                      totalPages: libraryTotalPages,
                      defaultValue: "Page {{page}} / {{totalPages}}",
                    })}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      startTransition(() => {
                        setLibraryPage((currentPage) =>
                          Math.min(libraryTotalPages, currentPage + 1),
                        );
                      })
                    }
                    disabled={
                      isLibraryLoading ||
                      libraryTotal === 0 ||
                      libraryPage >= libraryTotalPages
                    }
                    className="rounded-lg border border-border/50 px-3 py-2 text-sm text-foreground transition-colors hover:bg-muted/40 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {t("skills.libraryNextPage", { defaultValue: "Next" })}
                  </button>
                </div>
              </div>
            </div>

            {libraryError ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
                {libraryError}
              </div>
            ) : isLibraryLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              </div>
            ) : skills.length === 0 ? (
              <div className="glass-panel rounded-2xl p-16 text-center shadow-xl">
                <Package className="mx-auto h-10 w-10 text-muted-foreground" />
                <p className="mt-4 text-sm text-muted-foreground">
                  {librarySearchQuery
                    ? t("skills.noSkillsFound")
                    : t("skills.noSkillsYet")}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                {skills.map((skill) => (
                  <SkillCardV2
                    key={skill.skill_id}
                    skill={skill}
                    onEdit={(selected) => {
                      void handleEditSkill(selected);
                    }}
                    onDelete={handleDeleteSkill}
                    onToggleActive={handleToggleActive}
                    onTest={handleTestSkill}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {activeSection === "store" && (
          <section className="space-y-4">
            <div className="glass-panel rounded-2xl p-6 shadow-xl">
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  {t("skills.storeTitle", { defaultValue: "Official Skill Store" })}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("skills.storeDescription", {
                    defaultValue:
                      "Browse official curated skills. Install adds the skill to your library; uninstall removes your installed copy.",
                  })}
                </p>
              </div>
            </div>

            {storeLoadError ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
                {storeLoadError}
              </div>
            ) : isStoreLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              </div>
            ) : storeSkills.length === 0 ? (
              <div className="glass-panel rounded-2xl p-16 text-center shadow-xl">
                <Package className="mx-auto h-10 w-10 text-muted-foreground" />
                <p className="mt-4 text-sm text-muted-foreground">
                  {t("skills.storeEmpty", { defaultValue: "No official skills available right now." })}
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {storeActionError ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
                    {storeActionError}
                  </div>
                ) : null}
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                {storeSkills.map((skill) => {
                  const isBusy = storeActionSkillId === skill.skill_id;
                  const bindingCount = skill.installed_binding_count ?? 0;
                  const uninstallDisabled = isBusy || bindingCount > 0;
                  return (
                    <article
                      key={skill.skill_id}
                      className="glass-panel rounded-2xl border border-border/40 p-6 shadow-xl"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-lg font-semibold text-foreground">{skill.display_name}</h3>
                          <p className="mt-1 text-xs font-mono text-muted-foreground">{skill.skill_slug}</p>
                        </div>
                        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                          {t("skills.officialCurated", { defaultValue: "Official" })}
                        </span>
                      </div>
                      <p className="mt-4 text-sm text-muted-foreground">{skill.description}</p>
                      <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        {skill.runtime_mode ? <span>{skill.runtime_mode}</span> : null}
                        {skill.artifact_kind ? <span>· {skill.artifact_kind}</span> : null}
                        <span>· v{skill.version}</span>
                        {skill.is_installed && bindingCount > 0 ? (
                          <span>· {t("skills.storeBoundAgentsCount", { defaultValue: "Bound to {{count}} agents", count: bindingCount })}</span>
                        ) : null}
                      </div>
                      <div className="mt-6 flex items-center justify-between gap-3">
                        <span className="text-sm text-muted-foreground">
                          {skill.is_installed
                            ? t("skills.storeInstalled", { defaultValue: "Installed" })
                            : t("skills.storeNotInstalled", { defaultValue: "Not installed" })}
                        </span>
                        {skill.is_installed ? (
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                void openBindSkillModal(skill);
                              }}
                              className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                            >
                              {t("skills.bindToAgent", { defaultValue: "Bind to Agent" })}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                void handleUninstallStoreSkill(skill);
                              }}
                              disabled={uninstallDisabled}
                              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 transition-colors hover:bg-rose-100 disabled:opacity-60 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300 dark:hover:bg-rose-500/20"
                            >
                              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                              {t("skills.uninstall", { defaultValue: "Uninstall" })}
                            </button>
                          </div>
                        ) : (
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                void handleInstallStoreSkill(skill);
                              }}
                              disabled={isBusy}
                              className="inline-flex items-center gap-2 rounded-xl border border-border/50 px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted/40 disabled:opacity-60"
                            >
                              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                              {t("skills.install", { defaultValue: "Install" })}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                void openBindSkillModal(skill);
                              }}
                              disabled={isBusy}
                              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-4 py-2 text-sm font-medium text-white shadow-lg transition-transform hover:-translate-y-0.5 disabled:opacity-60"
                            >
                              {t("skills.installAndBind", { defaultValue: "Install & Bind" })}
                            </button>
                          </div>
                        )}
                      </div>
                    </article>
                  );
                })}
                </div>
              </div>
            )}
          </section>
        )}

        {activeSection === "bindings" && (
          <section className="space-y-4">
            <div className="glass-panel rounded-2xl p-6 shadow-xl">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-foreground">
                    {t("skills.bindingsTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t("skills.bindingsDescription")}
                  </p>
                </div>
                <div className="relative w-full lg:max-w-md">
                  <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={bindingSearchQuery}
                    onChange={(event) =>
                      setBindingSearchQuery(event.target.value)
                    }
                    placeholder={t("skills.bindingsSearchPlaceholder")}
                    className="w-full rounded-xl border border-border/50 bg-muted/30 py-3 pl-11 pr-4 text-sm text-foreground outline-none transition-colors focus:border-emerald-500"
                  />
                </div>
              </div>
            </div>

            {bindingsError ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
                {bindingsError}
              </div>
            ) : isBindingsLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              </div>
            ) : bindingGroups.length === 0 ? (
              <div className="glass-panel rounded-2xl p-16 text-center shadow-xl">
                <Link2 className="mx-auto h-10 w-10 text-muted-foreground" />
                <p className="mt-4 text-sm text-muted-foreground">
                  {t("skills.bindingsEmpty")}
                </p>
              </div>
            ) : (
              <div className="grid gap-4">
                {bindingGroups.map((group) => (
                  <article
                    key={`${group.ownerType}:${group.ownerId}`}
                    className="glass-panel rounded-2xl border border-border/40 p-5 shadow-sm"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-foreground">
                          {group.ownerName}
                        </h3>
                        <p className="mt-1 text-sm text-muted-foreground">
                          {t("skills.bindingsOwnerSummary", {
                            ownerType: getOwnerTypeLabel(t, group.ownerType),
                            count: group.bindings.length,
                          })}
                        </p>
                      </div>
                      <div className="text-xs text-zinc-500 dark:text-zinc-400">
                        {group.bindings.some((binding) => binding.updated_at)
                          ? t("skills.bindingsUpdated", {
                              time: formatDateTime(
                                group.bindings[0]?.updated_at ||
                                  group.bindings[0]?.created_at,
                              ),
                            })
                          : ""}
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {group.bindings.map((binding) => (
                        <div
                          key={binding.binding_id}
                          className="rounded-xl border border-zinc-200 bg-white/70 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900/50"
                        >
                          <div className="font-medium text-zinc-900 dark:text-zinc-100">
                            {binding.display_name}
                          </div>
                          <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {binding.skill_slug}
                            {binding.skill_type
                              ? ` · ${getSkillTypeLabel(t, binding.skill_type)}`
                              : ""}
                          </div>
                          <div className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                            {getBindingSourceLabel(t, binding.source)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {activeSection === "mcp_servers" && (
          <section className="space-y-4">
            <div className="glass-panel rounded-2xl p-6 shadow-xl">
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  {t("skills.mcpServersTitle", "MCP Servers")}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t(
                    "skills.mcpServersDescription",
                    "Connect external MCP servers and use their tools as skills.",
                  )}
                </p>
              </div>
            </div>

            {isMcpLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              </div>
            ) : mcpServers.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <Plug className="mb-4 h-12 w-12 text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">
                  {t(
                    "skills.mcpNoServers",
                    "No MCP servers configured yet. Click \"Add MCP Server\" to get started.",
                  )}
                </p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {mcpServers.map((server) => (
                  <McpServerCard
                    key={server.server_id}
                    server={server}
                    onSync={async (id) => {
                      await mcpServersApi.syncTools(id);
                      await loadPageData();
                    }}
                    onConnect={async (id) => {
                      await mcpServersApi.testConnection(id);
                      await loadPageData();
                    }}
                    onDisconnect={async (id) => {
                      await mcpServersApi.disconnect(id);
                      await loadPageData();
                    }}
                    onDelete={async (id) => {
                      if (!confirm(t("skills.mcpDeleteConfirm", "Delete this MCP server and all its synced tools?"))) return;
                      await mcpServersApi.delete(id);
                      await loadPageData();
                    }}
                    onEdit={(srv) => setEditingMcpServer(srv)}
                    onTestTool={(skillId) => {
                      void (async () => {
                        const cachedSkill = skills.find((s) => s.skill_id === skillId);
                        const resolvedSkill =
                          cachedSkill ?? (await skillsApi.getById(skillId));
                        setSelectedSkill(resolvedSkill);
                        setIsTesterModalOpen(true);
                      })();
                    }}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        <AddMcpServerModal
          isOpen={isAddMcpModalOpen}
          onClose={() => setIsAddMcpModalOpen(false)}
          onCreated={() => void loadPageData()}
        />

        <EditMcpServerModal
          server={editingMcpServer}
          onClose={() => setEditingMcpServer(null)}
          onSaved={() => void loadPageData()}
        />

        <AddSkillModalV2
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
          onSubmit={handleCreateSkill}
        />

        {selectedSkill && (
          <EditSkillModal
            isOpen={isEditModalOpen}
            onClose={() => {
              setIsEditModalOpen(false);
              setSelectedSkill(null);
              setSelectedSkillMode("edit");
            }}
            onSubmit={handleUpdateSkill}
            skill={selectedSkill}
            mode={selectedSkillMode}
          />
        )}

        {selectedSkill && (
          <AgentSkillViewer
            isOpen={isAgentSkillViewerOpen}
            onClose={() => {
              setIsAgentSkillViewerOpen(false);
              setSelectedSkill(null);
              setSelectedSkillMode("edit");
            }}
            skill={selectedSkill}
            mode={selectedSkillMode}
            onUpdate={loadPageData}
          />
        )}

        {selectedSkill && (
          <SkillTesterModal
            isOpen={isTesterModalOpen}
            onClose={() => {
              setIsTesterModalOpen(false);
              setSelectedSkill(null);
              void loadPageData();
            }}
            skillId={selectedSkill.skill_id}
            skillName={selectedSkill.display_name}
            skillType={selectedSkill.skill_type}
            interfaceDefinition={selectedSkill.interface_definition}
          />
        )}

        <BindSkillModal
          isOpen={isBindModalOpen}
          skillName={bindTargetSkill?.display_name || ""}
          agents={storeAgents}
          selectedAgentIds={selectedBindAgentIds}
          allowEmptySelection={bindInitiallyHadSelection}
          isLoadingAgents={isAgentsLoading}
          isSubmitting={isBindingSkill}
          error={bindError}
          onClose={closeBindSkillModal}
          onChangeSelectedAgentIds={setSelectedBindAgentIds}
          onConfirm={() => {
            void handleBindSkillToAgent();
          }}
        />
      </div>
    </div>
  );
}
