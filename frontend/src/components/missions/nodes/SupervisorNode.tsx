import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { Eye, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

interface SupervisorNodeData {
  task_id: string;
  task_label: string;
  verdict?: string;
  feedback?: string;
  is_active?: boolean;
}

export const SupervisorNode: React.FC<{ data?: SupervisorNodeData }> = memo(({ data }) => {
  const safeData = data ?? { task_id: '', task_label: 'Review' };
  const verdictConfig = {
    approved: { icon: CheckCircle2, color: 'border-green-400 bg-green-50 dark:bg-green-500/5', text: 'text-green-600' },
    rework: { icon: XCircle, color: 'border-red-400 bg-red-50 dark:bg-red-500/5', text: 'text-red-600' },
    pending: { icon: Eye, color: 'border-amber-300 bg-amber-50 dark:bg-amber-500/5', text: 'text-amber-600' },
  };

  const normalizedVerdict = (() => {
    const rawVerdict = String(safeData.verdict || '').trim().toLowerCase();
    if (rawVerdict === 'pass' || rawVerdict === 'approved' || rawVerdict === 'success') {
      return 'approved' as const;
    }
    if (
      rawVerdict === 'fail' ||
      rawVerdict === 'rework' ||
      rawVerdict === 'rejected' ||
      rawVerdict === 'reject'
    ) {
      return 'rework' as const;
    }
    return 'pending' as const;
  })();

  const config = verdictConfig[normalizedVerdict] ?? verdictConfig.pending;
  const Icon = config.icon;
  const HeaderIcon = safeData.is_active ? Loader2 : Icon;
  const iconClass = safeData.is_active ? 'text-purple-500 animate-spin' : config.text;

  return (
    <div
      className={`px-4 py-3 rounded-xl border-2 ${config.color} ${safeData.is_active ? 'ring-2 ring-purple-300/70 shadow-purple-200/30' : ''} bg-white dark:bg-zinc-900 shadow-md min-w-[200px] max-w-[260px]`}
    >
      <Handle type="target" position={Position.Top} className="!bg-purple-500 !w-2.5 !h-2.5" />

      <div className="flex items-center gap-2 mb-2">
        <HeaderIcon className={`w-4 h-4 ${iconClass}`} />
        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Review</span>
        {safeData.is_active && (
          <span className="ml-auto text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full text-purple-700 bg-purple-100 dark:text-purple-200 dark:bg-purple-500/20">
            Running
          </span>
        )}
      </div>

      <p className="text-[11px] text-zinc-600 dark:text-zinc-400 mb-1 truncate">
        {safeData.task_label}
      </p>

      {safeData.feedback && (
        <p className="text-[10px] text-zinc-500 italic leading-snug line-clamp-2">
          {safeData.feedback}
        </p>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-purple-500 !w-2.5 !h-2.5" />
    </div>
  );
});

SupervisorNode.displayName = 'SupervisorNode';
