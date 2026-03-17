import {
  Code2,
  Package,
  Layers,
  Trash2,
  Edit,
  Play,
  Power,
  PowerOff,
  BookOpen,
  AlertCircle,
  Eye,
} from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import type { Skill, SkillMetadata } from "@/api/skills";
import { useTranslation } from "react-i18next";

interface SkillCardV2Props {
  skill: Skill & {
    skill_type?: string;
    is_active?: boolean;
    execution_count?: number;
    average_execution_time?: number;
    homepage?: string;
    metadata?: SkillMetadata;
    skill_metadata?: SkillMetadata;
    gating_status?: {
      eligible: boolean;
      missing_bins?: string[];
      missing_env?: string[];
      missing_config?: string[];
      os_compatible?: boolean;
      reason?: string;
    };
  };
  onEdit: (skill: Skill) => void;
  onDelete: (skillId: string) => void;
  onToggleActive?: (skillId: string, isActive: boolean) => void;
  onTest?: (skill: Skill) => void;
}

const getSkillTypeInfo = (type: string, t: any) => {
  switch (type) {
    case "langchain_tool":
      return {
        icon: Code2,
        label: t("skills.langchainTool"),
        color: "text-blue-600 dark:text-blue-400",
        bgColor: "bg-blue-100 dark:bg-blue-500/20",
        badge: t("skills.langchainTool"),
      };
    case "agent_skill":
      return {
        icon: BookOpen,
        label: t("skills.agentSkill"),
        color: "text-purple-600 dark:text-purple-400",
        bgColor: "bg-purple-100 dark:bg-purple-500/20",
        badge: t("skills.agentSkill"),
      };
    case "agent_skill_simple":
      return {
        icon: Code2,
        label: t("skills.agentSkill"),
        color: "text-blue-600 dark:text-blue-400",
        bgColor: "bg-blue-100 dark:bg-blue-500/20",
        badge: "Simple",
      };
    case "agent_skill_module":
      return {
        icon: Layers,
        label: "Module",
        color: "text-purple-600 dark:text-purple-400",
        bgColor: "bg-purple-100 dark:bg-purple-500/20",
        badge: "Module",
      };
    case "agent_skill_package":
      return {
        icon: Package,
        label: "Package",
        color: "text-orange-600 dark:text-orange-400",
        bgColor: "bg-orange-100 dark:bg-orange-500/20",
        badge: "Package",
      };
    default:
      return {
        icon: Code2,
        label: "Skill",
        color: "text-zinc-600 dark:text-zinc-400",
        bgColor: "bg-zinc-100 dark:bg-zinc-800",
        badge: "Unknown",
      };
  }
};

const STAT_MAX_FONT_SIZE_PX = 18;
const STAT_MIN_FONT_SIZE_PX = 11;

interface AutoFitStatValueProps {
  value: string;
  maxFontPx?: number;
  minFontPx?: number;
  className?: string;
}

function AutoFitStatValue({
  value,
  maxFontPx = STAT_MAX_FONT_SIZE_PX,
  minFontPx = STAT_MIN_FONT_SIZE_PX,
  className = "",
}: AutoFitStatValueProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);

  const fitFontSize = useCallback(() => {
    const container = containerRef.current;
    const text = textRef.current;
    if (!container || !text) {
      return;
    }

    text.style.fontSize = `${maxFontPx}px`;
    const availableWidth = container.clientWidth;
    const requiredWidth = text.scrollWidth;

    if (!availableWidth || !requiredWidth || requiredWidth <= availableWidth) {
      text.style.fontSize = `${maxFontPx}px`;
      return;
    }

    const scaled = (maxFontPx * availableWidth) / requiredWidth;
    const nextSize = Math.max(minFontPx, Math.min(maxFontPx, scaled));
    text.style.fontSize = `${nextSize}px`;
  }, [maxFontPx, minFontPx]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const rafId = window.requestAnimationFrame(() => {
      fitFontSize();
    });

    const observer = new ResizeObserver(() => {
      fitFontSize();
    });
    observer.observe(container);

    const fontSet = (
      document as Document & { fonts?: { ready?: Promise<unknown> } }
    ).fonts;
    fontSet?.ready?.then(() => {
      fitFontSize();
    });

    return () => {
      window.cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, [fitFontSize, value]);

  return (
    <div ref={containerRef} className="w-full min-w-0 overflow-hidden">
      <span
        ref={textRef}
        className={`block w-full text-center font-semibold leading-none whitespace-nowrap ${className}`}
        style={{ fontSize: `${maxFontPx}px` }}
      >
        {value}
      </span>
    </div>
  );
}

