import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CheckCircle2,
  Inbox,
  Link2,
  Loader2,
  Package,
  Plus,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import SkillCardV2 from "@/components/skills/SkillCardV2";
import AddSkillModalV2 from "@/components/skills/AddSkillModalV2";
import EditSkillModal from "@/components/skills/EditSkillModal";
import AgentSkillViewer from "@/components/skills/AgentSkillViewer";
import SkillTesterModal from "@/components/skills/SkillTesterModal";
import {
  skillsApi,
  type CreateSkillRequest,
  type Skill,
  type SkillBinding,
  type SkillCandidate,
  type SkillOverviewStats,
} from "@/api/skills";

type SkillsSection = "inbox" | "library" | "bindings";

const SECTION_PARAM = "section";

const getSectionFromSearchParam = (value: string | null): SkillsSection => {
  if (value === "inbox" || value === "bindings") {
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
  t: (key: string, options?: Record<string, unknown> | string) => string,
  skillType?: string | null,
): string | null => {
  switch (skillType) {
    case "langchain_tool":
      return t("skills.langchainTool");
    case "agent_skill":
      return t("skills.agentSkill");
    default:
      return skillType || null;
  }
};

const getCandidateStatusLabel = (
  t: (key: string, options?: Record<string, unknown> | string) => string,
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
  t: (key: string, options?: Record<string, unknown> | string) => string,
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
  t: (key: string, options?: Record<string, unknown> | string) => string,
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

  useEffect(() => {
    void loadPageData();
  }, []);

  const setSection = (section: SkillsSection) => {
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.set(SECTION_PARAM, section);
    setSearchParams(nextSearchParams);
  };

  const loadPageData = async () => {
    setIsRefreshing(true);
    setIsLibraryLoading(true);
    setIsCandidatesLoading(true);
    setIsBindingsLoading(true);
    setLibraryError(null);
    setCandidatesError(null);
    setBindingsError(null);

    const [skillsResult, candidatesResult, bindingsResult, overviewResult] =
      await Promise.allSettled([
        skillsApi.getAll(),
        skillsApi.getCandidates({ status: "all", limit: 100 }),
        skillsApi.getBindings({ limit: 200 }),
        skillsApi.getOverviewStats(),
      ]);

    if (skillsResult.status === "fulfilled") {
      setSkills(skillsResult.value);
      setOverviewStats(
        overviewResult.status === "fulfilled"
          ? overviewResult.value
          : buildOverviewStatsFromSkills(skillsResult.value),
      );
    } else {
      setLibraryError(
        t("skills.loadError", {
          defaultValue: "Failed to load skills library.",
        }),
      );
    }
    setIsLibraryLoading(false);

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

    setIsRefreshing(false);
  };

  const handleCreateSkill = async (data: CreateSkillRequest) => {
    await skillsApi.create(data);
    await loadPageData();
  };

  const handleEditSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    setSelectedSkillMode(skill.can_edit ? "edit" : "view");
    if (skill.skill_type === "agent_skill") {
      setIsAgentSkillViewerOpen(true);
    } else {
      setIsEditModalOpen(true);
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

  const resolvedOverviewStats =
    overviewStats ?? buildOverviewStatsFromSkills(skills);
  const libraryQuery = normalizeSearchValue(librarySearchQuery);
  const candidateQuery = normalizeSearchValue(candidateSearchQuery);
  const bindingQuery = normalizeSearchValue(bindingSearchQuery);

  const filteredSkills = useMemo(() => {
    if (!libraryQuery) {
      return skills;
    }
    return skills.filter((skill) => {
      return [skill.display_name, skill.skill_slug, skill.description]
        .join("\n")
        .toLowerCase()
        .includes(libraryQuery);
    });
  }, [libraryQuery, skills]);

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
      id: "bindings",
      label: t("skills.sectionBindings"),
      icon: Link2,
      count: totalBindingsCount,
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
                  <input
                    type="text"
                    value={librarySearchQuery}
                    onChange={(event) =>
                      setLibrarySearchQuery(event.target.value)
                    }
                    placeholder={t("skills.searchPlaceholder")}
                    className="w-full rounded-xl border border-border/50 bg-muted/30 py-3 pl-11 pr-4 text-sm text-foreground outline-none transition-colors focus:border-emerald-500"
                  />
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
            ) : filteredSkills.length === 0 ? (
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
                {filteredSkills.map((skill) => (
                  <SkillCardV2
                    key={skill.skill_id}
                    skill={skill}
                    onEdit={handleEditSkill}
                    onDelete={handleDeleteSkill}
                    onToggleActive={handleToggleActive}
                    onTest={handleTestSkill}
                  />
                ))}
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
      </div>
    </div>
  );
}
