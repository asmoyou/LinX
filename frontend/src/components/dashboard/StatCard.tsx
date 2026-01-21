import React from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
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
  icon: Icon,
  trend,
  colorClass = 'bg-emerald-500 text-emerald-600',
}) => {
  return (
    <div className="glass-panel p-6 rounded-[24px] group hover:-translate-y-1 transition-all duration-300">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2.5 rounded-xl ${colorClass} bg-opacity-10 text-opacity-90`}>
          <Icon className="w-5 h-5" />
        </div>
        {trend && (
          <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-500 bg-emerald-500/5 px-2 py-0.5 rounded-full">
            {trend.isPositive ? '+' : ''}{trend.value}%
          </span>
        )}
      </div>
      <div>
        <h3 className="text-3xl font-bold tracking-tight mb-1">{value}</h3>
        <p className="text-zinc-500 dark:text-zinc-400 text-xs font-medium uppercase tracking-wider">
          {title}
        </p>
        {subtitle && (
          <p className="text-zinc-400 dark:text-zinc-500 text-[10px] mt-2 font-mono">
            {subtitle}
          </p>
        )}
      </div>
    </div>
  );
};
