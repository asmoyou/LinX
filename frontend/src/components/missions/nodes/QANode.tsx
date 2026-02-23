import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { ShieldCheck, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';

interface QANodeData {
  verdict?: string;
  issues_count?: number;
  summary?: string;
  is_active?: boolean;
}

export const QANode: React.FC<{ data?: QANodeData }> = memo(({ data }) => {
  const safeData = data ?? {};
  const verdictConfig = {
    pass: { icon: CheckCircle2, color: 'border-green-400 bg-green-50 dark:bg-green-500/5', text: 'text-green-600', label: 'Passed' },
    fail: { icon: AlertTriangle, color: 'border-red-400 bg-red-50 dark:bg-red-500/5', text: 'text-red-600', label: 'Failed' },
    pending: { icon: ShieldCheck, color: 'border-indigo-300 bg-indigo-50 dark:bg-indigo-500/5', text: 'text-indigo-600', label: 'Pending' },
  };

  const normalizedVerdict = (() => {
    const rawVerdict = String(safeData.verdict || '').trim().toLowerCase();
    if (rawVerdict === 'pass' || rawVerdict === 'approved' || rawVerdict === 'success') {
      return 'pass' as const;
    }
    if (rawVerdict === 'fail' || rawVerdict === 'rework' || rawVerdict === 'rejected') {
      return 'fail' as const;
    }
    return 'pending' as const;
  })();

  const config = verdictConfig[normalizedVerdict] ?? verdictConfig.pending;
  const Icon = config.icon;
  const HeaderIcon = safeData.is_active ? Loader2 : Icon;
  const iconClass = safeData.is_active ? 'text-indigo-500 animate-spin' : config.text;

  return (
    <div
      className={`px-4 py-3 rounded-xl border-2 ${config.color} ${safeData.is_active ? 'ring-2 ring-indigo-300/70 shadow-indigo-200/30' : ''} bg-white dark:bg-zinc-900 shadow-md min-w-[200px] max-w-[260px]`}
    >
      <Handle type="target" position={Position.Top} className="!bg-indigo-500 !w-2.5 !h-2.5" />

      <div className="flex items-center gap-2 mb-2">
        <HeaderIcon className={`w-4 h-4 ${iconClass}`} />
        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">QA Audit</span>
        {safeData.is_active && (
          <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full text-indigo-700 bg-indigo-100 dark:text-indigo-200 dark:bg-indigo-500/20">
            Running
          </span>
        )}
        <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full ${config.color} ${config.text}`}>
          {config.label}
        </span>
      </div>

      {safeData.issues_count !== undefined && safeData.issues_count > 0 && (
        <p className="text-[10px] text-red-500 mb-1">
          {safeData.issues_count} issue{safeData.issues_count !== 1 ? 's' : ''} found
        </p>
      )}

      {safeData.summary && (
        <p className="text-[10px] text-zinc-500 dark:text-zinc-400 leading-snug line-clamp-2">
          {safeData.summary}
        </p>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 !w-2.5 !h-2.5" />
    </div>
  );
});

QANode.displayName = 'QANode';
