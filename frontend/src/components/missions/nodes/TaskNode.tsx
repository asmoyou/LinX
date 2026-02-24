import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { CheckCircle2, Circle, Loader2, XCircle, AlertTriangle, Clock3 } from 'lucide-react';

interface TaskNodeData {
  task_id: string;
  goal_text: string;
  status: string;
  priority: number;
  assigned_agent_name?: string;
  dependency_level?: number;
  acceptance_criteria?: string;
}

const statusConfig: Record<string, { icon: React.ElementType; color: string; borderColor: string }> = {
  completed: { icon: CheckCircle2, color: 'text-green-500', borderColor: 'border-green-400' },
  in_progress: { icon: Loader2, color: 'text-emerald-500', borderColor: 'border-emerald-400' },
  pending: { icon: Circle, color: 'text-zinc-400', borderColor: 'border-zinc-300' },
  failed: { icon: XCircle, color: 'text-red-500', borderColor: 'border-red-400' },
  blocked: { icon: AlertTriangle, color: 'text-amber-500', borderColor: 'border-amber-400' },
  reviewing: { icon: Loader2, color: 'text-purple-500', borderColor: 'border-purple-400' },
  awaiting_review: { icon: Clock3, color: 'text-purple-500', borderColor: 'border-purple-300' },
};

export const TaskNode: React.FC<{ data: TaskNodeData }> = memo(({ data }) => {
  const config = statusConfig[data.status] || statusConfig.pending;
  const Icon = config.icon;

  return (
    <div className={`px-4 py-3 rounded-xl border-2 ${config.borderColor} bg-white dark:bg-zinc-900 shadow-md min-w-[200px] max-w-[260px]`}>
      <Handle type="target" position={Position.Top} className="!bg-emerald-500 !w-2.5 !h-2.5" />

      <div className="flex items-start gap-2 mb-2">
        <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${config.color} ${data.status === 'in_progress' || data.status === 'reviewing' ? 'animate-spin' : ''}`} />
        <p className="text-xs font-medium text-zinc-800 dark:text-zinc-200 leading-snug">
          {data.goal_text}
        </p>
      </div>

      {data.assigned_agent_name && (
        <div className="flex items-center gap-1.5 mb-1">
          <div className="w-4 h-4 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-[7px] font-bold text-white">
            {data.assigned_agent_name[0].toUpperCase()}
          </div>
          <span className="text-[10px] text-zinc-500">{data.assigned_agent_name}</span>
        </div>
      )}

      {data.priority > 0 && (
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-zinc-400">Priority:</span>
          <span className="text-[10px] font-medium text-zinc-600 dark:text-zinc-400">{data.priority}</span>
        </div>
      )}
      {typeof data.dependency_level === 'number' && (
        <div className="flex items-center gap-1 mt-0.5">
          <span className="text-[10px] text-zinc-400">Dep Wave:</span>
          <span className="text-[10px] font-medium text-zinc-600 dark:text-zinc-400">
            {data.dependency_level + 1}
          </span>
        </div>
      )}
      {data.status === 'awaiting_review' && (
        <div className="text-[10px] text-purple-500 mt-0.5">
          Awaiting review
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-emerald-500 !w-2.5 !h-2.5" />
    </div>
  );
});

TaskNode.displayName = 'TaskNode';
