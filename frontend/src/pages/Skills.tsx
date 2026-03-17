import { useState, useEffect } from "react";
import {
  Plus,
  Search,
  RefreshCw,
  Package,
  Layers,
  Power,
  BarChart3,
} from "lucide-react";
import SkillCardV2 from "@/components/skills/SkillCardV2";
import AddSkillModalV2 from "@/components/skills/AddSkillModalV2";
import EditSkillModal from "@/components/skills/EditSkillModal";
import AgentSkillViewer from "@/components/skills/AgentSkillViewer";
import SkillTesterModal from "@/components/skills/SkillTesterModal";
import {
  skillsApi,
  type Skill,
  type CreateSkillRequest,
  type SkillOverviewStats,
} from "@/api/skills";
import { useTranslation } from "react-i18next";

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

export default function Skills() {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [overviewStats, setOverviewStats] = useState<SkillOverviewStats | null>(
    null,
  );
  const [filteredSkills, setFilteredSkills] = useState<Skill[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isAgentSkillViewerOpen, setIsAgentSkillViewerOpen] = useState(false);
  const [isTesterModalOpen, setIsTesterModalOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [selectedSkillMode, setSelectedSkillMode] = useState<"view" | "edit">(
    "edit",
  );
  useEffect(() => {
    loadSkills();
  }, []);

  useEffect(() => {
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      setFilteredSkills(
        skills.filter(
          (skill) =>
            skill.display_name.toLowerCase().includes(query) ||
            skill.skill_slug.toLowerCase().includes(query) ||
            skill.description.toLowerCase().includes(query),
        ),
      );
    } else {
      setFilteredSkills(skills);
    }
  }, [searchQuery, skills]);

  const loadSkills = async () => {
    try {
      setIsLoading(true);
      const [skillsResult, overviewStatsResult] = await Promise.allSettled([
        skillsApi.getAll(),
        skillsApi.getOverviewStats(),
      ]);

      if (overviewStatsResult.status === "fulfilled") {
        setOverviewStats(overviewStatsResult.value);
      }

      if (skillsResult.status === "fulfilled") {
        const data = skillsResult.value;
        setSkills(data);
        setFilteredSkills(data);

        if (overviewStatsResult.status !== "fulfilled") {
          console.warn(
            "Failed to load skills overview stats, falling back to list-derived stats.",
          );
          setOverviewStats(buildOverviewStatsFromSkills(data));
        }
        return;
      }

      throw skillsResult.reason;
    } catch (error) {
      console.error("Failed to load skills:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateSkill = async (data: CreateSkillRequest) => {
    try {
      await skillsApi.create(data);
      await loadSkills();
    } catch (error) {
      console.error("Failed to create skill:", error);
      // Error notification is handled by apiClient interceptor
      throw error;
    }
  };

  const handleEditSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    setSelectedSkillMode(skill.can_edit ? "edit" : "view");
    // Use different editor based on skill type
    if (skill.skill_type === "agent_skill") {
      setIsAgentSkillViewerOpen(true);
    } else {
      setIsEditModalOpen(true);
    }
  };

  const handleUpdateSkill = async (skillId: string, data: any) => {
    try {
      await skillsApi.update(skillId, data);
      await loadSkills();
    } catch (error) {
      console.error("Failed to update skill:", error);
      throw error;
    }
  };

  const handleDeleteSkill = async (skillId: string) => {
    if (!confirm(t("skills.deleteConfirm"))) {
      return;
    }

    try {
      await skillsApi.delete(skillId);
      await loadSkills();
    } catch (error) {
      console.error("Failed to delete skill:", error);
    }
  };

  const handleToggleActive = async (
    skillId: string,
    currentlyActive: boolean,
  ) => {
    try {
      if (currentlyActive) {
        await skillsApi.deactivateSkill(skillId);
      } else {
        await skillsApi.activateSkill(skillId);
      }
      await loadSkills();
    } catch (error) {
      console.error("Failed to toggle skill status:", error);
    }
  };

  const handleTestSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    setIsTesterModalOpen(true);
  };

  const resolvedOverviewStats =
    overviewStats ?? buildOverviewStatsFromSkills(skills);
  const filteredPublicCount = filteredSkills.filter(
    (skill) => skill.access_level === "public",
  ).length;
  const filteredTeamCount = filteredSkills.filter(
    (skill) => skill.access_level === "team",
  ).length;
  const filteredPrivateCount = filteredSkills.filter(
    (skill) => skill.access_level === "private",
  ).length;
  const formattedCardValues = {
    total: resolvedOverviewStats.total_skills.toLocaleString(),
    active: resolvedOverviewStats.active_skills.toLocaleString(),
    executions: resolvedOverviewStats.total_execution_count.toLocaleString(),
    dependencies:
      resolvedOverviewStats.skills_with_dependencies.toLocaleString(),
  };

  return (
    <div>
      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground mb-2 bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              {t("skills.title")}
            </h1>
            <p className="text-muted-foreground">{t("skills.subtitle")}</p>
          </div>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground transition-all duration-300 shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5"
          >
            <Plus className="w-5 h-5" />
            {t("skills.addSkill")}
          </button>
        </div>

        {/* Search and Filter Bar */}
        <div className="glass-panel p-6 rounded-2xl shadow-xl">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("skills.searchPlaceholder")}
                className="w-full pl-12 pr-4 py-3 rounded-xl bg-muted/30 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
              />
            </div>
            <button
              onClick={loadSkills}
              disabled={isLoading}
              className="p-3 rounded-xl bg-muted/30 hover:bg-muted/50 text-foreground transition-all duration-300 disabled:opacity-50 hover:shadow-lg"
              title={t("skills.refresh")}
            >
              <RefreshCw
                className={`w-5 h-5 ${isLoading ? "animate-spin" : ""}`}
              />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>
              {t("skills.filteredResults")}:{" "}
              <span className="font-semibold text-foreground">
                {filteredSkills.length}
              </span>
            </span>
            <span>
              {t("skills.public", { defaultValue: "Public" })}:{" "}
              <span className="font-semibold text-foreground">
                {filteredPublicCount}
              </span>
            </span>
            <span>
              {t("skills.team", { defaultValue: "Team" })}:{" "}
              <span className="font-semibold text-foreground">
                {filteredTeamCount}
              </span>
            </span>
            <span>
              {t("skills.private", { defaultValue: "Private" })}:{" "}
              <span className="font-semibold text-foreground">
                {filteredPrivateCount}
              </span>
            </span>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="glass-panel px-4 py-3 rounded-xl border border-border/40 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  {t("skills.totalSkills")}
                </div>
                <div className="text-2xl font-semibold text-foreground leading-none">
                  {formattedCardValues.total}
                </div>
              </div>
              <div className="rounded-lg p-2 bg-primary/10 text-primary">
                <Package className="w-4 h-4" />
              </div>
            </div>
          </div>
          <div className="glass-panel px-4 py-3 rounded-xl border border-border/40 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  {t("skills.active")}
                </div>
                <div className="text-2xl font-semibold text-foreground leading-none">
                  {formattedCardValues.active}
                </div>
              </div>
              <div className="rounded-lg p-2 bg-primary/10 text-primary">
                <Power className="w-4 h-4" />
              </div>
            </div>
          </div>
          <div className="glass-panel px-4 py-3 rounded-xl border border-border/40 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  {t("skills.executionCount")}
                </div>
                <div className="text-2xl font-semibold text-foreground leading-none">
                  {formattedCardValues.executions}
                </div>
              </div>
              <div className="rounded-lg p-2 bg-primary/10 text-primary">
                <BarChart3 className="w-4 h-4" />
              </div>
            </div>
          </div>
          <div className="glass-panel px-4 py-3 rounded-xl border border-border/40 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  {t("skills.withDependencies")}
                </div>
                <div className="text-2xl font-semibold text-foreground leading-none">
                  {formattedCardValues.dependencies}
                </div>
              </div>
              <div className="rounded-lg p-2 bg-primary/10 text-primary">
                <Layers className="w-4 h-4" />
              </div>
            </div>
          </div>
        </div>

        {/* Skills Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto mb-4"></div>
                <Package className="w-8 h-8 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
              </div>
              <p className="text-muted-foreground font-medium">
                {t("skills.loading")}
              </p>
            </div>
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="glass-panel p-16 rounded-2xl shadow-xl text-center">
            <div className="max-w-md mx-auto">
              <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-6">
                <Package className="w-10 h-10 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-3">
                {searchQuery
                  ? t("skills.noSkillsFound")
                  : t("skills.noSkillsYet")}
              </h3>
              <p className="text-muted-foreground mb-6">
                {searchQuery
                  ? t("skills.tryAdjusting")
                  : t("skills.getStarted")}
              </p>
              {!searchQuery && (
                <button
                  onClick={() => setIsAddModalOpen(true)}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground transition-all duration-300 shadow-lg hover:shadow-primary/25 hover:-translate-y-0.5"
                >
                  <Plus className="w-5 h-5" />
                  {t("skills.addSkill")}
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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

        {/* Add Skill Modal */}
        <AddSkillModalV2
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
          onSubmit={handleCreateSkill}
        />

        {/* Edit Skill Modal */}
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

        {/* Agent Skill Viewer */}
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
            onUpdate={loadSkills}
          />
        )}

        {/* Skill Tester Modal */}
        {selectedSkill && (
          <SkillTesterModal
            isOpen={isTesterModalOpen}
            onClose={() => {
              setIsTesterModalOpen(false);
              setSelectedSkill(null);
              void loadSkills();
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
