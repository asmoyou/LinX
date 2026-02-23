import React from "react";
import { useTranslation } from "react-i18next";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { MetricHint } from "@/components/dashboard/MetricHint";

export type DistributionMode = "created" | "completed";

interface TaskDistributionChartProps {
  data: Array<{
    name: string;
    tasks: number;
  }>;
  mode: DistributionMode;
  onModeChange: (mode: DistributionMode) => void;
  definition?: string;
}

export const TaskDistributionChart: React.FC<TaskDistributionChartProps> = ({
  data,
  mode,
  onModeChange,
  definition,
}) => {
  const { t } = useTranslation();

  return (
    <div className="glass-panel p-8 rounded-[32px]">
      <div className="mb-8 flex items-center gap-1.5">
        <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
          {t("dashboard.taskDistribution", "Task Distribution")}
        </h3>
        {definition && <MetricHint text={definition} />}
        <div className="ml-auto inline-flex rounded-lg border border-zinc-200 dark:border-zinc-700 p-0.5">
          <button
            type="button"
            onClick={() => onModeChange("created")}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
              mode === "created"
                ? "bg-emerald-500 text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
            aria-pressed={mode === "created"}
          >
            {t("dashboard.distributionCreated", "Created")}
          </button>
          <button
            type="button"
            onClick={() => onModeChange("completed")}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
              mode === "completed"
                ? "bg-emerald-500 text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
            aria-pressed={mode === "completed"}
          >
            {t("dashboard.distributionCompleted", "Completed")}
          </button>
        </div>
      </div>
      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorTasks" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.1} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(120,120,128,0.08)"
              vertical={false}
            />
            <XAxis
              dataKey="name"
              stroke="#a1a1aa"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              dy={10}
            />
            <YAxis
              stroke="#a1a1aa"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              dx={-10}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "16px",
                backdropFilter: "blur(20px)",
                padding: "12px",
                fontSize: "12px",
              }}
              formatter={(value) => [`${value}`, t("dashboard.tasks", "Tasks")]}
              itemStyle={{ color: "#10b981", fontWeight: "600" }}
              cursor={{
                stroke: "#10b981",
                strokeWidth: 1,
                strokeDasharray: "4 4",
              }}
            />
            <Area
              type="monotone"
              dataKey="tasks"
              stroke="#10b981"
              strokeWidth={3}
              fillOpacity={1}
              fill="url(#colorTasks)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
