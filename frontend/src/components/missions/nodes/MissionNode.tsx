import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import type { MissionStatus } from '@/types/mission';

interface MissionNodeData {
  title: string;
  status: MissionStatus;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  agents: Array<{ agent_name?: string; avatar?: string; role: string }>;
}

const statusColors: Record<MissionStatus, string> = {
  draft: 'border-zinc-400',
  requirements: 'border-blue-400',
  planning: 'border-indigo-400',
  executing: 'border-emerald-400',
  reviewing: 'border-amber-400',
  qa: 'border-purple-400',
  completed: 'border-green-500',
  failed: 'border-red-500',
  cancelled: 'border-zinc-500',
};

const statusBgColors: Record<MissionStatus, string> = {
  draft: 'bg-zinc-400/10',
  requirements: 'bg-blue-400/10',
  planning: 'bg-indigo-400/10',
  executing: 'bg-emerald-400/10',
  reviewing: 'bg-amber-400/10',
  qa: 'bg-purple-400/10',
  completed: 'bg-green-500/10',
  failed: 'bg-red-500/10',
  cancelled: 'bg-zinc-500/10',
};

export const MissionNode: React.FC<{ data: MissionNodeData }> = memo(({ data }) => {
  const progress = data.total_tasks > 0
    ? Math.round((data.completed_tasks / data.total_tasks) * 100)
    : 0;

  return (
    <div className={`px-5 py-4 rounded-xl border-2 ${statusColors[data.status]} ${statusBgColors[data.status]} bg-white dark:bg-zinc-900 shadow-lg min-w-[260px]`}>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
        <h3 className="font-bold text-sm text-zinc-800 dark:text-zinc-100 truncate">
          {data.title}
        </h3>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${statusBgColors[data.status]} text-zinc-700 dark:text-zinc-300`}>
          {data.status}
        </span>
        <span className="text-xs text-zinc-500">
          {data.completed_tasks}/{data.total_tasks} tasks
        </span>
      </div>

      {data.total_tasks > 0 && (
        <div className="w-full bg-zinc-200 dark:bg-zinc-700 rounded-full h-1.5 mb-3">
          <div
            className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {data.agents.length > 0 && (
        <div className="flex -space-x-2">
          {data.agents.slice(0, 5).map((agent, i) => (
            <div
              key={i}
              className="w-6 h-6 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 border-2 border-white dark:border-zinc-900 flex items-center justify-center text-[8px] font-bold text-white"
              title={`${agent.agent_name || 'Agent'} (${agent.role})`}
            >
              {(agent.agent_name || 'A')[0].toUpperCase()}
            </div>
          ))}
          {data.agents.length > 5 && (
            <div className="w-6 h-6 rounded-full bg-zinc-300 dark:bg-zinc-600 border-2 border-white dark:border-zinc-900 flex items-center justify-center text-[8px] font-bold text-zinc-600 dark:text-zinc-300">
              +{data.agents.length - 5}
            </div>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-emerald-500 !w-3 !h-3" />
    </div>
  );
});

MissionNode.displayName = 'MissionNode';