export default function SkillCardV2({
  skill,
  onEdit,
  onDelete,
  onToggleActive,
  onTest,
}: SkillCardV2Props) {
  const { t, i18n } = useTranslation();
  const typeInfo = getSkillTypeInfo(skill.skill_type || "langchain_tool", t);
  const TypeIcon = typeInfo.icon;
  const latestUpdatedAt = skill.updated_at || skill.created_at;
  const skillMetadata = skill.skill_metadata || skill.metadata;
  const canManageSkill = Boolean(skill.can_edit);
  const canDeleteSkill = Boolean(skill.can_delete);
  const ownershipInfo =
    skill.access_level === "public"
      ? {
          label: t("skills.public", { defaultValue: "Public" }),
          className:
            "bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300",
        }
      : skill.access_level === "team"
        ? {
            label: skill.department_name
              ? `${t("skills.team", { defaultValue: "Team" })} · ${skill.department_name}`
              : t("skills.team", { defaultValue: "Team" }),
            className:
              "bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300",
          }
        : {
            label: t("skills.private", { defaultValue: "Private" }),
            className:
              "bg-slate-100 dark:bg-slate-500/20 text-slate-700 dark:text-slate-300",
          };
  const EditActionIcon = canManageSkill ? Edit : Eye;
  const updatedDate = latestUpdatedAt ? new Date(latestUpdatedAt) : null;
  const dateLocale = i18n.language === "zh" ? "zh-CN" : undefined;
  const updatedYearLabel =
    updatedDate && !Number.isNaN(updatedDate.getTime())
      ? String(updatedDate.getFullYear())
      : "-";
  const updatedMonthDayTimeLabel =
    updatedDate && !Number.isNaN(updatedDate.getTime())
      ? `${String(updatedDate.getMonth() + 1).padStart(2, "0")}-${String(updatedDate.getDate()).padStart(2, "0")} ${new Intl.DateTimeFormat(
          dateLocale,
          {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          },
        ).format(updatedDate)}`
      : "-";
  const executionCountLabel = String(skill.execution_count || 0);
  const avgTimeLabel =
    skill.average_execution_time !== undefined &&
    skill.average_execution_time !== null
      ? `${skill.average_execution_time.toFixed(3)}s`
      : "-";

  return (
    <div className="glass-panel group relative rounded-2xl overflow-visible p-6 hover:-translate-y-1 transition-all duration-300 flex flex-col h-full shadow-xl hover:shadow-2xl">
      {/* Gradient overlay on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      {/* Content */}
      <div className="relative z-10 flex flex-col h-full">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-start gap-3 flex-1">
            <div
              className={`p-3 rounded-xl ${typeInfo.bgColor} shadow-lg group-hover:shadow-xl transition-shadow duration-300`}
            >
              {skillMetadata?.emoji ? (
                <span className="text-2xl">{skillMetadata.emoji}</span>
              ) : (
                <TypeIcon className={`w-6 h-6 ${typeInfo.color}`} />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                {skill.display_name}
              </h3>
              <p className="text-xs font-mono text-muted-foreground mt-1 truncate">
                {skill.skill_slug}
              </p>
              <div className="flex items-center gap-2 mt-2 mb-1 flex-wrap min-w-0">
                <span
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${typeInfo.bgColor} ${typeInfo.color}`}
                >
                  {typeInfo.badge}
                </span>
                <span
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${ownershipInfo.className}`}
                >
                  {ownershipInfo.label}
                </span>
                {skill.is_active !== undefined && (
                  <span
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${
                      skill.is_active
                        ? "bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400"
                        : "bg-zinc-100 dark:bg-zinc-500/20 text-zinc-600 dark:text-zinc-400"
                    }`}
                  >
                    {skill.is_active
                      ? t("skills.active")
                      : t("skills.inactive")}
                  </span>
                )}
              </div>
              <div className="relative group/description">
                <p className="text-sm text-muted-foreground line-clamp-2 break-words cursor-help">
                  {skill.description}
                </p>
                {skill.description && (
                  <div className="absolute top-full left-0 right-0 z-30 mt-2 opacity-0 translate-y-1 pointer-events-none transition-all duration-150 group-hover/description:opacity-100 group-hover/description:translate-y-0">
                    <div className="max-h-44 overflow-y-auto rounded-lg border border-border/60 bg-background/95 p-3 text-xs leading-5 text-foreground shadow-2xl backdrop-blur-sm">
                      {skill.description}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Gating requirements for agent_skill */}
        {skill.skill_type === "agent_skill" && skillMetadata?.requires && (
          <div className="mb-4 p-3 rounded-xl bg-muted/30">
            <div className="text-xs font-medium text-muted-foreground mb-2">
              {t("skills.requirements")}:
            </div>
            <div className="flex flex-wrap gap-2">
              {skillMetadata.requires.bins &&
                skillMetadata.requires.bins.length > 0 && (
                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-muted-foreground">Bins:</span>
                    <span className="text-foreground">
                      {skillMetadata.requires.bins.join(", ")}
                    </span>
                  </div>
                )}
              {skillMetadata.requires.env &&
                skillMetadata.requires.env.length > 0 && (
                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-muted-foreground">Env:</span>
                    <span className="text-foreground">
                      {skillMetadata.requires.env.join(", ")}
                    </span>
                  </div>
                )}
            </div>

            {/* Gating status indicator */}
            {skill.gating_status && !skill.gating_status.eligible && (
              <div className="mt-2 flex items-center gap-2 text-xs text-orange-600 dark:text-orange-400">
                <AlertCircle className="w-3 h-3" />
                <span>{t("skills.requirementsNotMet")}</span>
              </div>
            )}
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 mb-4 flex-shrink-0">
          <div className="text-center p-2.5 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors min-w-0">
            <AutoFitStatValue value={executionCountLabel} />
            <div className="mt-1 text-[11px] leading-tight text-muted-foreground">
              {t("skills.executionCount")}
            </div>
          </div>
          <div className="text-center p-2.5 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors min-w-0">
            <AutoFitStatValue value={avgTimeLabel} />
            <div className="mt-1 text-[11px] leading-tight text-muted-foreground">
              {t("skills.avgTime")}
            </div>
          </div>
          <div className="text-center p-2.5 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors min-w-0">
            <AutoFitStatValue
              value={updatedYearLabel}
              maxFontPx={13}
              minFontPx={8}
            />
            <AutoFitStatValue
              value={updatedMonthDayTimeLabel}
              maxFontPx={11}
              minFontPx={7}
              className="mt-1 text-muted-foreground"
            />
            <div className="mt-1 text-[11px] leading-tight text-muted-foreground">
              {t("skills.updatedAt")}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto">
          {/* Test button - prominent */}
          <button
            onClick={() => onTest?.(skill)}
            className="flex-1 px-4 py-2.5 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary transition-all duration-300 flex items-center justify-center gap-2 text-sm font-medium hover:shadow-lg"
          >
            <Play className="w-4 h-4" />
            {t("skills.test")}
          </button>

          {/* Icon buttons - grouped together */}
          <div className="flex items-center gap-2">
            {onToggleActive && canManageSkill && (
              <button
                onClick={() =>
                  onToggleActive(skill.skill_id, skill.is_active || false)
                }
                className={`p-2.5 rounded-xl transition-all duration-300 hover:shadow-lg ${
                  skill.is_active
                    ? "bg-orange-100 dark:bg-orange-500/10 hover:bg-orange-200 dark:hover:bg-orange-500/20 text-orange-700 dark:text-orange-400"
                    : "bg-green-100 dark:bg-green-500/10 hover:bg-green-200 dark:hover:bg-green-500/20 text-green-700 dark:text-green-400"
                }`}
                title={
                  skill.is_active
                    ? t("skills.deactivate")
                    : t("skills.activate")
                }
              >
                {skill.is_active ? (
                  <PowerOff className="w-4 h-4" />
                ) : (
                  <Power className="w-4 h-4" />
                )}
              </button>
            )}

            <button
              onClick={() => onEdit(skill)}
              className="p-2.5 rounded-xl bg-muted/30 hover:bg-muted/50 text-foreground transition-all duration-300 hover:shadow-lg"
              title={canManageSkill ? t("skills.edit") : t("skills.view")}
            >
              <EditActionIcon className="w-4 h-4" />
            </button>

            {canDeleteSkill && (
              <button
                onClick={() => onDelete(skill.skill_id)}
                className="p-2.5 rounded-xl bg-red-100 dark:bg-red-500/10 hover:bg-red-200 dark:hover:bg-red-500/20 text-red-700 dark:text-red-400 transition-all duration-300 hover:shadow-lg"
                title={t("skills.delete")}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
