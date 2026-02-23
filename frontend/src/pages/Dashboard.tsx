import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Server,
} from "lucide-react";
import { StatCard } from "@/components/dashboard/StatCard";
import {
  TaskDistributionChart,
  type DistributionMode,
} from "@/components/dashboard/TaskDistributionChart";
import { RecentEvents } from "@/components/dashboard/RecentEvents";
import { dashboardApi } from "@/api/dashboard";
import type { DashboardStats } from "@/api/dashboard";

interface ChartPoint {
  name: string;
  tasks: number;
}

interface DashboardEventItem {
  id: string;
  type: "success" | "error" | "info";
  eventType: string;
  message: string;
  timestamp: string;
}

const DASHBOARD_WINDOW_DAYS = 7;

const defaultStats: DashboardStats = {
  active_agents: 0,
  idle_agents: 0,
  offline_agents: 0,
  total_agents: 0,
  goals_completed: 0,
  goals_completed_in_window: 0,
  missions_in_progress: 0,
  tasks_completed: 0,
  tasks_completed_24h: 0,
  tasks_failed: 0,
  tasks_in_progress: 0,
  throughput_per_hour: 0,
  success_rate: 0,
  compute_load: 0,
  memory_load: 0,
};

const getLocale = (language: string): string =>
  language.startsWith("zh") ? "zh-CN" : "en-US";

