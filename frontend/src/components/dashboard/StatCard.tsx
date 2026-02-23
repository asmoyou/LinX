import React from "react";
import { MetricHint } from "@/components/dashboard/MetricHint";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  definition?: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  colorClass?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  definition,
  icon: Icon,
  trend,
  colorClass = "bg-emerald-500 text-emerald-600",
}) => {
  return (
    <div className="glass-panel relative z-0 p-6 rounded-[24px] group hover:-translate-y-1 hover:z-40 focus-within:z-40 transition-all duration-300 overflow-visible">
      <div className="flex justify-between items-start mb-4">
        <div
          className={`p-2.5 rounded-xl ${colorClass} bg-opacity-10 text-opacity-90`}
        >
          <Icon className="w-5 h-5" />
        </div>
        {trend && (
          <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-500 bg-emerald-500/5 px-2 py-0.5 rounded-full">
            {trend.isPositive ? "+" : ""}
            {trend.value}%
          </span>
        )}
      </div>
      <div>
        <h3 className="text-3xl font-bold tracking-tight mb-1 text-zinc-800 dark:text-zinc-200">
          {value}
        </h3>
        <div className="flex items-center gap-1.5">
          <p className="text-zinc-600 dark:text-zinc-400 text-xs font-medium uppercase tracking-wider">
            {title}
          </p>
          {definition && <MetricHint text={definition} />}
        </div>
        {subtitle && (
          <p className="text-zinc-500 dark:text-zinc-500 text-[10px] mt-2 font-mono">
            {subtitle}
          </p>
        )}
      </div>
    </div>
  );
};
