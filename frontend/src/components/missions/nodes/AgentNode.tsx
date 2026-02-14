import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { Bot } from 'lucide-react';
import type { MissionAgentRole, MissionAgentStatus } from '@/types/mission';

interface AgentNodeData {
  agent_name: string;
  role: MissionAgentRole;
  status: MissionAgentStatus;
  avatar?: string;
  is_temporary: boolean;
}

const roleColors: Record<MissionAgentRole, string> = {
  leader: 'bg-amber-500/10 text-amber-600 border-amber-300',
  supervisor: 'bg-purple-500/10 text-purple-600 border-purple-300',
  qa: 'bg-blue-500/10 text-blue-600 border-blue-300',
  worker: 'bg-emerald-500/10 text-emerald-600 border-emerald-300',
};

const statusIndicators: Record<MissionAgentStatus, string> = {
  assigned: 'bg-zinc-400',
  active: 'bg-green-500 animate-pulse',
  idle: 'bg-amber-400',
  completed: 'bg-green-600',
  failed: 'bg-red-500',
};

export const AgentNode: React.FC<{ data: AgentNodeData }> = memo(({ data }) => {
  return (
    <div className="px-4 py-3 rounded-xl border-2 border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-md min-w-[180px]">
      <Handle type="target" position={Position.Top} className="!bg-cyan-500 !w-2.5 !h-2.5" />

      <div className="flex items-center gap-2 mb-2">
        <div className="relative">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-xs font-bold text-white">
            {data.avatar ? (
              <img src={data.avatar} alt={data.agent_name} className="w-full h-full rounded-full object-cover" />
            ) : (
              <Bot className="w-4 h-4" />
            )}
          </div>
          <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-zinc-900 ${statusIndicators[data.status]}`} />
        </div>
        <div>
          <p className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">{data.agent_name}</p>
          <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full border ${roleColors[data.role]}`}>
            {data.role.toUpperCase()}
          </span>
        </div>
      </div>

      {data.is_temporary && (
        <span className="text-[9px] text-zinc-400 italic">temporary</span>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-cyan-500 !w-2.5 !h-2.5" />
    </div>
  );
});

AgentNode.displayName = 'AgentNode';