const formatChartLabel = (dateString: string, locale: string): string => {
  const date = new Date(`${dateString}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return dateString;
  }
  return new Intl.DateTimeFormat(locale, { weekday: "short" }).format(date);
};

const formatRelativeTime = (timestamp: string, locale: string): string => {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  const diffMs = date.getTime() - Date.now();
  const absMs = Math.abs(diffMs);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  if (absMs < 60_000) {
    return rtf.format(Math.round(diffMs / 1000), "second");
  }
  if (absMs < 3_600_000) {
    return rtf.format(Math.round(diffMs / 60_000), "minute");
  }
  if (absMs < 86_400_000) {
    return rtf.format(Math.round(diffMs / 3_600_000), "hour");
  }
  return rtf.format(Math.round(diffMs / 86_400_000), "day");
};

const resolveErrorMessage = (
  error: unknown,
  fallbackMessage: string,
): string => {
  if (typeof error === "object" && error !== null) {
    const maybeError = error as {
      message?: string;
      response?: {
        data?: {
          detail?: string;
          message?: string;
        };
      };
    };
    const detail =
      maybeError.response?.data?.detail || maybeError.response?.data?.message;
    if (detail) {
      return detail;
    }
    if (maybeError.message) {
      return maybeError.message;
    }
  }
  return fallbackMessage;
};

export const Dashboard: React.FC = () => {
  const { t, i18n } = useTranslation();

  const [stats, setStats] = useState<DashboardStats>(defaultStats);
  const [taskCreatedDistribution, setTaskCreatedDistribution] = useState<
    ChartPoint[]
  >([]);
  const [taskCompletedDistribution, setTaskCompletedDistribution] = useState<
    ChartPoint[]
  >([]);
  const [distributionMode, setDistributionMode] =
    useState<DistributionMode>("created");
  const [events, setEvents] = useState<DashboardEventItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(
    async (silent = false) => {
      if (silent) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      try {
        const locale = getLocale(i18n.language);
        const response = await dashboardApi.getOverview({
          days: DASHBOARD_WINDOW_DAYS,
          event_limit: 8,
        });

        setStats(response.stats);
        setTaskCreatedDistribution(
          response.task_distribution.map((point) => ({
            name: formatChartLabel(point.date, locale),
            tasks: point.tasks,
          })),
        );
        setTaskCompletedDistribution(
          (response.task_completion_distribution ?? []).map((point) => ({
            name: formatChartLabel(point.date, locale),
            tasks: point.tasks,
          })),
        );
        setEvents(
          response.recent_events.map((event) => ({
            id: event.id,
            type: event.type,
            eventType: event.event_type,
            message: event.message,
            timestamp: formatRelativeTime(event.timestamp, locale),
          })),
        );
        setError(null);
      } catch (loadError) {
        setError(
          resolveErrorMessage(
            loadError,
            t("dashboard.loadFailed", "Failed to load dashboard data"),
          ),
        );
      } finally {
        if (silent) {
          setIsRefreshing(false);
        } else {
          setIsLoading(false);
        }
      }
    },
    [i18n.language, t],
  );

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadDashboard(true);
    }, 30000);
    return () => window.clearInterval(interval);
  }, [loadDashboard]);

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <header>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-4xl font-bold tracking-tight text-zinc-800 dark:text-zinc-200">
            {t("nav.dashboard")}
          </h1>
          {isRefreshing && (
            <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
          )}
        </div>
        <p className="text-zinc-600 dark:text-zinc-400 font-medium">
          {t(
            "dashboard.subtitle",
            "Real-time system overview and performance metrics",
          )}
        </p>
      </header>

      {error && (
        <div className="glass-panel p-4 rounded-2xl border border-rose-500/30 bg-rose-500/5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
            <p className="text-sm text-rose-600 dark:text-rose-400 truncate">
              {error}
            </p>
          </div>
          <button
            onClick={() => void loadDashboard()}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-500 text-white hover:bg-rose-600 transition-colors"
          >
            {t("dashboard.retry", "Retry")}
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="glass-panel rounded-[24px] p-12 flex items-center justify-center gap-3">
          <Loader2 className="w-7 h-7 animate-spin text-emerald-500" />
          <span className="text-zinc-600 dark:text-zinc-400">
            {t("common.loading", "Loading...")}
          </span>
        </div>
      ) : (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              title={t("dashboard.totalAgents", "Total Agents")}
              value={stats.total_agents}
              subtitle={`${stats.active_agents} ${t("dashboard.active", "active")} · ${stats.idle_agents} ${t("dashboard.idle", "idle")} · ${stats.offline_agents} ${t("dashboard.offline", "offline")}`}
              definition={t(
                "dashboard.totalAgentsDefinition",
                "All agents you own, including active, idle, and offline states.",
              )}
              icon={Activity}
              colorClass="bg-emerald-500 text-emerald-600"
            />
            <StatCard
              title={t("dashboard.completedMissions", "Completed Missions")}
              value={stats.goals_completed}
              subtitle={`${t("dashboard.completedInLastDays", {
                value: stats.goals_completed_in_window,
                days: DASHBOARD_WINDOW_DAYS,
                defaultValue: `${stats.goals_completed_in_window} completed in last ${DASHBOARD_WINDOW_DAYS} days`,
              })} · ${t("dashboard.completedTasksTotal", {
                value: stats.tasks_completed,
                defaultValue: `tasks completed ${stats.tasks_completed}`,
              })} · ${stats.missions_in_progress} ${t("dashboard.inProgress", "in progress")}`}
              definition={t("dashboard.completedMissionsDefinition", {
                days: DASHBOARD_WINDOW_DAYS,
                defaultValue:
                  "Mission-level metric. Counts missions with status = completed. This is different from task counts.",
              })}
              icon={CheckCircle2}
              colorClass="bg-blue-500 text-blue-600"
            />
            <StatCard
              title={t("dashboard.throughput", "Throughput")}
              value={`${stats.tasks_completed_24h}/24h`}
              subtitle={`${stats.throughput_per_hour.toFixed(2)}/hr ${t("dashboard.average", "avg")} · ${stats.success_rate.toFixed(1)}% ${t("dashboard.successRate", "success rate")}`}
              definition={t(
                "dashboard.throughputDefinition",
                "Tasks completed in the last 24 hours. /hr is the 24h average completion rate.",
              )}
              icon={Clock}
              colorClass="bg-purple-500 text-purple-600"
            />
            <StatCard
              title={t("dashboard.computeLoad", "Compute Load")}
              value={`${stats.compute_load.toFixed(1)}%`}
              subtitle={`${t("dashboard.memory", "Memory")} ${stats.memory_load.toFixed(1)}%`}
              definition={t(
                "dashboard.computeLoadDefinition",
                "Current backend host resource usage: CPU and memory utilization.",
              )}
              icon={Server}
              colorClass="bg-orange-500 text-orange-600"
            />
          </div>

          {/* Charts and Events */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <TaskDistributionChart
                data={
                  distributionMode === "created"
                    ? taskCreatedDistribution
                    : taskCompletedDistribution
                }
                mode={distributionMode}
                onModeChange={setDistributionMode}
                definition={
                  distributionMode === "created"
                    ? t("dashboard.taskDistributionDefinition", {
                        days: DASHBOARD_WINDOW_DAYS,
                        defaultValue:
                          "Number of tasks created each day in the recent window.",
                      })
                    : t("dashboard.taskCompletionDistributionDefinition", {
                        days: DASHBOARD_WINDOW_DAYS,
                        defaultValue:
                          "Number of tasks completed each day in the recent window.",
                      })
                }
              />
            </div>
            <RecentEvents
              events={events}
              definition={t("dashboard.recentEventsDefinition", {
                limit: 8,
                defaultValue:
                  "Latest mission events for your account, including phase transitions and completion/failure updates.",
              })}
            />
          </div>
        </>
      )}
    </div>
  );
};
